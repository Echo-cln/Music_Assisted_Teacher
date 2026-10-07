import { api } from "../api/client.js?v=20261007-5";
import { esc, notify } from "../utils/dom.js";

function lines(value) {
  return String(value || "").split(/\n+/).map(item => item.trim()).filter(Boolean);
}
function textBlocks(value) {
  const blocks = lines(value);
  return (blocks.length ? blocks : [String(value || "—")]).map(item => `<p>${esc(item)}</p>`).join("");
}
function list(items) { return (items || []).filter(Boolean).map(item => `<li>${esc(item)}</li>`).join("") || "<li>—</li>"; }

function stageCard(item, index) {
  return `<article class="lesson-stage" data-stage data-stage-index="${index}" data-minutes="${Number(item.minutes) || 0}">
    <div class="lesson-stage-index"><span>${String(index + 1).padStart(2, "0")}</span><b>${esc(item.minutes)} 分钟</b></div>
    <div class="lesson-stage-content"><h4>${esc(item.stage)}</h4><div class="stage-columns">
      <section><span>教师这样组织</span>${textBlocks(item.teacher)}</section>
      <section><span>学生要完成</span>${textBlocks(item.students)}</section>
    </div>
    ${item.device_action ? `<div class="lesson-stage-device"><b>本设备安排</b><p>${esc(item.device_action)}</p></div>` : ""}
    ${item.look_for ? `<div class="lesson-stage-evidence"><b>本段观察</b><p>${esc(item.look_for)}</p></div>` : ""}
    ${item.low_device_option ? `<div class="lesson-stage-alternative"><b>设备不足时</b><p>${esc(item.low_device_option)}</p></div>` : ""}
    <div class="lesson-run-note" data-run-note-panel hidden><label>本段随堂批注<textarea data-run-note data-stage-index="${index}" maxlength="3000" placeholder="记录学生反应、现场调整、设备情况或时间变化"></textarea></label><small data-note-status>自动保存</small></div>
  </div></article>`;
}

function revisionPreview(content = {}) {
  const timeline = Array.isArray(content.timeline) ? content.timeline : [];
  return `<article class="lesson-revision-preview"><h3>${esc(content.title || "教案旧版本")}</h3><p>${esc(content.summary?.class_name || "通用班级")} · ${esc(content.summary?.duration || "—")}</p><h4>教学目标</h4><ul>${list(content.objectives)}</ul><h4>课堂流程</h4><ol>${timeline.map(item => `<li><b>${esc(item.stage || "教学环节")} · ${esc(item.minutes || "—")} 分钟</b><p>教师：${esc(item.teacher || "—")}</p><p>学生：${esc(item.students || "—")}</p></li>`).join("") || "<li>暂无流程</li>"}</ol></article>`;
}

