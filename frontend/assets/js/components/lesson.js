import { esc } from "../utils/dom.js";

function lines(value) {
  return String(value || "").split(/\n+/).map(item => item.trim()).filter(Boolean);
}
function textBlocks(value) {
  const blocks = lines(value);
  return (blocks.length ? blocks : [String(value || "—")]).map(item => `<p>${esc(item)}</p>`).join("");
}
function list(items) { return (items || []).filter(Boolean).map(item => `<li>${esc(item)}</li>`).join("") || "<li>—</li>"; }
function stageCard(item, index) {
  return `<article class="lesson-stage" data-stage data-minutes="${Number(item.minutes) || 0}">
    <div class="lesson-stage-index"><span>${String(index + 1).padStart(2, "0")}</span><b>${esc(item.minutes)} 分钟</b></div>
    <div class="lesson-stage-content"><h4>${esc(item.stage)}</h4><div class="stage-columns">
      <section><span>教师这样组织</span>${textBlocks(item.teacher)}</section>
      <section><span>学生要完成</span>${textBlocks(item.students)}</section>
    </div>
    ${item.device_action ? `<div class="lesson-stage-device"><b>本设备安排</b><p>${esc(item.device_action)}</p></div>` : ""}
    ${item.look_for ? `<div class="lesson-stage-evidence"><b>本段观察</b><p>${esc(item.look_for)}</p></div>` : ""}
    ${item.low_device_option ? `<div class="lesson-stage-alternative"><b>设备不足时</b><p>${esc(item.low_device_option)}</p></div>` : ""}
  </div>
  </article>`;
}

export function lessonView(plan) {
  const content = plan.content || {};
  const summary = content.summary || {};
  const song = content.generation_context?.selected_song_from_database || {};
  const basis = song.design_basis || {};
  const changes = plan.adjustment_changes || [];
  const requirement = String(content.teacher_requirements || plan.teacher_requirements || "").trim();
  const strategy = content.generation_strategy || plan.generation_strategy;
  const strategyLabel = strategy === "fast" ? "快速模式" : strategy === "deep" ? "深度模式" : "历史教案";
  const sourceLabel = content.generation_source === "ai" ? "模型生成" : content.generation_source === "rules" ? "基础生成" : "";
  return `<article class="lesson" id="lessonDocument">
    <header class="lesson-hero"><div><span>课堂设计 · ${esc(strategyLabel)}${sourceLabel ? ` · ${esc(sourceLabel)}` : ""}</span><h2>${esc(content.title || plan.title || "音乐教案")}</h2><p>${esc(summary.class_name || plan.class_name || "通用班级")} · ${esc(summary.duration || plan.duration_minutes || "—")} 分钟 · ${esc(summary.region || "—")}</p><button class="btn soft lesson-start-teaching" type="button" data-teaching-start>进入授课视图</button></div><div class="lesson-hero-badge"><b>${esc(song.mood || "音乐课")}</b><small>${esc(song.song_type || "课堂设计")}</small></div></header>
    <div class="lesson-summary"><div><small>建议音域</small><b>${esc(summary.range_note || song.range_note || "—")}</b></div><div><small>歌曲难度</small><b>${esc(summary.difficulty || song.difficulty || "—")}</b></div><div><small>课堂重点</small><b>${esc(basis.primary || "听唱与表达")}</b></div><div><small>适用班级</small><b>${esc(summary.class_name || plan.class_name || "—")}</b></div></div>
    ${changes.length ? `<section class="lesson-change-summary"><div><span class="eyebrow">THIS REVISION</span><h3>本次调整重点</h3></div><ul>${changes.map(change => `<li><b>${esc(change.label)}</b><span>${esc(change.detail)}</span></li>`).join("")}</ul></section>` : ""}
    ${requirement ? `<section class="lesson-requirement"><span>教师补充要求</span><p>${esc(requirement)}</p></section>` : ""}
    <section class="lesson-focus-grid"><article><span>本课教学抓手</span><b>${esc(content.key_points || "—")}</b></article><article><span>预判与支架</span><b>${esc(content.difficulties || "—")}</b></article></section>
    <section class="lesson-section objective-section"><div class="section-title"><span>01</span><div><h3>教学目标</h3><p>学生在本课结束时可被观察到的表现</p></div></div><ol class="objective-list">${list(content.objectives)}</ol></section>
    ${content.objective_evidence?.length ? `<section class="lesson-objective-evidence"><div class="section-title"><span>✓</span><div><h3>本课观察目标</h3><p>用学生实际表现判断目标进展</p></div></div><div class="objective-evidence-list">${content.objective_evidence.map((item, index) => `<article><b>目标 ${index + 1}</b><p>${esc(item.objective)}</p><small>${esc(item.evidence)}</small></article>`).join("")}</div></section>` : ""}
    <section class="lesson-classroom-setup"><b>课堂设备</b><span>${esc(content.classroom_setup || "电脑与音箱")}</span><small>每个环节均附有设备不足时的替代做法。</small></section>
    <section class="lesson-section"><div class="section-title"><span>02</span><div><h3>课前准备</h3><p>把课堂资源和组织方式提前准备好</p></div></div><p class="body-copy">${esc(content.preparation || "—")}</p></section>
    <section class="lesson-section lesson-flow"><div class="section-title"><span>03</span><div><h3>完整课堂流程</h3><p>每一段都分开呈现教师动作与学生任务</p></div></div><div class="lesson-teaching-controls hidden" data-teaching-controls><button type="button" class="btn soft" data-stage-nav="prev">上一个环节</button><span data-stage-progress>第 1 / 1 环节</span><button type="button" class="btn soft" data-stage-timer>开始本段计时</button><span data-stage-clock aria-live="polite"></span><button type="button" class="btn primary" data-stage-nav="next">下一个环节</button><button type="button" class="link" data-stage-nav="exit">退出授课视图</button></div>${flow}</section>
    <section class="lesson-detail-grid"><article class="lesson-detail-card theory"><span>04 · 乐理大白话</span><h3>${esc(content.theory_explanation?.term || "本课音乐要点")}</h3>${textBlocks(content.theory_explanation?.script)}</article><article class="lesson-detail-card practice"><span>05 · 易错点与纠正</span><h3>${esc(content.mistake_practice?.problem || "需要留意的表现")}</h3><p><b>立刻练习：</b>${esc(content.mistake_practice?.correction || "—")}</p></article></section>
    <section class="lesson-section"><div class="section-title"><span>06</span><div><h3>分层教学</h3><p>让不同基础的学生都有清晰任务</p></div></div><ul class="tier-list">${list(content.differentiation)}</ul></section>
    <section class="lesson-section assessment-section"><div class="section-title"><span>07</span><div><h3>课堂评价</h3><p>以学生的实际表现作为下一课依据</p></div></div>${textBlocks(content.assessment)}</section>
  </article>`;
}


