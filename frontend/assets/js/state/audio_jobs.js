import { api } from "../api/client.js";
import { esc } from "../utils/dom.js";

let job = null;
let timer = null;
let dismissed = false;
let centerVisible = true;

function render() {
  const root = document.getElementById("audioJobCenter");
  if (!root) return;
  if (!job || dismissed || !centerVisible) { root.classList.add("hidden"); root.innerHTML = ""; return; }
  root.classList.remove("hidden");
  const done = job.status === "completed";
  const failed = job.status === "failed";
  const cancelled = job.status === "cancelled";
  root.innerHTML = `<div class="task-dock audio-dock ${job.status}">
    <div class="task-dock-icon">♫</div><div class="task-dock-copy"><b>${done ? "音频分析完成" : failed ? "音频分析失败" : cancelled ? "音频分析已取消" : "正在分析音频"}</b><small>${esc(job.stage || "正在准备")} · ${Number(job.progress || 0)}%</small></div>
    <button class="task-dock-action" id="openAudioJob">查看</button><button class="icon-close" aria-label="关闭">×</button>
  </div>`;
  root.querySelector(".icon-close").onclick = () => {
    dismissed = true;
    // 终态任务关闭后清除持久化指针，避免把上一次失败带到下一次打开。
    if (["completed", "failed", "cancelled"].includes(job.status)) clearAudioJob();
    else render();
  };
  root.querySelector("#openAudioJob").onclick = () => {
    // 音频卡只能定位音频任务；不要依赖上一次分析结果的 ID。
    localStorage.setItem("activeAudioJobId", job.id);
    if (job.analysis_id) localStorage.setItem("lastAudioAnalysisId", String(job.analysis_id));
    window.dispatchEvent(new CustomEvent("app:navigate", { detail: "audio" }));
  };
}

async function refresh() {
  const id = localStorage.getItem("activeAudioJobId");
  if (!id) { job = null; render(); return; }
  try {
    job = await api.audioJob(id);
    if (job.status === "completed" && job.analysis_id) {
      localStorage.setItem("lastAudioAnalysisId", String(job.analysis_id));
      window.dispatchEvent(new CustomEvent("audio-job:complete", { detail: job }));
    }
    window.dispatchEvent(new CustomEvent("audio-job:update", { detail: job }));
    render();
    if (["completed", "failed", "cancelled"].includes(job.status)) { clearInterval(timer); timer = null; }
  } catch (error) {
    if (error.status === 404 || error.status === 401) localStorage.removeItem("activeAudioJobId");
    job = null; render();
  }
}

function poll() { if (!timer) timer = setInterval(refresh, 1500); }

export async function initAudioJobCenter() { await refresh(); if (job && !["completed", "failed", "cancelled"].includes(job.status)) poll(); }

export async function startAudioJob(form) {
  dismissed = false;
  job = await api.createAudioJob(form);
  localStorage.setItem("activeAudioJobId", job.id);
  render(); poll();
  return job;
}

export async function refreshAudioJob() { await refresh(); return job; }

export async function cancelActiveAudioJob() {
  if (!job || ["completed", "failed", "cancelled"].includes(job.status)) return;
  await api.cancelAudioJob(job.id);
  await refresh();
}

export function clearAudioJob() {
  localStorage.removeItem("activeAudioJobId");
  localStorage.removeItem("lastAudioAnalysisId");
  job = null;
  clearInterval(timer);
  timer = null;
  render();
}

export function setAudioJobCenterVisible(visible) {
  centerVisible = visible;
  if (visible) dismissed = false;
  render();
}
