import { api } from "../api/client.js?v=20261009-dialogue-trends";
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
    grid.innerHTML = classes.map(item => `<article class="card"><div class="card-head"><span class="iconbox">${item.grade}</span><span class="pill">${esc(item.province)}</span></div><h3>${esc(item.name)}</h3><p class="muted">${item.student_count} 人 · ${esc(item.learning_level)}</p><div class="profile-grid"><div><small>课堂活跃度</small><b>${esc(item.activity_level)}</b></div><div><small>合作情况</small><b>${esc(item.cooperation)}</b></div><div><small>音准</small><b>${esc(item.pitch_level)}</b></div><div><small>节奏</small><b>${esc(item.rhythm_level)}</b></div></div><div class="profile-difference-tags">${(item.common_problems || "").split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean).slice(0, 4).map(value => `<span class="pill soft">${esc(value)}</span>`).join("")}</div><p class="insight">${esc(item.teacher_notes || "尚未填写教学感受")}</p><div class="actions"><button class="btn" data-class-details="${item.id}">班级详情与趋势</button><button class="btn soft" data-edit-class="${item.id}">编辑画像</button></div></article>`).join("") || '<div class="empty">没有找到匹配的班级画像</div>';
    grid.querySelectorAll("[data-edit-class]").forEach(button => {
      button.onclick = () => openClassForm(classes.find(item => item.id === Number(button.dataset.editClass)), container);
    });
    grid.querySelectorAll("[data-class-details]").forEach(button => {
      button.onclick = () => openClassDetails(classes.find(item => item.id === Number(button.dataset.classDetails)));
    });
  }
}


