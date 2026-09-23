import { api } from "../api/client.js";
import { showModal } from "../components/modal.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const types = {
  songs: { title: "地区歌曲", display: "name", fields: { name: "歌曲名称", region: "地区", province: "省份", mood: "情绪", mode: "调式", grade: "适用年级", source: "来源", song_type: "歌曲类型", range_note: "音域说明", range_score: "音域难度", rhythm_score: "节奏难度", dialect_score: "方言难度", difficulty: "综合难度" } },
  games: { title: "音乐游戏", display: "name", fields: { category: "类别", name: "游戏名称", personality: "适用班级特点", grade: "适用年级", match_condition: "匹配条件", instructions: "游戏步骤" } },
  theory: { title: "乐理话术", display: "term", fields: { category: "类别", term: "乐理术语", lower_grade_script: "低年级话术", upper_grade_script: "高年级话术" } },
  mistakes: { title: "易错纠正", display: "problem", fields: { category: "类别", problem: "常见问题", correction: "纠正方法" } },
};

const defaults = {
  songs: { name: "", region: "华南地区", province: "广东", mood: "活泼", mode: "五声调式", grade: "三年级", source: "教师自建资源", song_type: "童谣", range_note: "C调，适中音域", range_score: 2, rhythm_score: 2, dialect_score: 1, difficulty: "2星" },
  games: { category: "节奏游戏", name: "", personality: "适合互动课堂", grade: "1-6年级", match_condition: "节奏训练、分组合作", instructions: "" },
  theory: { category: "节拍与节奏", term: "", lower_grade_script: "", upper_grade_script: "" },
  mistakes: { category: "音准", problem: "", correction: "" },
};

let selectedType = "songs";

export async function renderResources(container) {
  container.innerHTML = pageHeader(
    "教学资源库",
    "系统内置资源全体教师共享且只读；你可以直接在页面新增、编辑和删除自己的歌曲、游戏、乐理与易错纠正资源。",
    '<button class="btn primary" id="newResource">＋ 新增资源</button>'
  ) + `
    <section class="card"><div class="tabs resource-tabs">${Object.entries(types).map(([key, type]) => `<button class="tab ${selectedType === key ? "active" : ""}" data-resource-tab="${key}">${type.title}</button>`).join("")}</div>
    <label>搜索当前分类<input id="resourceSearch" placeholder="输入名称或问题关键词"></label>
    <div id="resourceList"></div></section>`;

  document.getElementById("newResource").onclick = () => openResourceForm(selectedType, { ...defaults[selectedType] }, "create");
  container.querySelectorAll("[data-resource-tab]").forEach(button => button.onclick = () => {
    selectedType = button.dataset.resourceTab;
    container.querySelectorAll("[data-resource-tab]").forEach(tab => tab.classList.toggle("active", tab === button));
    document.getElementById("resourceSearch").value = "";
    loadRows();
  });
  let searchTimer;
  document.getElementById("resourceSearch").oninput = () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadRows, 240);
  };
  await loadRows();
}

async function loadRows() {
  const kind = selectedType;
  const target = document.getElementById("resourceList");
  const q = document.getElementById("resourceSearch").value.trim();
  try {
    const rows = await api.resources(kind, q);
    if (selectedType !== kind) return;
    const mine = rows.filter(row => row.scope === "mine").length;
    const system = rows.length - mine;
    target.innerHTML = `<p class="muted">共 ${rows.length} 条${q ? "搜索结果" : "记录"} · 我的资源 ${mine} 条 · 系统资源 ${system} 条</p>
      <div class="resource-list">${rows.map(row => `<article class="resource-row"><div><strong>${esc(row[types[kind].display])}</strong><small>${esc(row.category || row.province)} · ${esc(row.grade || row.match_condition || "资源条目")}</small></div><div class="resource-actions"><span class="resource-scope ${row.scope}">${row.scope === "mine" ? "我的资源" : "系统内置"}</span><button class="btn" data-resource-id="${row.id}">${row.editable ? "查看 / 编辑" : "查看 / 复制"}</button></div></article>`).join("") || '<div class="empty">没有找到相关资源</div>'}</div>`;
    target.querySelectorAll("[data-resource-id]").forEach(button => button.onclick = () => {
      const row = rows.find(item => item.id === Number(button.dataset.resourceId));
      openResourceForm(kind, row, row.editable ? "edit" : "clone");
    });
  } catch (error) {
    target.innerHTML = `<div class="notice">${esc(error.message)}</div>`;
  }
}

function openResourceForm(kind, row, mode) {
  const type = types[kind];
  const inputs = Object.entries(type.fields).map(([field, label]) => {
    const value = row[field] ?? "";
    if (["match_condition", "instructions", "lower_grade_script", "upper_grade_script", "problem", "correction"].includes(field)) {
      return `<label class="full">${label}<textarea name="${field}" required>${esc(value)}</textarea></label>`;
    }
    return `<label>${label}<input name="${field}" type="${field.endsWith("_score") ? "number" : "text"}" ${field.endsWith("_score") ? 'min="0" max="10"' : ""} value="${esc(value)}" required></label>`;
  }).join("");
  const title = mode === "create" ? `新增${type.title}` : mode === "clone" ? `复制系统${type.title}为我的资源` : `编辑${type.title}`;
  const sub = mode === "clone" ? "系统资源保持不变；保存后会生成你的私人副本。" : mode === "create" ? "新增内容只属于当前教师账号。" : `第 ${row.id} 条 · 更新后下一次备课立即生效`;
  const deleteButton = mode === "edit" ? '<button class="btn danger" type="button" id="deleteResource">删除</button>' : "";
  const modal = showModal(`<div class="modal-head"><div><h2>${title}</h2><p>${sub}</p></div><button class="close" data-close>×</button></div><form id="resourceForm" class="form-grid">${inputs}<div class="actions full">${deleteButton}<span class="grow"></span><button class="btn" type="button" data-close>取消</button><button class="btn primary" type="submit">${mode === "edit" ? "保存更改" : "保存到我的资源"}</button></div></form>`);

  modal.querySelector("#resourceForm").onsubmit = async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    for (const key of ["range_score", "rhythm_score", "dialect_score"]) {
      if (key in payload) payload[key] = Number(payload[key]);
    }
    const button = event.target.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      if (mode === "edit") await api.updateResource(kind, row.id, payload);
      else await api.createResource(kind, payload);
      document.getElementById("modalRoot").innerHTML = "";
      await loadRows();
      notify(mode === "edit" ? "资源已更新" : "已新增到你的个人资源库");
    } catch (error) {
      button.disabled = false;
      notify(error.message);
    }
  };

  const deleteBtn = modal.querySelector("#deleteResource");
  if (deleteBtn) deleteBtn.onclick = async () => {
    if (!confirm("确定删除这条个人资源吗？系统内置资源不会受影响。")) return;
    deleteBtn.disabled = true;
    try {
      await api.deleteResource(kind, row.id);
      document.getElementById("modalRoot").innerHTML = "";
      await loadRows();
      notify("个人资源已删除");
    } catch (error) {
      deleteBtn.disabled = false;
      notify(error.message);
    }
  };
}
