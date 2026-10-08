import { api } from "../api/client.js";
import { showModal } from "../components/modal.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const choices = {
  province: ["广东", "广西", "海南", "云南", "贵州", "四川", "湖南", "湖北", "江西", "福建", "浙江", "安徽", "江苏", "山东", "河南", "河北", "山西", "陕西", "甘肃", "青海", "宁夏", "新疆", "内蒙古", "辽宁", "吉林", "黑龙江", "北京", "天津", "上海", "重庆"],
  learning_level: ["基础较弱", "中等", "中等偏上", "基础较好"],
  activity_level: ["较低", "中等", "较高"],
  cooperation: ["需要教师带动", "一般", "喜欢分组合作", "合作意识较强"],
  pitch_level: ["音准基础较弱", "音准不稳定", "音准基础一般", "音准较稳定"],
  rhythm_level: ["节奏偏弱", "恒拍感不足", "节奏基础一般", "节奏基础较好"],
  theory_level: ["乐理理解较弱", "能理解基础术语", "乐理基础较好"],
  preferred_method: ["互动与分组合作", "唱游与律动", "地方文化体验", "基础演唱训练", "合作创编"],
};

const differenceChoices = [
  "音准差异明显", "节奏差异明显", "不太敢开口", "小组合作需要教师带动",
  "后半节容易走神", "高音容易喊唱", "跟不上节奏", "无明显问题",
];

function differenceField(value = "") {
  const saved = (value || "").split(/[、,，;；\n]+/).map(item => item.trim()).filter(Boolean);
  const selected = differenceChoices.filter(option => saved.includes(option));
  const custom = saved.filter(option => !differenceChoices.includes(option));
  return `<fieldset class="student-difference-field full"><legend>需要关注的群体差异（可多选）</legend><p>选择后会进入教案分层任务与课堂观察点；不需要的信息可留空。</p><div class="student-difference-options">${differenceChoices.map(option => `<label class="check-pill"><input type="checkbox" data-student-difference value="${esc(option)}" ${selected.includes(option) ? "checked" : ""}><span>${esc(option)}</span></label>`).join("")}</div><div class="tag-editor" data-student-difference-editor><div class="tag-chip-list" data-tag-list>${custom.map(value => `<span class="custom-tag-chip">${esc(value)}<button type="button" data-remove-tag="${esc(value)}" aria-label="删除标签">×</button></span>`).join("")}</div><input type="text" data-tag-input placeholder="输入其他群体特点，按回车添加"><input type="hidden" data-student-difference-custom value="${esc(custom.join("、"))}"></div></fieldset>`;
}

function selectable(name, label, value, required = true) {
  const listed = choices[name].includes(value);
  return `<label>${label}<select name="${name}" data-choice="${name}" ${required ? "required" : ""}>
    ${!required ? '<option value="">请选择</option>' : ""}
    ${choices[name].map(option => `<option value="${esc(option)}" ${value === option ? "selected" : ""}>${esc(option)}</option>`).join("")}
    <option value="__other__" ${!listed && value ? "selected" : ""}>其他（自行填写）</option>
  </select><input type="text" data-other="${name}" placeholder="请填写${label}" value="${!listed ? esc(value || "") : ""}" ${listed || !value ? "hidden" : ""}></label>`;
}

export async function renderClasses(container) {
  container.innerHTML = pageHeader("班级画像", "记录可观察、与教学直接相关的班级特点，反馈会持续回流。", '<button class="btn primary" id="newClass">新建班级</button>') + `
    <section class="list-search"><label class="search-field"><span>⌕</span><input id="classSearch" type="search" placeholder="搜索班级、省份、教学感受或常见问题"></label><div class="list-filters"><select id="classGradeFilter"><option value="">全部年级</option><option value="lower">1–3 年级</option><option value="upper">4–6 年级</option></select><select id="classActivityFilter"><option value="">全部活跃度</option>${choices.activity_level.map(item => `<option>${esc(item)}</option>`).join("")}</select><select id="classSort"><option value="grade">按年级排序</option><option value="name">按班级名称排序</option></select></div><small id="classSearchCount"></small></section>
    <div id="classGrid" class="class-grid"></div>`;
  document.getElementById("newClass").onclick = () => openClassForm(null, container);
  let searchTimer;
  document.getElementById("classSearch").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadClasses, 220); };
  ["classGradeFilter", "classActivityFilter", "classSort"].forEach(id => document.getElementById(id).onchange = loadClasses);
  await loadClasses();

  async function loadClasses() {
    const q = document.getElementById("classSearch").value.trim();
    let classes = await api.classes(q);
    const grade = document.getElementById("classGradeFilter").value;
    const activity = document.getElementById("classActivityFilter").value;
    if (grade === "lower") classes = classes.filter(item => Number(item.grade) <= 3);
    if (grade === "upper") classes = classes.filter(item => Number(item.grade) >= 4);
    if (activity) classes = classes.filter(item => item.activity_level === activity);
    if (document.getElementById("classSort").value === "name") classes.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    document.getElementById("classSearchCount").textContent = `共 ${classes.length} 个${q ? "匹配班级" : "班级"}`;
    const grid = document.getElementById("classGrid");
    grid.innerHTML = classes.map(item => `<article class="card"><div class="card-head"><span class="iconbox">${item.grade}</span><span class="pill">${esc(item.province)}</span></div><h3>${esc(item.name)}</h3><p class="muted">${item.student_count} 人 · ${esc(item.learning_level)}</p><div class="profile-grid"><div><small>课堂活跃度</small><b>${esc(item.activity_level)}</b></div><div><small>合作情况</small><b>${esc(item.cooperation)}</b></div><div><small>音准</small><b>${esc(item.pitch_level)}</b></div><div><small>节奏</small><b>${esc(item.rhythm_level)}</b></div></div><div class="profile-difference-tags">${(item.common_problems || "").split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean).slice(0, 4).map(value => `<span class="pill soft">${esc(value)}</span>`).join("")}</div><p class="insight">${esc(item.teacher_notes || "尚未填写教学感受")}</p><button class="btn block" data-edit-class="${item.id}">查看 / 编辑</button></article>`).join("") || '<div class="empty">没有找到匹配的班级画像</div>';
    grid.querySelectorAll("[data-edit-class]").forEach(button => {
      button.onclick = () => openClassForm(classes.find(item => item.id === Number(button.dataset.editClass)), container);
    });
  }
}

