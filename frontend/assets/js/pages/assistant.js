import { api } from "../api/client.js";
import { lessonView } from "../components/lesson.js?v=20261007-2";
import { cancelActiveGeneration, getGenerationJob, refreshGeneration, startGeneration } from "../state/generation.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const regions = ["华南地区", "西南地区", "西北地区", "华中地区", "华东地区", "华北地区", "东北地区"];
let selectedSong = null;
let currentPlan = null;
let recommendedSongs = [];

function normalizeText(value) {
  if (Array.isArray(value)) return value.join("\n").replace(/\s+/g, " ").trim();
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value || "").replace(/\s+/g, " ").trim();
}
function adjustmentChanges(before, after) {
  const from = before?.content || before || {};
  const to = after?.content || after || {};
  const changes = [];
  const fields = [
    ["objectives", "教学目标"], ["key_points", "教学重点"], ["difficulties", "教学难点"],
    ["preparation", "课前准备"], ["theory_explanation", "乐理讲解"], ["mistake_practice", "易错点练习"],
    ["differentiation", "分层教学"], ["assessment", "课堂评价"],
  ];
  fields.forEach(([key, label]) => { if (normalizeText(from[key]) !== normalizeText(to[key])) changes.push({ label, detail: "已按本次要求调整" }); });
  const beforeTimeline = from.timeline || [], afterTimeline = to.timeline || [];
  afterTimeline.forEach((stage, index) => {
    const old = beforeTimeline[index] || {};
    if (normalizeText(old.teacher) !== normalizeText(stage.teacher) || normalizeText(old.students) !== normalizeText(stage.students)) {
      changes.push({ label: `课堂流程 · ${stage.stage || `第 ${index + 1} 环节`}`, detail: "教师组织或学生任务已更新" });
    }
  });
  return changes.slice(0, 6);
}

function classOptions(classes, includeGeneral = false) {
  const general = includeGeneral ? '<option value="">通用模式（不指定班级）</option>' : "";
  return general + classes.map(item => `<option value="${item.id}">${esc(item.name)} · ${esc(item.rhythm_level)}</option>`).join("");
}