export function lessonView(plan, { interactive = true } = {}) {
  const content = plan.content || {};
  const summary = content.summary || {};
  const song = content.generation_context?.selected_song_from_database || {};
  const basis = song.design_basis || {};
  const changes = plan.adjustment_changes || [];
  const requirement = String(content.teacher_requirements || plan.teacher_requirements || "").trim();
  const strategy = content.generation_strategy || plan.generation_strategy;
  const strategyLabel = strategy === "fast" ? "快速模式" : strategy === "deep" ? "深度模式" : "历史教案";
  const sourceLabel = content.generation_source === "ai" ? "模型生成" : content.generation_source === "rules" ? "基础生成" : "";
  const flow = (Array.isArray(content.timeline) ? content.timeline : []).map((item, index) => stageCard(item || {}, index)).join("") || '<p class="muted lesson-flow-empty">这份教案还没有课堂流程。</p>';
  const actions = interactive ? `<div class="lesson-hero-actions"><button class="btn primary lesson-start-teaching" type="button" data-teaching-start>进入授课视图</button><button class="btn soft" type="button" data-run-history-toggle>授课记录与版本</button></div><div class="lesson-run-launch" data-run-launch hidden><div><b>开始一条授课记录</b><small>选择记录类型；每段时间与课中批注会自动保存。</small></div><button class="btn soft" type="button" data-run-mode="actual">实际授课</button><button class="btn soft" type="button" data-run-mode="simulation">模拟演练</button><button class="link" type="button" data-run-cancel>取消</button></div><section class="lesson-run-history" data-run-history hidden><div class="run-history-head"><b>授课记录</b><button class="link" type="button" data-run-history-close>收起</button></div><div data-run-history-list><p class="muted">正在读取记录…</p></div><div data-run-revision-list></div><div data-run-history-preview></div></section>` : "";
  return `<article class="lesson" id="lessonDocument" data-plan-id="${Number(plan.id) || ""}">
    <header class="lesson-hero"><div><span>课堂设计 · ${esc(strategyLabel)}${sourceLabel ? ` · ${esc(sourceLabel)}` : ""}</span><h2>${esc(content.title || plan.title || "音乐教案")}</h2><p>${esc(summary.class_name || plan.class_name || "通用班级")} · ${esc(summary.duration || plan.duration_minutes || "—")} 分钟 · ${esc(summary.region || "—")}</p>${actions}</div><div class="lesson-hero-badge"><b>${esc(song.mood || "音乐课")}</b><small>${esc(song.song_type || "课堂设计")}</small></div></header>
    <div class="lesson-summary"><div><small>建议音域</small><b>${esc(summary.range_note || song.range_note || "—")}</b></div><div><small>歌曲难度</small><b>${esc(summary.difficulty || song.difficulty || "—")}</b></div><div><small>课堂重点</small><b>${esc(basis.primary || "听唱与表达")}</b></div><div><small>适用班级</small><b>${esc(summary.class_name || plan.class_name || "—")}</b></div></div>
    ${changes.length ? `<section class="lesson-change-summary"><div><span class="eyebrow">THIS REVISION</span><h3>本次调整重点</h3></div><ul>${changes.map(change => `<li><b>${esc(change.label)}</b><span>${esc(change.detail)}</span></li>`).join("")}</ul></section>` : ""}
    ${requirement ? `<section class="lesson-requirement"><span>教师补充要求</span><p>${esc(requirement)}</p></section>` : ""}
    <section class="lesson-focus-grid"><article><span>本课教学抓手</span><b>${esc(content.key_points || "—")}</b></article><article><span>预判与支架</span><b>${esc(content.difficulties || "—")}</b></article></section>
    <section class="lesson-section objective-section"><div class="section-title"><span>01</span><div><h3>教学目标</h3><p>学生在本课结束时可被观察到的表现</p></div></div><ol class="objective-list">${list(content.objectives)}</ol></section>
    ${content.objective_evidence?.length ? `<section class="lesson-objective-evidence"><div class="section-title"><span>✓</span><div><h3>本课观察目标</h3><p>用学生实际表现判断目标进展</p></div></div><div class="objective-evidence-list">${content.objective_evidence.map((item, index) => `<article><b>目标 ${index + 1}</b><p>${esc(item.objective)}</p><small>${esc(item.evidence)}</small></article>`).join("")}</div></section>` : ""}
    <section class="lesson-classroom-setup"><b>课堂设备</b><span>${esc(content.classroom_setup || "电脑与音箱")}</span><small>每个环节均附有设备不足时的替代做法。</small></section>
    <section class="lesson-section"><div class="section-title"><span>02</span><div><h3>课前准备</h3><p>把课堂资源和组织方式提前准备好</p></div></div><p class="body-copy">${esc(content.preparation || "—")}</p></section>
    <section class="lesson-section lesson-flow"><div class="section-title"><span>03</span><div><h3>课堂流程</h3><p>环节时间、课堂观察和临场批注集中在这里</p></div></div>
      <div class="lesson-teaching-controls hidden" data-teaching-controls>
        <div class="lesson-run-live-meta"><span data-run-mode-label></span><span data-stage-progress>第 1 / 1 环节</span><span data-run-plan-time></span></div>
        <div class="lesson-run-live-clock"><span>本段有效授课</span><b data-stage-clock>00:00</b><small data-run-totals>本次有效 00:00 · 暂停 00:00</small></div>
        <div class="lesson-run-buttons"><button type="button" class="btn soft" data-run-action="previous">上一个环节</button><button type="button" class="btn soft" data-run-action="pause">暂停计时</button><button type="button" class="btn soft" data-run-action="resume" hidden>继续计时</button><button type="button" class="btn primary" data-run-action="next">下一个环节</button><button type="button" class="btn soft" data-run-action="finish">结束并复盘</button><button type="button" class="link" data-run-action="collapse">暂停并返回教案</button></div>
        <p class="lesson-run-interrupted" data-run-interrupted hidden>上次页面中断后的时间未计入。继续后从现在开始计时。</p>
      </div>
      ${flow}
      <section class="lesson-run-recap" data-run-recap hidden></section>
      <section class="lesson-run-revision" data-run-revision hidden></section>
    </section>
    <section class="lesson-detail-grid"><article class="lesson-detail-card theory"><span>04 · 乐理大白话</span><h3>${esc(content.theory_explanation?.term || "本课音乐要点")}</h3>${textBlocks(content.theory_explanation?.script)}</article><article class="lesson-detail-card practice"><span>05 · 易错点与纠正</span><h3>${esc(content.mistake_practice?.problem || "需要留意的表现")}</h3><p><b>立刻练习：</b>${esc(content.mistake_practice?.correction || "—")}</p></article></section>
    <section class="lesson-section"><div class="section-title"><span>06</span><div><h3>分层教学</h3><p>让不同基础的学生都有清晰任务</p></div></div><ul class="tier-list">${list(content.differentiation)}</ul></section>
    <section class="lesson-section assessment-section"><div class="section-title"><span>07</span><div><h3>课堂评价</h3><p>以学生的实际表现作为下一课依据</p></div></div>${textBlocks(content.assessment)}</section>
  </article>`;
}