function bindClassDifferenceTags(root) {
  const editor = root.querySelector("[data-student-difference-editor]");
  if (!editor) return;
  const input = editor.querySelector("[data-tag-input]");
  const hidden = editor.querySelector("[data-student-difference-custom]");
  const list = editor.querySelector("[data-tag-list]");
  let tags = hidden.value.split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean);
  const render = () => {
    hidden.value = tags.join("、");
    list.innerHTML = tags.map(value => `<span class="custom-tag-chip">${esc(value)}<button type="button" data-remove-tag="${esc(value)}" aria-label="删除标签">×</button></span>`).join("");
    list.querySelectorAll("[data-remove-tag]").forEach(button => button.onclick = () => {
      tags = tags.filter(value => value !== button.dataset.removeTag);
      render();
    });
  };
  const add = raw => {
    const values = raw.split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean);
    for (const value of values) if (!tags.includes(value) && value !== "无明显问题") tags.push(value);
    input.value = "";
    render();
  };
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === "," || event.key === "，") {
      event.preventDefault();
      add(input.value);
    }
  });
  input.addEventListener("blur", () => { if (input.value.trim()) add(input.value); });
  render();
}

function openClassForm(existing, container) {
  const item = existing || { name: "", grade: 3, student_count: 30, province: "广东", learning_level: "中等", activity_level: "较高", cooperation: "喜欢分组合作", pitch_level: "音准不稳定", rhythm_level: "节奏偏弱", theory_level: "乐理理解较弱", preferred_method: "互动与分组合作", common_problems: "", teacher_notes: "" };
  const root = showModal(`<div class="modal-head"><div><h2>${existing ? "编辑" : "新建"}班级画像</h2><p>画像字段将直接参与推荐与教案生成。</p></div><button class="close" data-close>×</button></div><form id="classForm" class="form-grid">
    <label>班级名称<input name="name" value="${esc(item.name)}" required></label><label>年级<select name="grade" required>${[1,2,3,4,5,6].map(grade => `<option value="${grade}" ${Number(item.grade) === grade ? "selected" : ""}>${grade} 年级</option>`).join("")}</select></label>
    <label>学生人数<input name="student_count" type="number" min="1" max="100" value="${item.student_count}" required></label>${selectable("province", "所在省份", item.province)}
    ${selectable("learning_level", "整体基础", item.learning_level)}${selectable("activity_level", "课堂活跃度", item.activity_level)}
    ${selectable("cooperation", "合作情况", item.cooperation)}${selectable("pitch_level", "音准情况", item.pitch_level)}
    ${selectable("rhythm_level", "节奏情况", item.rhythm_level)}${selectable("theory_level", "乐理基础", item.theory_level)}
    ${selectable("preferred_method", "喜欢的课堂方式", item.preferred_method)}${differenceField(item.common_problems)}
    <label class="full">教师教学感受<textarea name="teacher_notes">${esc(item.teacher_notes)}</textarea></label>
    <div class="actions full"><button type="button" class="btn" data-close>取消</button><button class="btn primary">保存</button></div>
  </form>`);
  bindClassDifferenceTags(root);
  const differenceBoxes = [...root.querySelectorAll("[data-student-difference]")];
  differenceBoxes.forEach(box => box.addEventListener("change", () => {
    if (box.value === "无明显问题" && box.checked) {
      differenceBoxes.filter(other => other !== box).forEach(other => { other.checked = false; });
    } else if (box.value !== "无明显问题" && box.checked) {
      const none = differenceBoxes.find(other => other.value === "无明显问题");
      if (none) none.checked = false;
    }
  }));
  root.querySelectorAll("[data-choice]").forEach(select => {
    select.onchange = () => {
      const input = root.querySelector(`[data-other="${select.dataset.choice}"]`);
      input.hidden = select.value !== "__other__";
      input.required = select.value === "__other__";
    };
  });
  root.querySelector("#classForm").onsubmit = async event => {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = Object.fromEntries(form.entries());
    for (const select of root.querySelectorAll("[data-choice]")) {
      if (select.value === "__other__") {
        payload[select.name] = root.querySelector(`[data-other="${select.name}"]`).value.trim();
        if (!payload[select.name]) return notify(`请填写“${select.closest("label").firstChild.textContent}”的其他内容`);
      }
    }
    const differences = [...root.querySelectorAll("[data-student-difference]:checked")].map(input => input.value);
    const customDifferences = root.querySelector("[data-student-difference-custom]").value.split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean);
    payload.common_problems = [...new Set([...differences, ...customDifferences])].join("、");
    payload.grade = Number(payload.grade);
    payload.student_count = Number(payload.student_count);
    if (existing) await api.updateClass(existing.id, payload);
    else await api.createClass(payload);
    document.getElementById("modalRoot").innerHTML = "";
    await renderClasses(container);
    notify("班级画像已保存");
  };
}