export async function renderAssistant(container) {
  const classes = await api.classes();
  container.innerHTML = pageHeader("教案助手", "按班级推荐歌曲，或手动选择歌曲生成教案。") + `
    <div class="grid two">
      <div class="grid">
        <section class="card">
          <div class="tabs"><button class="tab active" data-mode="smart">智能推荐</button><button class="tab" data-mode="manual">手动指定</button></div>
          <div id="smartForm" class="form-grid">
            <label>地区歌库<select id="region">${regions.map(region => `<option>${region}</option>`).join("")}</select></label>
            <label>授课班级<select id="classId">${classOptions(classes)}</select></label>
            <label>课时长度<select id="duration"><option value="40">40 分钟</option><option value="45">45 分钟</option><option value="30">30 分钟</option></select></label>
            <label>课堂偏好<select id="activity"><option>互动与分组合作</option><option>唱游与律动</option><option>地方文化体验</option><option>基础演唱训练</option></select></label>
            ${equipmentControls("smart")}
            <label>生成模式<select id="strategy"><option value="fast">快速模式 · 更快生成完整教案</option><option value="deep" selected>深度模式 · 生成时间较长</option></select></label>
            <label class="full">本课要求（选填）<textarea id="requirements" placeholder="填写设备条件、学生基础或课堂重点"></textarea></label>
            <button class="btn primary" id="recommend">从数据库推荐歌曲</button>
          </div>
          <div id="manualForm" class="form-grid hidden">
            <label>歌曲名称<input id="songName" value="茉莉花"></label>
            <label>授课班级<select id="manualClassId">${classOptions(classes, true)}</select></label>
            <label>课时长度<select id="manualDuration"><option value="40">40 分钟</option><option value="45">45 分钟</option></select></label>
            <label>课堂偏好<select id="manualActivity"><option>互动与分组合作</option><option>唱游与律动</option><option>地方文化体验</option></select></label>
            ${equipmentControls("manual")}
            <label>生成模式<select id="manualStrategy"><option value="fast">快速模式 · 更快生成完整教案</option><option value="deep" selected>深度模式 · 生成时间较长</option></select></label>
            <label class="full">本课要求（选填）<textarea id="manualRequirements" placeholder="填写设备条件、学生基础或课堂重点"></textarea></label>
            <button class="btn primary" id="manualGenerate">检索并生成教案</button>
          </div>
          <div id="recommendations"></div>
        </section>
        <div id="lessonArea"></div>
      </div>
      <aside class="side-stack">
        <section class="card"><h3>调整与保存</h3><p class="muted">生成期间可在右下角查看进度，也可以切换到其他页面。</p><label>调整要求<textarea id="adjustment" placeholder="写下希望修改的部分"></textarea></label><button class="btn block" id="adjustPlan" disabled>按要求调整预览</button><button class="btn primary block" id="savePlan" disabled>保存教案</button><button class="btn block" id="printPlan" disabled>打印 / 导出 PDF</button></section>
      </aside>
    </div>`;

  bindEquipmentControls(container);
  container.querySelectorAll("[data-mode]").forEach(button => button.onclick = () => {
    container.querySelectorAll("[data-mode]").forEach(item => item.classList.toggle("active", item === button));
    document.getElementById("smartForm").classList.toggle("hidden", button.dataset.mode !== "smart");
    document.getElementById("manualForm").classList.toggle("hidden", button.dataset.mode !== "manual");
  });

  document.getElementById("recommend").onclick = async () => {
    const regionValue = document.getElementById("region").value;
    const classValue = document.getElementById("classId").value;
    if (!classValue) return notify("智能推荐需要先选择一个班级；通用模式请使用手动指定");
    const list = await api.recommend({ region: regionValue, class_id: Number(classValue), limit: 3 });
    if (!list.length) return notify("当前地区暂无可推荐歌曲，可在资源库新增后再试");
    recommendedSongs = list;
    selectedSong = recommendedSongs[0];
    document.getElementById("recommendations").innerHTML = `<div class="recommendations">${recommendedSongs.map((song, index) => songCard(song, index === 0)).join("")}</div><p class="selection-status" id="selectionStatus">已选择：${esc(selectedSong.name)}</p><button class="btn primary" id="generateSelected">根据所选歌曲生成详细教案</button>`;
    bindSongCards(document.getElementById("recommendations"));
    document.getElementById("generateSelected").onclick = () => generate(false);
  };

  document.getElementById("manualGenerate").onclick = async () => {
    const songs = await api.songs({ q: document.getElementById("songName").value.trim() });
    if (!songs.length) return notify("数据库中没有找到这首歌曲，可先到教学资源库新增");
    selectedSong = songs[0];
    await generate(true);
  };

  document.getElementById("adjustPlan").onclick = async () => {
    const instruction = document.getElementById("adjustment").value.trim();
    if (!instruction) return notify("请填写修改要求");
    await streamPreviewAdjustment(document.getElementById("lessonArea"), instruction);
  };

  document.getElementById("savePlan").onclick = async () => {
    if (!currentPlan || currentPlan.is_saved) return;
    const button = document.getElementById("savePlan");
    button.disabled = true;
    button.textContent = "正在保存…";
    try {
      currentPlan = await api.saveLesson({
        song_id: currentPlan.song_id,
        class_id: currentPlan.class_id,
        duration_minutes: currentPlan.duration_minutes,
        teacher_requirements: currentPlan.content.teacher_requirements || "",
        generation_mode: currentPlan.generation_mode,
        content: currentPlan.content,
      });
      renderPreview(document.getElementById("lessonArea"), false);
      button.textContent = "已保存到教案与课堂记录";
      document.getElementById("adjustPlan").disabled = true;
      notify("教案已保存，现在可在“教案与课堂记录”中查看");
    } catch (error) {
      button.disabled = false;
      button.textContent = "保存教案";
      const prefix = error?.status ? `保存失败（HTTP ${error.status}）：` : "保存教案失败：";
      notify(`${prefix}${error.message || "请检查后端日志后重试"}`, "error");
    }
  };
  document.getElementById("printPlan").onclick = () => window.print();

  window.addEventListener("generation:update", updateFromGenerationEvent);
  const job = await refreshGeneration();
  restoreJob(job);
}

