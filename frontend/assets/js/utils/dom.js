export const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

export function notify(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove("show"), 2400);
}

export function pageHeader(title, subtitle, actions = "") {
  return `<header class="page-head"><div><span class="eyebrow">乡音智谱 · AI 音乐美育工作台</span><h1>${title}</h1><p>${subtitle}</p></div>${actions ? `<div class="actions">${actions}</div>` : ""}</header>`;
}

export function loading(text = "正在加载") {
  return `<div class="card loading">${text}<i></i><i></i><i></i></div>`;
}

