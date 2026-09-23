import { api } from "./api/client.js";
import { renderAssistant } from "./pages/assistant.js";
import { renderAuth } from "./pages/auth.js";
import { renderClasses } from "./pages/classes.js";
import { renderFeedback } from "./pages/feedback.js";
import { renderHome } from "./pages/home.js";
import { renderLessons } from "./pages/lessons.js";
import { renderAIEngine } from "./pages/ai_engine.js";
import { renderResources } from "./pages/resources.js";
import { initGenerationCenter } from "./state/generation.js";
import { esc, loading, notify } from "./utils/dom.js";

const app = document.getElementById("app");
const routes = {
  home: renderHome,
  assistant: renderAssistant,
  classes: renderClasses,
  resources: renderResources,
  lessons: renderLessons,
  feedback: renderFeedback,
  ai_engine: renderAIEngine,
};
let currentTeacher = null;

function bindRoutes() {
  document.querySelectorAll("[data-route]").forEach(button => {
    button.onclick = () => navigate(button.dataset.route);
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
}

async function showLogin() {
  currentTeacher = null;
  document.body.classList.add("auth-mode");
  document.getElementById("generationCenter").classList.add("hidden");
  renderAuth(app, async teacher => {
    applyTeacher(teacher);
    document.body.classList.remove("auth-mode");
    await initGenerationCenter();
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
  try {
    await routes[route](app);
    bindRoutes();
  } catch (error) {
    if (error.status === 401) return showLogin();
    app.innerHTML = `<div class="card notice"><h2>页面暂时无法加载</h2><p>${esc(error.message)}</p><p>请确认 Python 后端已经启动并完成数据导入。</p></div>`;
  }
}

async function boot() {
  bindRoutes();
  window.addEventListener("app:navigate", event => navigate(event.detail));
  document.getElementById("logoutButton").onclick = async () => {
    try {
      await api.logout();
    } finally {
      localStorage.removeItem("activeGenerationJobId");
      notify("已退出登录");
      await showLogin();
    }
  };
  try {
    const teacher = await api.me();
    applyTeacher(teacher);
    document.body.classList.remove("auth-mode");
    await initGenerationCenter();
    await refreshStats();
    await navigate("home");
  } catch (error) {
    if (error.status === 401) return showLogin();
    app.innerHTML = `<div class="card notice"><h2>无法连接后端</h2><p>${esc(error.message)}</p></div>`;
  }
}

boot();
