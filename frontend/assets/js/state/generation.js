import { api } from "../api/client.js";
import { esc } from "../utils/dom.js";

let currentJob = null;
let timer = null;
let started = false;
let centerVisible = false;
let detailsOpen = false;
let dismissed = false;
let previousStatus = null;
let completionToastShown = false;
let completionToastTimer = null;

function elapsedText(seconds = 0) {
  return seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
}

function emit() {
  window.dispatchEvent(new CustomEvent("generation:update", { detail: currentJob }));
}

function removeCompletionToast() {
  clearTimeout(completionToastTimer);
  completionToastTimer = null;
  document.getElementById("generationCompletionToast")?.remove();
}

// 只在用户离开 AI 教案助手后提醒，避免遮挡教案生成与查看。
function showCompletionToast() {
  if (!currentJob || centerVisible || completionToastShown) return;
  completionToastShown = true;
  removeCompletionToast();
  const toast = document.createElement("aside");
  toast.id = "generationCompletionToast";
  toast.className = "generation-completion-toast";
  toast.setAttribute("role", "status");
  toast.innerHTML = `<div><b>教案已生成完成</b><small>${currentJob.strategy_used === "fast" ? "快速生成" : "深度思考"} · 用时 ${elapsedText(currentJob.elapsed_seconds || 0)}</small></div><button class="icon-close" aria-label="关闭完成提醒">×</button>`;
  toast.querySelector("button").onclick = removeCompletionToast;
  document.body.appendChild(toast);
  completionToastTimer = setTimeout(removeCompletionToast, 12000);
}

function render() {
  const root = document.getElementById("generationCenter");
  if (!root) return;
  if (!currentJob || !centerVisible || dismissed) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }
  root.classList.remove("hidden");
  const statusText = currentJob.status === "completed" ? "教案已生成" : currentJob.status === "failed" ? "生成失败" : currentJob.status === "cancelled" ? "生成已取消" : "正在生成详细教案";
  const steps = (currentJob.steps || []).map(step => `<li class="${step.state}"><span>${step.state === "done" ? "✓" : step.state === "running" ? "●" : step.state === "error" ? "!" : "○"}</span>${esc(step.label)}</li>`).join("");
  root.innerHTML = `<div class="generation-card">
    <div class="generation-head">
      <div><b>✦ ${statusText}</b><small>${esc(currentJob.stage || "处理中")} · 已耗时 ${elapsedText(currentJob.elapsed_seconds || 0)}</small></div>
      <div class="generation-tools"><span>${Number(currentJob.progress || 0)}%</span><button class="icon-close" id="dismissGeneration" aria-label="关闭">×</button></div>
    </div>
    <div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(currentJob.progress || 0)))}%"></i></div>
    <button type="button" class="generation-toggle" id="toggleGeneration" aria-expanded="${detailsOpen}">${detailsOpen ? "收起生成步骤" : "查看生成步骤与依据"}</button>
    ${detailsOpen || currentJob.status === "failed" ? `<ul class="generation-steps">${steps}</ul>${currentJob.error_message ? `<p class="generation-error">${esc(currentJob.error_message)}</p>` : ""}` : ""}
    ${currentJob.status === "completed" ? '<button class="btn soft block" id="openGeneratedLesson">查看已生成教案</button>' : ""}
    ${!["completed", "failed", "cancelled"].includes(currentJob.status) ? '<button class="btn soft block" id="cancelGeneration">取消本次生成</button>' : ""}
  </div>`;
  const open = root.querySelector("#openGeneratedLesson");
  if (open) open.onclick = () => window.dispatchEvent(new CustomEvent("app:navigate", { detail: "assistant" }));
  const cancel = root.querySelector("#cancelGeneration");
  if (cancel) cancel.onclick = async () => {
    await api.cancelGenerationJob(currentJob.id);
    clearGenerationJob();
  };
  const dismiss = root.querySelector("#dismissGeneration");
  if (dismiss) dismiss.onclick = () => { dismissed = true; render(); };
  const toggle = root.querySelector("#toggleGeneration");
  if (toggle) toggle.addEventListener("click", () => { detailsOpen = !detailsOpen; render(); });
}

async function refresh() {
  const id = localStorage.getItem("activeGenerationJobId");
  if (!id) {
    currentJob = null;
    render();
    emit();
    return;
  }
  try {
    currentJob = await api.generationJob(id);
    if (currentJob.status === "completed" && previousStatus !== "completed") showCompletionToast();
    previousStatus = currentJob.status;
    render();
    emit();
    if (["completed", "failed", "cancelled"].includes(currentJob.status)) {
      clearInterval(timer);
      timer = null;
    }
  } catch (error) {
    if (error.status === 404 || error.status === 401) {
      localStorage.removeItem("activeGenerationJobId");
      if (error.status === 404) window.dispatchEvent(new CustomEvent("generation:expired"));
    }
    currentJob = null;
    render();
    emit();
  }
}

function ensurePolling() {
  if (timer) return;
  timer = setInterval(refresh, 2500);
}

export async function initGenerationCenter() {
  if (started) return;
  started = true;
  await refresh();
  if (currentJob && !["completed", "failed", "cancelled"].includes(currentJob.status)) ensurePolling();
}

export async function startGeneration(payload) {
  dismissed = false;
  detailsOpen = false;
  completionToastShown = false;
  removeCompletionToast();
  currentJob = await api.createGenerationJob(payload);
  if (currentJob.status === "completed") showCompletionToast();
  previousStatus = currentJob.status;
  localStorage.setItem("activeGenerationJobId", currentJob.id);
  render();
  emit();
  ensurePolling();
  return currentJob;
}

export async function refreshGeneration() {
  await refresh();
  if (currentJob && !["completed", "failed"].includes(currentJob.status)) ensurePolling();
  return currentJob;
}

export function getGenerationJob() {
  return currentJob;
}

export function clearGenerationJob() {
  localStorage.removeItem("activeGenerationJobId");
  currentJob = null;
  clearInterval(timer);
  timer = null;
  render();
  emit();
}

export function setGenerationCenterVisible(visible) {
  centerVisible = visible;
  if (visible) dismissed = false;
  if (!visible && currentJob?.status === "completed") showCompletionToast();
  render();
}
