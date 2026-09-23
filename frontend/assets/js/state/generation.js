import { api } from "../api/client.js";
import { esc } from "../utils/dom.js";

let currentJob = null;
let timer = null;
let started = false;

function emit() {
  window.dispatchEvent(new CustomEvent("generation:update", { detail: currentJob }));
}

function render() {
  const root = document.getElementById("generationCenter");
  if (!root) return;
  if (!currentJob) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }
  root.classList.remove("hidden");
  const statusText = currentJob.status === "completed" ? "生成完成" : currentJob.status === "failed" ? "生成失败" : "AI 正在生成";
  const steps = (currentJob.steps || []).map(step => `<li class="${step.state}"><span>${step.state === "done" ? "✓" : step.state === "running" ? "●" : step.state === "error" ? "!" : "○"}</span>${esc(step.label)}</li>`).join("");
  root.innerHTML = `<div class="generation-card">
    <div class="generation-head">
      <div><b>✦ ${statusText}</b><small>${esc(currentJob.stage || "处理中")}</small></div>
      <span>${Number(currentJob.progress || 0)}%</span>
    </div>
    <div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(currentJob.progress || 0)))}%"></i></div>
    <details ${currentJob.status === "failed" ? "open" : ""}><summary>查看生成步骤与依据</summary><ul class="generation-steps">${steps}</ul>${currentJob.error_message ? `<p class="generation-error">${esc(currentJob.error_message)}</p>` : ""}</details>
    ${currentJob.status === "completed" ? '<button class="btn soft block" id="openGeneratedLesson">查看已生成教案</button>' : ""}
  </div>`;
  const open = document.getElementById("openGeneratedLesson");
  if (open) open.onclick = () => window.dispatchEvent(new CustomEvent("app:navigate", { detail: "assistant" }));
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
    render();
    emit();
    if (["completed", "failed"].includes(currentJob.status)) {
      clearInterval(timer);
      timer = null;
    }
  } catch (error) {
    if (error.status === 404 || error.status === 401) localStorage.removeItem("activeGenerationJobId");
    currentJob = null;
    render();
    emit();
  }
}

function ensurePolling() {
  if (timer) return;
  timer = setInterval(refresh, 1100);
}

export async function initGenerationCenter() {
  if (started) return;
  started = true;
  await refresh();
  if (currentJob && !["completed", "failed"].includes(currentJob.status)) ensurePolling();
}

export async function startGeneration(payload) {
  currentJob = await api.createGenerationJob(payload);
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
