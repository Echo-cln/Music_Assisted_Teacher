import { api } from "./api/client.js";
import { renderAuth } from "./pages/auth.js";
import { initGenerationCenter, setGenerationCenterVisible } from "./state/generation.js";
import { initAudioJobCenter, setAudioJobCenterVisible } from "./state/audio_jobs.js";
import { esc, loading, notify } from "./utils/dom.js";

const app = document.getElementById("app");
// 页面按需载入：一个实验性功能页即使有语法/浏览器兼容问题，也不能让登录页、
// 首页和其余功能在模块图阶段一起白屏。
const routeLoaders = {
  home: () => import("./pages/home.js").then(m => m.renderHome),
  assistant: () => import("./pages/assistant.js").then(m => m.renderAssistant),
  classes: () => import("./pages/classes.js").then(m => m.renderClasses),
  resources: () => import("./pages/resources.js").then(m => m.renderResources),
  workbench: () => import("./pages/workbench.js").then(m => m.renderWorkbench),
  lessons: () => import("./pages/lessons.js").then(m => m.renderLessons),
  feedback: () => import("./pages/feedback.js").then(m => m.renderFeedback),
  audio: () => import("./pages/audio.js").then(m => m.renderAudio),
  admin: () => import("./pages/admin.js").then(m => m.renderAdmin),
};
let currentTeacher = null;

function bindRoutes() {
  document.querySelectorAll("[data-route]").forEach(button => {
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
    await initGenerationCenter();
    await initAudioJobCenter();
    await refreshStats();
    await navigate("home");
  });
}

async function refreshStats() {
  try {
    const stats = await api.stats();
    document.getElementById("serviceStatus").textContent = `${stats.songs} 首歌曲 · ${stats.games + stats.theory + stats.mistakes} 条教学知识`;
  } catch (error) {
    document.getElementById("serviceStatus").textContent = error.status === 401 ? "等待登录" : "后端未启动";
  }
}

async function navigate(route = "home") {
  if (!currentTeacher) return showLogin();
  app.innerHTML = loading();
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.route === route));
  // 对应功能页已有完整任务面板；全局仅在离开页面后显示紧凑入口。
  setGenerationCenterVisible(route !== "assistant");
  // 进入音频页时，进行中的任务在页面主体展示，避免全局入口遮挡内容。
  setAudioJobCenterVisible(route !== "audio");
  try {
    const render = await (routeLoaders[route] || routeLoaders.home)();
    await render(app);
    bindRoutes();
  } catch (error) {
    if (error.status === 401) return showLogin();
    app.innerHTML = `<div class="card notice"><h2>页面暂时无法加载</h2><p>${esc(error.message)}</p><p>请确认 Python 后端已经启动并完成数据导入。</p></div>`;
  }
}

async function boot() {
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
    await initGenerationCenter();
    await initAudioJobCenter();
    await refreshStats();
    await navigate("home");
  } catch (error) {
    if (error.status === 401) return showLogin();
    app.innerHTML = `<div class="card notice"><h2>无法连接后端</h2><p>${esc(error.message)}</p></div>`;
  }
}

// 不让模块初始化异常变成“空白页”。错误会显示在页面上，也会打印到控制台，
// 方便教师把准确原因发回，而不是只能看到静态资源 200。
boot().catch(error => {
  console.error("应用启动失败", error);
  app.innerHTML = `<div class="card notice"><h2>页面启动失败</h2><p>${esc(error?.message || "未知前端错误")}</p><p>请按 Ctrl + F5 强制刷新；若仍失败，请将浏览器控制台这条红色错误一并发给我。</p></div>`;
});
