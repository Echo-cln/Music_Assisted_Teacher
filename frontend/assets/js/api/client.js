// EdgeOne 静态前端可在部署时通过 config.js 指向独立的 Python API；本地仍使用同源 /api。
const API_ROOT = (window.__APP_CONFIG__?.apiBaseUrl || "/api").replace(/\/$/, "");

export function apiUrl(path) {
  return `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    credentials: "include",
    ...options,
    headers: options.body instanceof FormData
      ? options.headers
      : { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    const err = new Error(error.detail || "请求失败");
    err.status = response.status;
    throw err;
  }
  if (response.status === 204) return null;
  return response.json();
}

async function streamRequest(path, payload, onEvent) {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    const err = new Error(error.detail || "请求失败");
    err.status = response.status;
    throw err;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const messages = buffer.split("\n\n");
    buffer = messages.pop();
    for (const message of messages) {
      const dataLine = message.split("\n").find(line => line.startsWith("data: "));
      if (!dataLine) continue;
      const event = JSON.parse(dataLine.slice(6));
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "complete") completed = true;
      onEvent(event);
    }
    if (done) break;
  }
  if (!completed) throw new Error("请求中断，未生成完整预览");
}

export const api = {
  health: () => request("/health"),
  me: () => request("/auth/me"),
  login: payload => request("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  register: payload => request("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  requestEmailVerification: payload => request("/auth/verification/email", { method: "POST", body: JSON.stringify(payload) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  stats: () => request("/stats"),
  classes: (q = "") => request(`/classes?${new URLSearchParams({ q })}`),
  createClass: payload => request("/classes", { method: "POST", body: JSON.stringify(payload) }),
  updateClass: (id, payload) => request(`/classes/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteClass: id => request(`/classes/${id}`, { method: "DELETE" }),
  songs: params => request(`/songs?${new URLSearchParams(params)}`),
  resources: (kind, q = "", sort = "default") => request(`/resources/${kind}?${new URLSearchParams({ q, sort })}`),
  createResource: (kind, payload) => request(`/resources/${kind}`, { method: "POST", body: JSON.stringify(payload) }),
  updateResource: (kind, id, payload) => request(`/resources/${kind}/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteResource: (kind, id) => request(`/resources/${kind}/${id}`, { method: "DELETE" }),
  recommend: payload => request("/songs/recommend", { method: "POST", body: JSON.stringify(payload) }),
  lessons: (q = "") => request(`/lessons?${new URLSearchParams({ q })}`),
  generateLesson: payload => request("/lessons/generate", { method: "POST", body: JSON.stringify(payload) }),
  generateLessonStream: (payload, onEvent) => streamRequest("/lessons/generate/stream", payload, onEvent),
  createGenerationJob: payload => request("/generation-jobs", { method: "POST", body: JSON.stringify(payload) }),
  generationJobs: (limit = 10) => request(`/generation-jobs?${new URLSearchParams({ limit })}`),
  generationJob: id => request(`/generation-jobs/${id}`),
  cancelGenerationJob: id => request(`/generation-jobs/${id}`, { method: "DELETE" }),
  adjustPreviewStream: (payload, onEvent) => streamRequest("/lessons/preview/adjust/stream", payload, onEvent),
  saveLesson: payload => request("/lessons/save", { method: "POST", body: JSON.stringify(payload) }),
  updateLesson: (id, payload) => request(`/lessons/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  adjustLesson: (id, instruction) => request(`/lessons/${id}/adjust`, { method: "POST", body: JSON.stringify({ instruction }) }),
  analyzeAudio: form => request("/audio/analyze", { method: "POST", body: form }),
  createAudioJob: form => request("/audio/jobs", { method: "POST", body: form }),
  audioJob: id => request(`/audio/jobs/${id}`),
  cancelAudioJob: id => request(`/audio/jobs/${id}`, { method: "DELETE" }),
  audioAnalyses: () => request("/audio/analyses"),
  audioAnalysis: id => request(`/audio/analyses/${id}`),
  feedback: payload => request("/feedback", { method: "POST", body: JSON.stringify(payload) }),
  feedbackRecords: () => request("/feedback"),
  workbenchProjects: () => request("/workbench/projects"),
  workbenchProject: id => request(`/workbench/projects/${id}`),
  createWorkbenchProject: payload => request("/workbench/projects", { method: "POST", body: JSON.stringify(payload) }),
  arrangeProject: (id, payload) => request(`/workbench/projects/${id}/arrange`, { method: "POST", body: JSON.stringify(payload) }),
  importScore: form => request("/workbench/import", { method: "POST", body: form }),
  parseNotes: payload => request("/workbench/parse-notes", { method: "POST", body: JSON.stringify(payload) }),
  deleteWorkbenchProject: id => request(`/workbench/projects/${id}`, { method: "DELETE" }),
  adminUsers: () => request("/admin/users"),
  updateAdminUser: (id, payload) => request(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
};