function songCard(song, active) {
  return `<article class="song-card ${active ? "selected" : ""}" data-song-id="${song.id}" tabindex="0" role="button" aria-pressed="${active}"><div><span class="eyebrow">规则适配分 ${song.match_score}/100</span><h3>《${esc(song.name)}》</h3><p>${esc(song.province)} · ${esc(song.grade)} · ${esc(song.mood)} · ${esc(song.difficulty)}</p><small>${esc(song.reason)}</small></div><button type="button" class="btn soft" data-choose-song="${song.id}">${active ? "已选择" : "选择"}</button></article>`;
}

function bindSongCards(root) {
  const choose = id => {
    selectedSong = recommendedSongs.find(song => song.id === Number(id));
    if (!selectedSong) return;
    root.querySelectorAll(".song-card").forEach(card => {
      const active = Number(card.dataset.songId) === selectedSong.id;
      card.classList.toggle("selected", active);
      card.setAttribute("aria-pressed", String(active));
      const button = card.querySelector("[data-choose-song]");
      if (button) button.textContent = active ? "已选择" : "选择";
    });
    const status = root.querySelector("#selectionStatus");
    if (status) status.textContent = `已选择：${selectedSong.name}`;
  };
  root.querySelectorAll(".song-card").forEach(card => {
    card.onclick = event => { if (!event.target.closest("button") || event.target.matches("[data-choose-song]")) choose(card.dataset.songId); };
    card.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(card.dataset.songId); } };
  });
}

function equipmentControls(id) {
  return '<fieldset class="equipment-panel full" data-equipment-controls="' + id + '">' +
    '<legend>课堂可用设备（可多选）</legend><p>只勾选本节确实能用的设备，教案会据此安排播放、投影或无设备替代活动。</p>' +
    '<label class="equipment-preset">快速选择<select data-equipment-preset><option value="custom">自定义设备</option><option value="none">无电子设备</option><option value="phone">手机播放</option><option value="computer">电脑播放</option><option value="computer-speaker">电脑 + 音箱</option><option value="classroom">电脑 + 投影 + 音箱</option></select></label>' +
    '<div class="equipment-options">' +
    '<label class="check-pill"><input type="checkbox" data-equipment="phone"><span>手机 / 平板</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="computer"><span>电脑</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="speaker"><span>外接音箱</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="projector"><span>投影 / 大屏</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="instrument"><span>课堂乐器 / 节奏乐器</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="offline"><span>音频已下载，可离线播放</span></label>' +
    '</div><div class="tag-editor equipment-tag-editor" data-equipment-tag-editor><div class="tag-chip-list" data-tag-list></div><input type="text" data-tag-input placeholder="其他设备或音源，按回车添加"><input type="hidden" data-equipment-custom-tags></div>' +
    '<input type="hidden" data-equipment-summary></fieldset>';
}