// 授课视图只突出当前环节；普通预览与打印内容保持完整。
if (!window.__lessonTeachingControlsBound) {
  window.__lessonTeachingControlsBound = true;
  let timerId = null;
  let secondsLeft = 0;
  const clearStageTimer = () => {
    if (timerId) window.clearInterval(timerId);
    timerId = null;
    secondsLeft = 0;
    document.querySelectorAll("[data-stage-clock]").forEach(node => { node.textContent = ""; });
    document.querySelectorAll("[data-stage-timer]").forEach(node => { node.textContent = "开始本段计时"; });
  };
  const setStage = (lesson, index) => {
    const stages = [...lesson.querySelectorAll("[data-stage]")];
    if (!stages.length) return;
    const nextIndex = Math.max(0, Math.min(index, stages.length - 1));
    clearStageTimer();
    stages.forEach((stage, i) => { stage.hidden = i !== nextIndex; });
    const controls = lesson.querySelector("[data-teaching-controls]");
    controls?.classList.remove("hidden");
    const progress = lesson.querySelector("[data-stage-progress]");
    if (progress) progress.textContent = `第 ${nextIndex + 1} / ${stages.length} 环节`;
    lesson.dataset.activeStage = String(nextIndex);
    const next = lesson.querySelector('[data-stage-nav="next"]');
    if (next) next.textContent = nextIndex === stages.length - 1 ? "完成授课" : "下一个环节";
  };
  document.addEventListener("click", event => {
    const start = event.target.closest("[data-teaching-start]");
    if (start) {
      const lesson = start.closest(".lesson");
      if (lesson) {
        lesson.classList.add("lesson-teaching-mode");
        setStage(lesson, 0);
      }
      return;
    }
    const nav = event.target.closest("[data-stage-nav]");
    if (nav) {
      const lesson = nav.closest(".lesson");
      if (!lesson) return;
      const stages = lesson.querySelectorAll("[data-stage]");
      const index = Number(lesson.dataset.activeStage || 0);
      if (nav.dataset.stageNav === "exit" || (nav.dataset.stageNav === "next" && index >= stages.length - 1)) {
        lesson.classList.remove("lesson-teaching-mode");
        stages.forEach(stage => { stage.hidden = false; });
        lesson.querySelector("[data-teaching-controls]")?.classList.add("hidden");
        clearStageTimer();
      } else {
        setStage(lesson, index + (nav.dataset.stageNav === "next" ? 1 : -1));
      }
      return;
    }
    const timer = event.target.closest("[data-stage-timer]");
    if (timer) {
      const lesson = timer.closest(".lesson");
      const stage = lesson?.querySelector("[data-stage]:not([hidden])");
      if (!stage) return;
      if (timerId) { clearStageTimer(); return; }
      secondsLeft = Math.max(1, Number(stage.dataset.minutes || 1)) * 60;
      const clock = lesson.querySelector("[data-stage-clock]");
      const tick = () => {
        if (clock) clock.textContent = `剩余 ${String(Math.floor(secondsLeft / 60)).padStart(2, "0")}:${String(secondsLeft % 60).padStart(2, "0")}`;
        if (secondsLeft <= 0) {
          clearStageTimer();
          if (clock) clock.textContent = "本段时间到";
          return;
        }
        secondsLeft -= 1;
      };
      timer.textContent = "暂停计时";
      tick();
      timerId = window.setInterval(tick, 1000);
    }
  });
}
