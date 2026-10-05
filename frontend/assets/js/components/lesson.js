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
  return `<article class="lesson-stage">
    <div class="lesson-stage-index"><span>${String(index + 1).padStart(2, "0")}</span><b>${esc(item.minutes)} 分钟</b></div>
    <div class="lesson-stage-content"><h4>${esc(item.stage)}</h4><div class="stage-columns">
      <section><span>教师这样组织</span>${textBlocks(item.teacher)}</section>
      <section><span>学生要完成</span>${textBlocks(item.students)}</section>
    </div></div>
  </article>`;
}

export function lessonView(plan) {
  const content = plan.content || {};
  const summary = content.summary || {};
  const song = content.generation_context?.selected_song_from_database || {};
  const basis = song.design_basis || {};
  const changes = plan.adjustment_changes || [];
  const requirement = String(content.teacher_requirements || plan.teacher_requirements || "").trim();
  return `<article class="lesson" id="lessonDocument">
    <header class="lesson-hero"><div><span>${plan.generation_mode === "ai" ? "已由模型完整生成" : "规则生成"}</span><h2>${esc(content.title || plan.title || "音乐教案")}</h2><p>${esc(summary.class_name || plan.class_name || "通用班级")} · ${esc(summary.duration || plan.duration_minutes || "—")} 分钟 · ${esc(summary.region || "—")}</p></div><div class="lesson-hero-badge"><b>${esc(song.mood || "音乐课")}</b><small>${esc(song.song_type || "课堂设计")}</small></div></header>
    <div class="lesson-summary"><div><small>建议音域</small><b>${esc(summary.range_note || song.range_note || "—")}</b></div><div><small>歌曲难度</small><b>${esc(summary.difficulty || song.difficulty || "—")}</b></div><div><small>课堂重点</small><b>${esc(basis.primary || "听唱与表达")}</b></div><div><small>适用班级</small><b>${esc(summary.class_name || plan.class_name || "—")}</b></div></div>
    ${changes.length ? `<section class="lesson-change-summary"><div><span class="eyebrow">THIS REVISION</span><h3>本次调整重点</h3></div><ul>${changes.map(change => `<li><b>${esc(change.label)}</b><span>${esc(change.detail)}</span></li>`).join("")}</ul></section>` : ""}
    ${requirement ? `<section class="lesson-requirement"><span>教师补充要求</span><p>${esc(requirement)}</p></section>` : ""}
    <section class="lesson-focus-grid"><article><span>本课教学抓手</span><b>${esc(content.key_points || "—")}</b></article><article><span>预判与支架</span><b>${esc(content.difficulties || "—")}</b></article></section>
    <section class="lesson-section objective-section"><div class="section-title"><span>01</span><div><h3>教学目标</h3><p>学生在本课结束时可被观察到的表现</p></div></div><ol class="objective-list">${list(content.objectives)}</ol></section>
    <section class="lesson-section"><div class="section-title"><span>02</span><div><h3>课前准备</h3><p>把课堂资源和组织方式提前准备好</p></div></div><p class="body-copy">${esc(content.preparation || "—")}</p></section>
    <section class="lesson-section lesson-flow"><div class="section-title"><span>03</span><div><h3>完整课堂流程</h3><p>每一段都分开呈现教师动作与学生任务</p></div></div><div class="timeline">${(content.timeline || []).map(stageCard).join("")}</div></section>
    <section class="lesson-detail-grid"><article class="lesson-detail-card theory"><span>04 · 乐理大白话</span><h3>${esc(content.theory_explanation?.term || "本课音乐要点")}</h3>${textBlocks(content.theory_explanation?.script)}</article><article class="lesson-detail-card practice"><span>05 · 易错点与纠正</span><h3>${esc(content.mistake_practice?.problem || "需要留意的表现")}</h3><p><b>立刻练习：</b>${esc(content.mistake_practice?.correction || "—")}</p></article></section>
    <section class="lesson-section"><div class="section-title"><span>06</span><div><h3>分层教学</h3><p>让不同基础的学生都有清晰任务</p></div></div><ul class="tier-list">${list(content.differentiation)}</ul></section>
    <section class="lesson-section assessment-section"><div class="section-title"><span>07</span><div><h3>课堂评价</h3><p>以学生的实际表现作为下一课依据</p></div></div>${textBlocks(content.assessment)}</section>
  </article>`;
}