function bindTagEditor(editor) {
  const input = editor.querySelector("[data-tag-input]");
  const list = editor.querySelector("[data-tag-list]");
  const hidden = editor.querySelector("[data-equipment-custom-tags], [data-student-difference-custom]");
  let tags = (hidden?.value || "").split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean);
  const render = () => {
    if (hidden) hidden.value = tags.join("、");
    list.innerHTML = tags.map(value => `<span class="custom-tag-chip">${esc(value)}<button type="button" data-remove-tag="${esc(value)}" aria-label="删除标签">×</button></span>`).join("");
    list.querySelectorAll("[data-remove-tag]").forEach(button => button.onclick = () => {
      tags = tags.filter(value => value !== button.dataset.removeTag);
      render();
      editor.dispatchEvent(new CustomEvent("tags:change"));
    });
  };
  const add = raw => {
    for (const value of raw.split(/[、,，;；\n]+/).map(item => item.trim()).filter(Boolean)) {
      if (!tags.includes(value)) tags.push(value);
    }
    input.value = "";
    render();
    editor.dispatchEvent(new CustomEvent("tags:change"));
  };
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === "," || event.key === "，") {
      event.preventDefault();
      add(input.value);
    }
  });
  input.addEventListener("blur", () => { if (input.value.trim()) add(input.value); });
  render();
  return () => [...tags];
}

function bindEquipmentControls(root) {
  const labels = { phone: "手机", computer: "电脑", speaker: "外接音箱", projector: "投影/大屏", instrument: "课堂乐器/节奏乐器", offline: "音频已下载可离线播放" };
  const presets = {
    none: [],
    phone: ["phone", "offline"],
    computer: ["computer", "offline"],
    "computer-speaker": ["computer", "speaker", "offline"],
    classroom: ["computer", "speaker", "projector", "offline"],
  };
  root.querySelectorAll("[data-equipment-controls]").forEach(panel => {
    const boxes = [...panel.querySelectorAll("[data-equipment]")];
    const summary = panel.querySelector("[data-equipment-summary]");
    const preset = panel.querySelector("[data-equipment-preset]");
    const customTags = bindTagEditor(panel.querySelector("[data-equipment-tag-editor]"));
    const syncSummary = () => {
      const selected = boxes.filter(box => box.checked).map(box => labels[box.dataset.equipment]);
      summary.value = [...selected, ...customTags()].join("、") || "无电子设备（教师清唱与身体声势）";
    };
    boxes.forEach(box => box.addEventListener("change", () => {
      preset.value = "custom";
      syncSummary();
    }));
    panel.querySelector("[data-equipment-tag-editor]").addEventListener("tags:change", syncSummary);
    preset.addEventListener("change", () => {
      const chosen = presets[preset.value];
      if (!chosen) return;
      boxes.forEach(box => { box.checked = chosen.includes(box.dataset.equipment); });
      syncSummary();
    });
    syncSummary();
  });
}

async function generate(manual) {
  if (!selectedSong) return notify("请先选择歌曲");
  const classElement = document.getElementById(manual ? "manualClassId" : "classId");
  const durationElement = document.getElementById(manual ? "manualDuration" : "duration");
  const activityElement = document.getElementById(manual ? "manualActivity" : "activity");
  const requirementsElement = document.getElementById(manual ? "manualRequirements" : "requirements");
  const equipmentElement = document.querySelector(`[data-equipment-controls="${manual ? "manual" : "smart"}"] [data-equipment-summary]`);
  const strategyElement = document.getElementById(manual ? "manualStrategy" : "strategy");
  disableActions(true);
  try {
    const job = await startGeneration({
      song_id: selectedSong.id,
      class_id: classElement.value ? Number(classElement.value) : null,
      duration_minutes: Number(durationElement.value),
      activity_preference: activityElement.value,
      teacher_requirements: [requirementsElement.value.trim(), `[课堂设备条件：${equipmentElement.value || "无电子设备（教师清唱与身体声势）"}]`].filter(Boolean).join("\n"),
      generation_strategy: strategyElement.value,
    });
    currentPlan = job.preview;
    renderPreview(document.getElementById("lessonArea"), true, job);
    notify(strategyElement.value === "fast" ? "正在快速生成完整教案" : "正在生成完整教案（深度模式）");
  } catch (error) {
    disableActions(false);
    document.getElementById("lessonArea").innerHTML = `<div class="notice">${esc(error.message)}</div>`;
  }
}