function openClassDetails(item) {
  if (!item) return;
  const root = showModal(`<div class="modal-head"><div><span class="eyebrow">CLASS PROFILE</span><h2>${esc(item.name)} · 班级详情</h2><p>${item.grade} 年级 · ${esc(item.province)} · ${item.student_count} 人</p></div><button class="close" data-close>×</button></div>
    <div class="tabs class-detail-tabs"><button class="tab active" data-class-detail-tab="profile">班级画像</button><button class="tab" data-class-detail-tab="trends">学情趋势</button></div>
    <section data-class-detail-panel="profile"><div class="profile-grid"><div><small>整体基础</small><b>${esc(item.learning_level)}</b></div><div><small>课堂活跃度</small><b>${esc(item.activity_level)}</b></div><div><small>合作情况</small><b>${esc(item.cooperation)}</b></div><div><small>音准</small><b>${esc(item.pitch_level)}</b></div><div><small>节奏</small><b>${esc(item.rhythm_level)}</b></div><div><small>乐理</small><b>${esc(item.theory_level)}</b></div></div><h3>需要关注的群体差异</h3><div class="profile-difference-tags">${(item.common_problems || "").split(/[、,，;；\\n]+/).map(value => value.trim()).filter(Boolean).map(value => `<span class="pill soft">${esc(value)}</span>`).join("") || '<span class="muted">尚无记录</span>'}</div><p class="insight">${esc(item.teacher_notes || "尚未填写教学感受")}</p><div class="actions"><button class="btn primary" data-edit-detail>编辑班级画像</button><button class="btn" data-close>关闭</button></div></section>
    <section data-class-detail-panel="trends" hidden><div class="class-trend-view">
      <header class="class-trend-head"><div><span class="eyebrow">CLASSROOM EVIDENCE</span><h3>近几次课堂表现</h3><p class="muted">音准与节奏来自已关联的音频分析；参与和合作来自课后观察。只呈现班级整体，不展示学生个人排名。</p></div>
        <div class="trend-mode-toggle hidden" data-trend-mode-toggle role="group" aria-label="趋势数据类型"><button type="button" class="active" data-trend-mode="demo">演示预览</button><button type="button" data-trend-mode="real">课堂记录</button></div>
      </header>
      <div data-trend-summary class="trend-summary"></div><div data-trend-source class="trend-data-source"></div>
      <div data-trend-grid class="trend-chart-grid"><div class="trend-loading">正在读取课堂记录…</div></div>
    </div></section>`);
  const buttons = [...root.querySelectorAll("[data-class-detail-tab]")], panels = [...root.querySelectorAll("[data-class-detail-panel]")];
  let data = null, selectedMode = "real";
  const metrics = [
    { key: "pitch_stability", title: "音准轨迹稳定度", subtitle: "主音高轨迹的稳定程度", type: "score" },
    { key: "rhythm_regularness", title: "节奏规律度", subtitle: "起音间隔的规律程度", type: "score" },
    { key: "participation", title: "课堂参与", subtitle: "教师课后观察", type: "participation" },
    { key: "cooperation", title: "合作情况", subtitle: "教师课后观察", type: "cooperation" },
  ];
  const dateLabel = value => String(value || "").startsWith("演示") ? value : String(value || "").slice(5, 10);
  const valueLabel = (metric, value) => metric.type === "score" ? (value == null ? "—" : `${value} 分`) : (value || "—");
  const drawCard = (metric, sourcePoints) => {
    const points = sourcePoints.filter(point => point[metric.key] !== null && point[metric.key] !== undefined && point[metric.key] !== "").slice(-6);
    const latest = points.at(-1);
    let chart = '<div class="trend-chart-empty">暂无记录</div>';
    if (points.length) {
      const width = 520, height = 184, left = metric.type === "score" ? 43 : 92, right = 14, top = 15, bottom = 37;
      const plotWidth = width - left - right, plotHeight = height - top - bottom, isScore = metric.type === "score";
      const categoryOrder = metric.type === "participation" ? { "需要带动": 1, "参与一般": 2, "参与积极": 3 } : { "需要教师带动": 1, "合作一般": 2, "主动合作": 3 };
      const categoryLabels = metric.type === "participation" ? ["需要带动", "参与一般", "参与积极"] : ["需要教师带动", "合作一般", "主动合作"];
      const coords = points.map((point, index) => {
        const raw = isScore ? Number(point[metric.key]) : categoryOrder[point[metric.key]];
        const value = Number.isFinite(raw) ? raw : (isScore ? 0 : 1);
        return { x: left + (points.length === 1 ? plotWidth / 2 : index * plotWidth / (points.length - 1)), y: top + plotHeight - (isScore ? Math.max(0, Math.min(100, value)) / 100 : (value - 1) / 2) * plotHeight, value: point[metric.key], point };
      });
      const ticks = isScore ? [0, 50, 100].map(value => ({ value: `${value}`, y: top + plotHeight - value / 100 * plotHeight })) : categoryLabels.map((value, index) => ({ value, y: top + plotHeight - index * plotHeight / 2 }));
      const grid = ticks.map(tick => `<line x1="${left}" y1="${tick.y}" x2="${width - right}" y2="${tick.y}" class="trend-grid"/><text x="${left - 8}" y="${tick.y + 4}" text-anchor="end" class="trend-axis-label">${esc(tick.value)}</text>`).join("");
      const line = coords.length > 1 ? `<polyline points="${coords.map(point => `${point.x},${point.y}`).join(" ")}" class="trend-line"/>` : "";
      const marks = coords.map(point => `<circle cx="${point.x}" cy="${point.y}" r="5" class="trend-dot"><title>${esc(dateLabel(point.point.date))}：${esc(valueLabel(metric, point.value))}</title></circle><text x="${point.x}" y="${height - 10}" text-anchor="middle" class="trend-axis-label">${esc(dateLabel(point.point.date))}</text>`).join("");
      chart = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(metric.title)}趋势">${grid}${line}${marks}</svg>`;
      if (points.length === 1) chart += '<small class="trend-chart-hint">已有 1 次记录；累计两次后显示变化线</small>';
    }
    return `<article class="trend-chart-card"><header><div><h4>${esc(metric.title)}</h4><p>${esc(metric.subtitle)}</p></div><strong class="trend-latest">${esc(valueLabel(metric, latest?.[metric.key]))}</strong></header><div class="trend-chart-canvas">${chart}</div><footer><span>${points.length ? `最近 ${points.length} 次记录` : "暂无有效记录"}</span><small>${esc(latest?.source || "等待课堂记录")}</small></footer></article>`;
  };
  const render = () => {
    if (!data) return;
    const demoMode = selectedMode === "demo" && data.demo_available && data.demo_points?.length;
    const points = demoMode ? data.demo_points : data.points;
    root.querySelector("[data-trend-summary]").textContent = demoMode
      ? "演示预览使用示例数值，只用于查看四项趋势图的排版和交互，不代表该班真实表现。"
      : points.length >= 2 ? `已读取 ${points.length} 条课堂记录；趋势以真实归档记录为准。`
      : `课堂记录积累中：当前有 ${points.length} 条有效记录，建议结合音频分析和课后观察继续记录。`;
    const realSources = [...new Set(points.filter(point => point.source && !point.source.includes("演示样例")).map(point => point.source))];
    root.querySelector("[data-trend-source]").textContent = demoMode
      ? `演示班级：${esc(data.class_name)} · 样例数据 4 次 · 与真实课堂反馈分开保存`
      : `真实数据来源：${realSources.join("、") || "暂未归档"} · 已归档 ${data.record_count} 条反馈 · 最近更新：${data.updated_at?.slice(0, 10) || "暂无"}`;
    root.querySelector("[data-trend-grid]").innerHTML = metrics.map(metric => drawCard(metric, points || [])).join("");
  };
  root.querySelectorAll("[data-trend-mode]").forEach(button => button.onclick = () => {
    selectedMode = button.dataset.trendMode;
    root.querySelectorAll("[data-trend-mode]").forEach(mode => mode.classList.toggle("active", mode === button));
    render();
  });
  buttons.forEach(button => button.onclick = async () => {
    buttons.forEach(mode => mode.classList.toggle("active", mode === button));
    panels.forEach(panel => panel.hidden = panel.dataset.classDetailPanel !== button.dataset.classDetailTab);
    if (button.dataset.classDetailTab === "trends" && !data) {
      try {
        data = await api.classTrends(item.id);
        selectedMode = data.demo_available ? "demo" : "real";
        root.querySelector("[data-trend-mode-toggle]").classList.toggle("hidden", !data.demo_available);
        root.querySelectorAll("[data-trend-mode]").forEach(mode => mode.classList.toggle("active", mode.dataset.trendMode === selectedMode));
        render();
      } catch (error) {
        root.querySelector("[data-trend-summary]").textContent = "暂时无法读取趋势数据";
        root.querySelector("[data-trend-source]").textContent = error.message || "请确认后端已启动后重试。";
        root.querySelector("[data-trend-grid]").innerHTML = "";
      }
    }
  });
  root.querySelector("[data-edit-detail]").onclick = () => { document.getElementById("modalRoot").innerHTML = ""; openClassForm(item, document.getElementById("app")); };
}
`
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
  const root = showModal(`<div class="modal-head"><div><h2>${existing ? "编辑" : "新建"}班级画像</h2><p>班级整体特征会用于推荐与教案生成；教师教学感受只保存在档案，不发送给模型。请勿填写学生姓名、联系方式或可识别个人的信息。</p></div><button class="close" data-close>×</button></div><form id="classForm" class="form-grid">
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