const modeNames = { actual: "实际授课", simulation: "模拟演练" };
const formatTime = value => {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
};
let currentRuntime = null;
let clockTimer = null;
let heartbeatTimer = null;
const noteTimers = new Map();
let reflectionTimer = null;

function clearRunTimers() {
  if (clockTimer) clearInterval(clockTimer);
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  clockTimer = heartbeatTimer = null;
}
function runDelta(run) {
  if (run.status !== "running" || !run.snapshot_at) return 0;
  return Math.max(0, Math.floor((Date.now() - Date.parse(run.snapshot_at)) / 1000));
}
function paintRunClock() {
  if (!currentRuntime) return;
  const { lesson, run } = currentRuntime;
  if (!document.contains(lesson)) { clearRunTimers(); currentRuntime = null; return; }
  const delta = runDelta(run);
  const status = run.status;
  const stageSeconds = (Number(run.current_stage_seconds) || 0) + delta;
  const total = (Number(run.total_active_seconds) || 0) + delta;
  const pausedDelta = status === "paused" && run.paused_since ? Math.max(0, Math.floor((Date.now() - Date.parse(run.paused_since)) / 1000)) : 0;
  const paused = (Number(run.total_paused_seconds) || 0) + pausedDelta;
  const clock = lesson.querySelector("[data-stage-clock]");
  const totals = lesson.querySelector("[data-run-totals]");
  if (clock) clock.textContent = formatTime(stageSeconds);
  if (totals) totals.textContent = `本次有效 ${formatTime(total)} · 暂停 ${formatTime(paused)}`;
}
function renderRun(lesson, run) {
  currentRuntime = { lesson, run };
  lesson.dataset.runId = String(run.id);
  lesson.classList.add("lesson-teaching-mode");
  lesson.querySelector("[data-run-launch]")?.setAttribute("hidden", "");
  lesson.querySelector("[data-teaching-controls]")?.classList.remove("hidden");
  lesson.querySelectorAll("[data-stage]").forEach((stage, index) => {
    stage.hidden = index !== run.current_stage_index;
    const notePanel = stage.querySelector("[data-run-note-panel]");
    if (notePanel) notePanel.hidden = run.status === "completed";
    const note = stage.querySelector("[data-run-note]");
    if (note) note.value = run.stages[index]?.note || "";
  });
  const stage = run.stages[run.current_stage_index] || {};
  const progress = lesson.querySelector("[data-stage-progress]");
  if (progress) progress.textContent = `第 ${Math.min(run.current_stage_index + 1, run.stages.length)} / ${run.stages.length} 环节`;
  lesson.querySelector("[data-run-mode-label]").textContent = `${modeNames[run.mode] || "授课记录"} · ${run.status === "paused" ? "已暂停" : run.status === "interrupted" ? "待恢复" : run.status === "completed" ? "已结束" : "计时中"}`;
  lesson.querySelector("[data-run-plan-time]").textContent = `本段计划 ${formatTime(stage.planned_seconds)}`;
  lesson.querySelector('[data-run-action="pause"]').hidden = run.status !== "running";
  lesson.querySelector('[data-run-action="resume"]').hidden = !["paused", "interrupted"].includes(run.status);
  lesson.querySelector('[data-run-action="next"]').hidden = run.status !== "running";
  lesson.querySelector('[data-run-action="previous"]').hidden = run.status !== "running";
  lesson.querySelector('[data-run-action="finish"]').hidden = run.status === "completed";
  lesson.querySelector('[data-run-action="collapse"]').hidden = run.status === "completed";
  lesson.querySelector("[data-run-interrupted]").hidden = run.status !== "interrupted";
  const recap = lesson.querySelector("[data-run-recap]");
  const revision = lesson.querySelector("[data-run-revision]");
  if (run.status === "completed") {
    lesson.querySelector("[data-teaching-controls]")?.classList.add("hidden");
    recap.hidden = false;
    revision.hidden = true;
    recap.innerHTML = recapMarkup(run);
  } else {
    recap.hidden = true;
  }
  paintRunClock();
  clearRunTimers();
  if (run.status === "running" || run.status === "paused") {
    clockTimer = setInterval(paintRunClock, 1000);
    if (run.status === "running") heartbeatTimer = setInterval(() => sendRunEvent(lesson, "heartbeat", {}, false), 15000);
  }
}
function recapMarkup(run) {
  const modeLabel = modeNames[run.mode] || "授课";
  const rows = (run.stages || []).map((stage, index) => {
    const difference = Number(stage.active_seconds || 0) - Number(stage.planned_seconds || 0);
    const delta = difference === 0 ? "与计划相同" : `比计划${difference > 0 ? "多" : "少"} ${formatTime(Math.abs(difference))}`;
    return `<article class="run-recap-stage"><div><span>环节 ${index + 1}</span><b>${esc(stage.stage)}</b></div><small>计划 ${formatTime(stage.planned_seconds)} · 实际 ${formatTime(stage.active_seconds)} · ${delta}</small><p>${esc(stage.note || "本段未添加批注")}</p></article>`;
  }).join("");
  const snapshot = run.snapshot || {};
  const content = snapshot.content || {};
  return `<div class="run-recap-heading"><span class="eyebrow">LESSON REVIEW</span><h3>${esc(modeLabel)}复盘</h3><p>总有效授课 ${formatTime(run.total_active_seconds)} · 暂停 ${formatTime(run.total_paused_seconds)}${run.ended_at ? ` · ${esc(run.ended_at.slice(0, 16).replace("T", " "))}` : ""}</p></div><div class="run-recap-stages">${rows}</div><label class="run-reflection-field">整体复盘<textarea data-run-reflection maxlength="5000" placeholder="哪些环节顺利？哪些内容需要调整？">${esc(run.reflection || "")}</textarea><small data-reflection-status>自动保存</small></label><details class="run-plan-snapshot"><summary>查看本次授课所用教案快照</summary>${revisionPreview(content)}</details><div class="run-recap-actions"><button class="btn primary" type="button" data-run-open-revision>根据批注修订教案</button><button class="btn soft" type="button" data-run-action="close-recap">返回教案</button></div>`;
}
function revisionForm(run) {
  const content = run.snapshot?.content || {};
  const timeline = content.timeline || [];
  const notes = run.stages || [];
  return `<div class="run-revision-heading"><span class="eyebrow">NEXT LESSON VERSION</span><h3>根据本次授课修订教案</h3><p>修改会保存为新版本；本次使用的旧教案快照仍保留在授课记录中。</p></div><label>整体调整说明<textarea data-revision-overall maxlength="3000" placeholder="例如：缩短示范时间，把小组汇报多留两分钟"></textarea></label><div class="run-revision-stages">${timeline.map((stage, index) => `<article><header><b>${esc(stage.stage || `环节 ${index + 1}`)}</b><small>本次批注：${esc(notes[index]?.note || "未填写")}</small></header><label>教师活动<textarea data-revision-teacher="${index}">${esc(stage.teacher || "")}</textarea></label><label>学生活动<textarea data-revision-student="${index}">${esc(stage.students || "")}</textarea></label></article>`).join("")}</div><div class="run-recap-actions"><button class="btn primary" type="button" data-run-save-revision>保存为新版教案</button><button class="btn soft" type="button" data-run-cancel-revision>返回复盘</button></div>`;
}
async function sendRunEvent(lesson, action, extra = {}, repaint = true) {
  const run = currentRuntime?.lesson === lesson ? currentRuntime.run : null;
  if (!run) return;
  const result = await api.lessonRunEvent(run.id, { action, ...extra });
  if (currentRuntime?.lesson === lesson) currentRuntime.run = result;
  if (repaint) renderRun(lesson, result);
  else paintRunClock();
  return result;
}
async function loadRunHistory(lesson) {
  const runPanel = lesson.querySelector("[data-run-history]");
  const listNode = lesson.querySelector("[data-run-history-list]");
  const revisionNode = lesson.querySelector("[data-run-revision-list]");
  runPanel.hidden = false;
  listNode.innerHTML = '<p class="muted">正在读取记录…</p>';
  try {
    const [runs, revisions] = await Promise.all([
      api.lessonRuns(Number(lesson.dataset.planId)),
      api.lessonRevisions(Number(lesson.dataset.planId)),
    ]);
    lesson.__runs = runs;
    lesson.__revisions = revisions;
    listNode.innerHTML = runs.length ? runs.map(run => `<article class="run-history-row"><div><b>${esc(modeNames[run.mode] || "授课")}${run.status === "completed" ? "" : ` · ${esc(run.status === "paused" ? "已暂停" : run.status === "interrupted" ? "待恢复" : "进行中")}`}</b><small>${esc((run.started_at || "").slice(0, 16).replace("T", " "))} · 有效 ${formatTime(run.total_active_seconds)}</small></div><button class="btn soft" type="button" data-run-history-open="${run.id}">${run.status === "completed" ? "查看复盘" : "恢复记录"}</button></article>`).join("") : '<p class="muted">还没有授课记录。</p>';
    revisionNode.innerHTML = revisions.length ? `<h4>教案历史版本</h4>${revisions.map(revision => `<details class="run-revision-history"><summary>第 ${revision.revision_number} 版 · ${esc((revision.created_at || "").slice(0, 16).replace("T", " "))} · ${esc(revision.content?.title || "教案")}</summary>${revisionPreview(revision.content)}</details>`).join("")}` : "";
  } catch (error) {
    listNode.innerHTML = `<p class="error-text">授课记录读取失败：${esc(error.message)}</p>`;
  }
}
async async function beginRun(lesson, mode = null) {
  const panel = lesson.querySelector("[data-run-launch]");
  if (mode == null) {
    const runs = await api.lessonRuns(Number(lesson.dataset.planId));
    const active = runs.find(item => ["running", "paused", "interrupted"].includes(item.status));
    if (active) {
      panel.innerHTML = `<div><b>发现未结束的授课记录</b><small>${esc(modeNames[active.mode])} · ${esc(active.status === "running" ? "计时中" : active.status === "paused" ? "已暂停" : "上次中断")} · 有效 ${formatTime(active.total_active_seconds)}</small></div><button class="btn primary" type="button" data-run-resume-existing="${active.id}">接续这次记录</button><button class="btn soft" type="button" data-run-finish-existing="${active.id}">结束并复盘</button><button class="link" type="button" data-run-cancel>取消</button>`;
      lesson.__activeRun = active;
    } else {
      panel.innerHTML = `<div><b>开始一条授课记录</b><small>选择记录类型；每段时间与课中批注会自动保存。</small></div><button class="btn soft" type="button" data-run-mode="actual">实际授课</button><button class="btn soft" type="button" data-run-mode="simulation">模拟演练</button><button class="link" type="button" data-run-cancel>取消</button>`;
    }
    panel.hidden = false;
    return;
  }
  const run = await api.startLessonRun(Number(lesson.dataset.planId), mode);
  renderRun(lesson, run);
}
function renderRevisionForm(lesson, run) {
  const target = lesson.querySelector("[data-run-revision]");
  target.innerHTML = revisionForm(run);
  target.hidden = false;
  lesson.querySelector("[data-run-recap]").hidden = true;
}
function saveRunRevision(lesson) {
  const run = currentRuntime?.lesson === lesson ? currentRuntime.run : lesson.__activeRun;
  if (!run) return;
  const content = structuredClone(run.snapshot.content || {});
  const timeline = content.timeline || [];
  timeline.forEach((stage, index) => {
    const teacher = lesson.querySelector(`[data-revision-teacher="${index}"]`);
    const students = lesson.querySelector(`[data-revision-student="${index}"]`);
    if (teacher) stage.teacher = teacher.value.trim();
    if (students) stage.students = students.value.trim();
  });
  content.timeline = timeline;
  const overall = lesson.querySelector("[data-revision-overall]")?.value.trim();
  if (overall) {
    const history = Array.isArray(content.teaching_revision_notes) ? content.teaching_revision_notes : [];
    content.teaching_revision_notes = [...history, { run_id: run.id, note: overall, created_at: new Date().toISOString() }];
  }
  return api.reviseLessonFromRun(run.id, content);
}