function updateFromGenerationEvent(event) {
  restoreJob(event.detail);
}

function restoreJob(job) {
  const area = document.getElementById("lessonArea");
  if (!area || !job) return;
  if (job.status === "completed" && job.result) {
    currentPlan = job.result;
    renderPreview(area, false, job);
    disableActions(false);
    return;
  }
  if (job.status === "failed") {
    currentPlan = job.preview || null;
    if (currentPlan) renderPreview(area, false, job);
    area.insertAdjacentHTML("afterbegin", `<div class="notice">教案完善未完成：${esc(job.error_message || "请稍后重试")}。下方仍保留规则生成的可用教案骨架。</div>`);
    disableActions(false);
    return;
  }
  if (job.preview) {
    currentPlan = job.preview;
    renderPreview(area, true, job);
    disableActions(true);
  }
}

function disableActions(generating) {
  const adjust = document.getElementById("adjustPlan");
  const save = document.getElementById("savePlan");
  const print = document.getElementById("printPlan");
  if (!adjust || !save || !print) return;
  adjust.disabled = generating || !currentPlan;
  save.disabled = generating || !currentPlan || currentPlan.is_saved;
  print.disabled = !currentPlan;
  save.textContent = currentPlan?.is_saved ? "已保存到教案与课堂记录" : generating ? "完善完成后可保存" : "保存教案";
}

function renderPreview(area, generating = false, job = null) {
  if (!currentPlan) return;
  const status = generating
    ? `<div class="ai-preview-banner"><div><b>正在完善教案</b><span>${esc(job?.stage || "切换页面后任务仍会继续")}</span></div><button class="btn soft" id="cancelGenerationInPage">取消本次生成</button></div><div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(job?.progress || 0)))}%"></i></div>${generationStepView(job)}`
    : "";
  area.innerHTML = `${status}<section class="card lesson-preview-card"><div class="card-head"><div><h3>教案预览</h3><p class="muted">${currentPlan.is_saved ? "已保存到教案与课堂记录" : generating ? "当前显示教案初稿，完善完成后会自动更新" : "未保存：可继续调整，满意后点击右侧“保存教案”"}</p></div></div><div class="lesson-preview-scroll">${lessonView(currentPlan)}</div></section>`;
  area.querySelector("#cancelGenerationInPage")?.addEventListener("click", async () => {
    try { await cancelActiveGeneration(); } catch (error) { notify(error.message); }
  });
}

function generationStepView(job) {
  const steps = job?.steps || [];
  if (!steps.length) return "";
  return `<ol class="job-step-list">${steps.map(item => `<li class="${esc(item.state || "pending")}"><i>${item.state === "done" ? "✓" : item.state === "error" ? "!" : item.state === "running" ? "•" : "○"}</i>${esc(item.label)}</li>`).join("")}</ol>`;
}

async function streamPreviewAdjustment(area, instruction) {
  const metadata = { ...currentPlan };
  document.getElementById("adjustPlan").disabled = true;
  document.getElementById("savePlan").disabled = true;
  try {
    area.innerHTML = `<section class="card lesson-stream-panel"><h3>正在调整教案</h3><p class="muted">正在根据你的要求调整教案。</p><div class="loading">正在根据你的要求调整教案<i></i><i></i><i></i></div></section>`;
    await api.adjustPreviewStream({ content: currentPlan.content, instruction }, event => {
      if (event.type === "complete") {
        const nextPlan = { ...metadata, ...event.preview, is_saved: false };
        currentPlan = { ...nextPlan, adjustment_changes: adjustmentChanges(metadata, nextPlan) };
        renderPreview(area, false);
      }
    });
    disableActions(false);
    notify("已按要求更新预览；“本次调整重点”已标出实际变更内容，尚未保存。");
  } catch (error) {
    currentPlan = metadata;
    renderPreview(area, false);
    disableActions(false);
    notify(error.message);
  }
}
