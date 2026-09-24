import { api } from "../api/client.js";
import { esc } from "../utils/dom.js";

let job = null;
let timer = null;
let dismissed = false;

function render() {
  const root = document.getElementById("audioJobCenter");
  if (!root) return;
  if (!job || dismissed) { root.classList.add("hidden"); root.innerHTML = ""; return; }
  root.classList.remove("hidden");
  const done = job.status === "completed";
  const failed = job.status === "failed";
  root.innerHTML = `<div class="generation-card audio-job-card">
    <div class="generation-head"><div><b>♫ ${done ? "音频分析已完成" : failed ? "音频分析失败" : "音频分析进行中"}</b><small>${esc(job.stage || "正在准备")}</small></div><div class="generation-tools"><span>${Number(job.progress || 0)}%</span><button class="icon-close" aria-label="关闭">×</button></div></div>
    <div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(job.progress || 0)))}%"></i></div>
    <button class="generation-toggle" id="openAudioJob">${done ? "查看已保存分析" : failed ? "查看错误详情" : "前往音频分析页查看"}</button>
    ${failed && job.error_message ? `<p class="generation-error">${esc(job.error_message)}</p>` : ""}
  </div>`;
  root.querySelector(".icon-close").onclick = () => { dismissed = true; render(); };
  root.querySelector("#openAudioJob").onclick = () => {
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
    render();
    if (["completed", "failed"].includes(job.status)) { clearInterval(timer); timer = null; }
  } catch (error) {
    if (error.status === 404 || error.status === 401) localStorage.removeItem("activeAudioJobId");
    job = null; render();
  }
}

function poll() { if (!timer) timer = setInterval(refresh, 1500); }

export async function initAudioJobCenter() { await refresh(); if (job && !["completed", "failed"].includes(job.status)) poll(); }

export async function startAudioJob(form) {
  dismissed = false;
  job = await api.createAudioJob(form);
  localStorage.setItem("activeAudioJobId", job.id);
  render(); poll();
  return job;
}

export async function refreshAudioJob() { await refresh(); return job; }
