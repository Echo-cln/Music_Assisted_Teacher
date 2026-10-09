import { api } from "./api/client.js";
import { renderAuth } from "./pages/auth.js?v=20261007-login1";
import { initGenerationCenter, setGenerationCenterVisible } from "./state/generation.js";
import { initAudioJobCenter, setAudioJobCenterVisible } from "./state/audio_jobs.js";
import { esc, loading, notify } from "./utils/dom.js";

const app = document.getElementById("app");
// 页面按需载入：一个实验性功能页即使有语法/浏览器兼容问题，也不能让登录页、
// 首页和其余功能在模块图阶段一起白屏。
const routeLoaders = {
  home: () => import("./pages/home.js").then(m => m.renderHome),
  assistant: () => import("./pages/assistant.js?v=20261009-dialogue-trends").then(m => m.renderAssistant),
  classes: () => import("./pages/classes.js?v=20261009-dialogue-trends").then(m => m.renderClasses),
  resources: () => import("./pages/resources.js").then(m => m.renderResources),
  workbench: () => import("./pages/workbench.js").then(m => m.renderWorkbench),
  lessons: () => import("./pages/lessons.js?v=20261007-6").then(m => m.renderLessons),
  feedback: () => import("./pages/feedback.js?v=20261007-5").then(m => m.renderFeedback),
  audio: () => import("./pages/audio.js?v=20261007-pilot1").then(m => m.renderAudio),
  admin: () => import("./pages/admin.js").then(m => m.renderAdmin),
};
let currentTeacher = null;
let navigationSequence = 0;

function bindRoutes(root = document) {
  root.querySelectorAll("[data-route]").forEach(button => {
    button.onclick = () => {
      if (button.dataset.resourceKind) sessionStorage.setItem("resourceKindToOpen", button.dataset.resourceKind);
      navigate(button.dataset.route);
    };
  });
}

function applyTeacher(teacher) {
  currentTeacher = teacher;
  const name = document.getElementById("teacherName");
  const meta = document.getElementById("teacherMeta");
  const avatar = document.getElementById("teacherAvatar");
  if (name) name.textContent = teacher.display_name;
  if (meta) meta.textContent = teacher.school || `@${teacher.username}`;
  if (avatar) avatar.textContent = (teacher.display_name || teacher.username || "师").slice(0, 1);
  document.getElementById("adminNav")?.classList.toggle("hidden", teacher.role !== "admin");
}

async function showLogin() {
  currentTeacher = null;
  document.body.classList.add("auth-mode");
  document.getElementById("generationCenter").classList.add("hidden");
  document.getElementById("audioJobCenter").classList.add("hidden");
  renderAuth(app, async teacher => {
    applyTeacher(teacher);
    document.body.classList.remove("auth-mode");
    await navigate("home");
    initializeBackgroundPanels();
  });
}

function initializeBackgroundPanels() {
  // 先显示页面，再初始化任务中心和统计，避免启动阶段串行等待多个接口。
  Promise.allSettled([initGenerationCenter(), initAudioJobCenter(), refreshStats()]).then(results => {
    for (const result of results) {
      if (result.status === "rejected") console.error("后台面板初始化失败", result.reason);
    }
  });
}

async function refreshStats() {
  try {
    const stats = await api.stats();
    document.getElementById("serviceStatus").textContent = `${stats.songs} 首歌曲 · ${stats.games + stats.theory + stats.mistakes} 条教学知识 · 前端 2026.10.08`;
  } catch (error) {
    document.getElementById("serviceStatus").textContent = error.status === 401 ? "等待登录" : "后端未启动 · 前端 2026.10.07";
  }
}

async function navigate(route = "home") {
  if (!currentTeacher) return showLogin();
  const sequence = ++navigationSequence;
  app.innerHTML = loading();
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.route === route));
  // 对应功能页已有完整任务面板；全局仅在离开页面后显示紧凑入口。
  setGenerationCenterVisible(route !== "assistant");
  // 进入音频页时，进行中的任务在页面主体展示，避免全局入口遮挡内容。
  setAudioJobCenterVisible(route !== "audio");
  try {
    const render = await (routeLoaders[route] || routeLoaders.home)();
    // 页面模块加载期间用户可能已经切页；过期导航不得启动渲染。
    if (sequence !== navigationSequence) return;
    // 独立容器令旧页面的迟到响应只能修改已脱离文档的节点。
    const page = document.createElement("div");
    page.style.display = "contents";
    app.replaceChildren(page);
    await render(page);
    if (sequence !== navigationSequence) return;
    bindRoutes(app);
  } catch (error) {
    // 旧页面的迟到异常不能覆盖当前页面。
    if (sequence !== navigationSequence) return;
    if (error.status === 401) return showLogin();
    app.innerHTML = `<div class="card notice"><h2>页面暂时无法加载</h2><p>${esc(error.message)}</p><p>请打开浏览器控制台查看具体错误；此处会区分前端脚本、接口和数据错误。</p></div>`;
  }
}

async function boot() {
  localStorage.removeItem("lastAudioAnalysisId");
  bindRoutes();
  window.addEventListener("app:navigate", event => navigate(event.detail));
  window.addEventListener("generation:expired", () => notify("上一条生成任务已不在当前数据中，已清除旧进度记录。"));
  // 旧浏览器缓存到上一个 index.html 时，退出按钮可能暂时不存在；
  // 不能因为一个非核心节点让整个应用在第一条 API 请求前白屏。
  document.getElementById("logoutButton")?.addEventListener("click", async () => {
    try {
      await api.logout();
    } finally {
      localStorage.removeItem("activeGenerationJobId");
      notify("已退出登录");
      await showLogin();
    }
  });
  try {
    const teacher = await api.me();
    applyTeacher(teacher);
    document.body.classList.remove("auth-mode");
    await navigate("home");
    initializeBackgroundPanels();
  } catch (error) {
    if (error.status === 401) return showLogin();
    console.error("后端连接失败", error);
    const staticEdge = location.hostname.endsWith(".edgeone.cool");
    const nextStep = staticEdge
      ? "当前地址只提供静态网页；登录、教案、音频和保存功能还需要 FastAPI 后端。你之前选择本机运行时，请使用项目根目录的 .\\run.bat 打开的 http://127.0.0.1:8000。"
      : "如要本机使用，请在项目根目录运行 .\\run.bat，再打开 http://127.0.0.1:8000。";
    app.innerHTML = `<div class="card notice"><span class="eyebrow">连接诊断 · 前端 2026.10.07</span><h2>暂时连不上后端</h2><p>${esc(error.message)}</p><p>${esc(nextStep)}</p></div>`;
  }
}

// 不让模块初始化异常变成“空白页”。错误会显示在页面上，也会打印到控制台，
// 方便教师把准确原因发回，而不是只能看到静态资源 200。
boot().catch(error => {
  console.error("应用启动失败", error);
  app.innerHTML = `<div class="card notice"><h2>页面启动失败</h2><p>${esc(error?.message || "未知前端错误")}</p><p>请按 Ctrl + F5 强制刷新；若仍失败，请将浏览器控制台这条红色错误一并发给我。</p></div>`;
});
