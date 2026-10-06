// EdgeOne 静态前端可在部署时通过 config.js 指向独立的 Python API；本地仍使用同源 /api。
const API_ROOT = (window.__APP_CONFIG__?.apiBaseUrl || "/api").replace(/\/$/, "");

export function apiUrl(path) {
  // 后端历史记录中可能已有 /api/audio/...；新接口内部使用 /audio/...。
  // 无论哪一种都只保留一个 /api 前缀，避免产生 /api/api/... 资源 404。
  const relative = String(path || "").startsWith("/api/") ? String(path).slice(4) : path;
  return `${API_ROOT}${String(relative).startsWith("/") ? relative : `/${relative}`}`;
}

async function responseError(response, path) {
  const url = apiUrl(path);
  const raw = await response.text().catch(() => "");
  let body = null;
  try { body = raw ? JSON.parse(raw) : null; } catch (_) {}
  let detail = body?.detail || body?.message || body?.error;
  if (Array.isArray(detail)) {
    detail = detail.map(item => item?.msg || JSON.stringify(item)).join("；");
  }
  if (detail && typeof detail === "object") detail = JSON.stringify(detail);
  if (response.status === 404 && API_ROOT === "/api" && location.hostname.endsWith(".edgeone.cool")) {
    detail = "EdgeOne 当前只发布了静态前端，预览站点没有找到 /api 后端。请先部署 FastAPI 后端，并在 frontend/config.js 配置它的 HTTPS 地址。";
  } else if (!detail) {
    detail = raw && !raw.trimStart().startsWith("<")
      ? raw.slice(0, 240)
      : `接口未返回错误说明（HTTP ${response.status}）`;
  }
  const err = new Error(`${detail}（HTTP ${response.status}，${url}）`);
  err.status = response.status;
  err.endpoint = url;
  err.requestId = response.headers.get("x-request-id") || response.headers.get("x-vercel-id") || "";
  console.error("API 返回错误", { status: err.status, endpoint: err.endpoint, requestId: err.requestId });
  return err;
}

function networkError(cause, path) {
  const url = apiUrl(path);
  const sameOrigin = API_ROOT.startsWith("/");
  const edgePreview = location.hostname.endsWith(".edgeone.cool");
  const hint = sameOrigin && edgePreview
    ? "当前预览站仍使用同源 /api，但 EdgeOne 只发布了静态前端；需要部署后端并配置其 HTTPS API 地址。"
    : "请检查后端是否运行、API 地址是否正确，以及后端 ALLOWED_ORIGINS 是否包含当前页面来源。";
  const err = new Error(`无法连接后端：${url}。 ${hint}`);
  err.cause = cause;
  err.endpoint = url;
  console.error("API 网络错误", { endpoint: url, cause: cause?.message || String(cause) });
  return err;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      credentials: "include",
      ...options,
      headers: options.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch (cause) {
    throw networkError(cause, path);
  }
  if (!response.ok) throw await responseError(response, path);
  if (response.status === 204) return null;
  return response.json();
}

// fetch 对 FormData 上传没有标准的上传进度回调。乐谱图片可能要经过本机 OMR，
// 因此这里使用 XMLHttpRequest：上传阶段显示真实字节进度，上传结束后明确切换到
// “服务器正在读取/识别”，不再让用户只看到一句“正在导入”。
function uploadRequest(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(path));
    xhr.withCredentials = true;
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      onProgress?.({ phase: "正在上传乐谱", progress: Math.min(65, Math.round(event.loaded / event.total * 65)) });
    };
    xhr.upload.onload = () => onProgress?.({ phase: "上传完成，正在读取乐谱", progress: 70 });
    xhr.onerror = () => reject(new Error("上传连接中断，请检查后端是否仍在运行"));
    xhr.onload = () => {
      let body;
      try { body = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch (_) { body = null; }
      if (xhr.status < 200 || xhr.status >= 300) {
        const error = new Error(body?.detail || `导入失败（HTTP ${xhr.status}）`);
        error.status = xhr.status;
        reject(error);
        return;
      }
      onProgress?.({ phase: "乐谱已解析，正在载入工程", progress: 96 });
      resolve(body);
    };
    xhr.send(form);
  });
}

async function streamRequest(path, payload, onEvent) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (cause) {
    throw networkError(cause, path);
  }
  if (!response.ok) throw await responseError(response, path);
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
      const dataLine = message.split("\\n").find(line => line.startsWith("data: "));
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
  importScore: (form, onProgress) => uploadRequest("/workbench/import", form, onProgress),
  parseNotes: payload => request("/workbench/parse-notes", { method: "POST", body: JSON.stringify(payload) }),
  deleteWorkbenchProject: id => request(`/workbench/projects/${id}`, { method: "DELETE" }),
  adminUsers: () => request("/admin/users"),
  updateAdminUser: (id, payload) => request(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
};