if (!window.__lessonTeachingControlsBound) {
  window.__lessonTeachingControlsBound = true;
  document.addEventListener("click", async event => {
    const start = event.target.closest("[data-teaching-start]");
    if (start) {
      const lesson = start.closest(".lesson");
      if (lesson) await beginRun(lesson);
      return;
    }
    const mode = event.target.closest("[data-run-mode]");
    if (mode) {
      const lesson = mode.closest(".lesson");
      if (!lesson) return;
      mode.disabled = true;
      try { await beginRun(lesson, mode.dataset.runMode); }
      catch (error) { notify(`无法开始授课记录：${error.message}`, "error"); mode.disabled = false; }
      return;
    }
    const history = event.target.closest("[data-run-history-toggle]");
    if (history) { await loadRunHistory(history.closest(".lesson")); return; }
    if (event.target.closest("[data-run-history-close]")) {
      event.target.closest(".lesson").querySelector("[data-run-history]").hidden = true;
      return;
    }
    const historyOpen = event.target.closest("[data-run-history-open]");
    if (historyOpen) {
      const lesson = historyOpen.closest(".lesson");
      const run = lesson.__runs?.find(item => item.id === Number(historyOpen.dataset.runHistoryOpen));
      if (run) renderRun(lesson, run);
      return;
    }
    const resumeExisting = event.target.closest("[data-run-resume-existing]");
    if (resumeExisting) {
      const lesson = resumeExisting.closest(".lesson");
      let run = lesson.__activeRun;
      if (run.status !== "running") run = await api.lessonRunEvent(run.id, { action: "resume" });
      renderRun(lesson, run);
      return;
    }
    const finishExisting = event.target.closest("[data-run-finish-existing]");
    if (finishExisting) {
      const lesson = finishExisting.closest(".lesson");
      const run = await api.lessonRunEvent(Number(finishExisting.dataset.runFinishExisting), { action: "finish" });
      renderRun(lesson, run);
      return;
    }
    if (event.target.closest("[data-run-cancel]")) {
      event.target.closest(".lesson").querySelector("[data-run-launch]").hidden = true;
      return;
    }
    const actionButton = event.target.closest("[data-run-action]");
    if (actionButton) {
      const lesson = actionButton.closest(".lesson");
      const action = actionButton.dataset.runAction;
      if (action === "collapse") {
        if (currentRuntime?.run?.status === "running") await sendRunEvent(lesson, "pause");
        lesson.classList.remove("lesson-teaching-mode");
        return;
      }
      if (action === "close-recap") {
        lesson.classList.remove("lesson-teaching-mode");
        return;
      }
      actionButton.disabled = true;
      try { await sendRunEvent(lesson, action); }
      catch (error) { notify(`授课记录未更新：${error.message}`, "error"); }
      finally { actionButton.disabled = false; }
      return;
    }
    if (event.target.closest("[data-run-open-revision]")) {
      const lesson = event.target.closest(".lesson");
      if (currentRuntime?.lesson === lesson) renderRevisionForm(lesson, currentRuntime.run);
      return;
    }
    if (event.target.closest("[data-run-cancel-revision]")) {
      const lesson = event.target.closest(".lesson");
      lesson.querySelector("[data-run-revision]").hidden = true;
      lesson.querySelector("[data-run-recap]").hidden = false;
      return;
    }
    if (event.target.closest("[data-run-save-revision]")) {
      const lesson = event.target.closest(".lesson");
      const button = event.target.closest("[data-run-save-revision]");
      button.disabled = true;
      try {
        const result = await saveRunRevision(lesson);
        notify(`教案已保存为第 ${result.revision_number + 1} 版；旧版仍保留。`);
        const updated = result.plan;
        const replacement = document.createElement("div");
        replacement.innerHTML = lessonView(updated);
        lesson.replaceWith(replacement.firstElementChild);
      } catch (error) {
        notify(`教案修订保存失败：${error.message}`, "error");
        button.disabled = false;
      }
      return;
    }
  });

  document.addEventListener("input", event => {
    const note = event.target.closest("[data-run-note]");
    if (note) {
      const lesson = note.closest(".lesson");
      const stageIndex = Number(note.dataset.stageIndex);
      const status = note.parentElement.querySelector("[data-note-status]");
      if (status) status.textContent = "正在保存…";
      clearTimeout(noteTimers.get(stageIndex));
      noteTimers.set(stageIndex, setTimeout(async () => {
        try {
          await sendRunEvent(lesson, "note", { stage_index: stageIndex, note: note.value }, false);
          if (status) status.textContent = "已保存";
        } catch (error) {
          if (status) status.textContent = `保存失败：${error.message}`;
        }
      }, 650));
      return;
    }
    const reflection = event.target.closest("[data-run-reflection]");
    if (reflection) {
      const lesson = reflection.closest(".lesson");
      const status = reflection.parentElement.querySelector("[data-reflection-status]");
      if (status) status.textContent = "正在保存…";
      clearTimeout(reflectionTimer);
      reflectionTimer = setTimeout(async () => {
        try {
          await sendRunEvent(lesson, "reflection", { reflection: reflection.value }, false);
          if (status) status.textContent = "已保存";
        } catch (error) {
          if (status) status.textContent = `保存失败：${error.message}`;
        }
      }, 650);
    }
  });

  document.addEventListener("click", async event => {
    const close = event.target.closest(".modal [data-close]");
    const lesson = close?.closest(".lesson");
    if (!lesson || currentRuntime?.lesson !== lesson || !["running", "paused", "interrupted"].includes(currentRuntime.run.status)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      if (currentRuntime.run.status === "running") await sendRunEvent(lesson, "pause", {}, false);
      clearRunTimers();
      currentRuntime = null;
      document.getElementById("modalRoot").innerHTML = "";
    } catch (error) {
      notify(`授课计时未能暂停，页面暂不关闭：${error.message}`, "error");
    }
  }, true);

  window.addEventListener("app:navigate", async () => {
    if (currentRuntime?.run.status === "running" && document.contains(currentRuntime.lesson)) {
      try { await sendRunEvent(currentRuntime.lesson, "pause", {}, false); }
      catch (error) { notify(`授课计时未能暂停：${error.message}`, "error"); }
      clearRunTimers();
    }
  });
}
