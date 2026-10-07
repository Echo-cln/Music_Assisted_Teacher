import { api, apiUrl } from "../api/client.js";
import { lessonView } from "../components/lesson.js";
import { showModal } from "../components/modal.js";
import { esc, notify, pageHeader } from "../utils/dom.js";
import { exportLessonPdf, exportLessonWord } from "../utils/lesson-export.js";

export async function renderLessons(container) {
  container.innerHTML = pageHeader("教学档案与课堂记录", "统一保存、检索和回看教案、课堂音频分析与课后反馈。", '<button class="btn primary" data-route="assistant">新建教案</button>') + `
    <nav class="archive-tabs"><button class="active" data-archive="lessons">教学档案</button><button data-archive="audio">音频分析记录</button><button data-archive="feedback">课堂反馈记录</button></nav>
    <div id="archiveContent"></div>`;
  container.querySelectorAll("[data-archive]").forEach(button => button.onclick = () => openArchive(button.dataset.archive));
  await openArchive("lessons");

  async function openArchive(kind) {
    container.querySelectorAll("[data-archive]").forEach(button => button.classList.toggle("active", button.dataset.archive === kind));
    const archive = document.getElementById("archiveContent");
    if (kind !== "lessons") return renderArchive(archive, kind);
    archive.innerHTML = `
      <section class="list-search"><label class="search-field"><span>⌕</span><input id="lessonSearch" type="search" placeholder="搜索教案标题、歌曲名称或班级"></label><div class="list-filters"><select id="lessonSort"><option value="newest">最新创建</option><option value="oldest">最早创建</option><option value="title">教案标题</option></select></div><small id="lessonSearchCount"></small></section>
      <section class="card table-wrap"><table><thead><tr><th>教案</th><th>班级</th><th>时长</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody id="lessonRows"></tbody></table></section>`;
    let searchTimer;
    document.getElementById("lessonSearch").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadLessons, 220); };
    document.getElementById("lessonSort").onchange = loadLessons;
    await loadLessons();
  }

  async function loadLessons() {
    const q = document.getElementById("lessonSearch").value.trim();
    const plans = await api.lessons(q);
    const sort = document.getElementById("lessonSort").value;
    if (sort === "oldest") plans.reverse();
    if (sort === "title") plans.sort((a, b) => a.title.localeCompare(b.title, "zh-CN"));
    document.getElementById("lessonSearchCount").textContent = `共 ${plans.length} 份${q ? "匹配教案" : "教案记录"}`;
    const rows = document.getElementById("lessonRows");
    rows.innerHTML = plans.length ? plans.map(plan => `<tr><td><b>${esc(plan.title)}</b><br><small>${esc(plan.song_name)}</small></td><td>${esc(plan.class_name)}</td><td>${plan.duration_minutes} 分钟</td><td><span class="status ${plan.generation_mode === "ai" ? "ok" : "info"}">${plan.generation_mode === "ai" ? "已完善" : "基础教案"}</span></td><td>${esc(plan.created_at)}</td><td class="lesson-actions"><button class="link" data-view="${plan.id}">查看</button><button class="link" data-edit="${plan.id}">编辑</button><button class="link" data-pdf="${plan.id}">PDF</button><button class="link" data-word="${plan.id}">Word</button></td></tr>`).join("") : '<tr><td colspan="6" class="empty">没有找到匹配的教案记录</td></tr>';
    rows.querySelectorAll("button[data-view]").forEach(button => button.onclick = () => viewPlan(plans.find(p => p.id === Number(button.dataset.view))));
    rows.querySelectorAll("button[data-edit]").forEach(button => button.onclick = () => editPlan(plans.find(p => p.id === Number(button.dataset.edit)), container));
    rows.querySelectorAll("button[data-pdf]").forEach(button => button.onclick = () => exportLessonPdf(plans.find(p => p.id === Number(button.dataset.pdf))));
    rows.querySelectorAll("button[data-word]").forEach(button => button.onclick = () => exportLessonWord(plans.find(p => p.id === Number(button.dataset.word))));
  }
}

async function renderArchive(container, kind) {
  container.innerHTML = '<section class="card"><p class="muted">正在读取归档记录…</p></section>';
  if (kind === "audio") {
    const rows = await api.audioAnalyses();
    container.innerHTML = `<section class="list-search"><div class="list-filters"><select id="archiveSort" aria-label="音频分析排序"><option value="newest">最新分析</option><option value="oldest">最早分析</option><option value="song">歌曲名称</option><option value="score">音高稳定分</option></select></div></section><section class="archive-list" id="archiveRows"></section>`;
    const paint = () => { const sorted = [...rows]; const sort = document.getElementById("archiveSort").value; if (sort === "oldest") sorted.reverse(); if (sort === "song") sorted.sort((a,b) => a.song_name.localeCompare(b.song_name, "zh-CN")); if (sort === "score") sorted.sort((a,b) => (b.scores?.pitch_stability || 0) - (a.scores?.pitch_stability || 0)); document.getElementById("archiveRows").innerHTML = `${sorted.length ? sorted.map(item => {
      const compare = item.intonation_comparison;
      return `<article class="card archive-item"><div><span class="eyebrow">AUDIO ANALYSIS</span><h3>《${esc(item.song_name)}》</h3><p>${esc(item.created_at)} · ${item.duration_seconds || "—"} 秒</p><div class="analysis-summary">${Object.entries(item.scores || {}).map(([key, value]) => `<span>${({ pitch_stability: "音高", rhythm_regularness: "节拍", dynamics: "力度", clarity: "清晰" })[key]} <b>${value}</b></span>`).join("")}</div><p class="muted">${esc(compare?.available ? `${compare.status} · 中位偏差 ${compare.median_deviation_cents} cents` : "无参考音频：仅保存稳定性分析")}</p></div><div class="archive-actions"><audio controls preload="metadata" src="${esc(apiUrl(item.recording_url))}"></audio><button class="link" data-import-analysis="${item.id}">带入课堂反馈</button></div></article>`;
    }).join("") : '<section class="card empty">暂无音频分析记录。完成一次分析后，录音和结果会自动保存在这里。</section>'}`; container.querySelectorAll("[data-import-analysis]").forEach(button => button.onclick = () => { localStorage.setItem("audioAnalysisForFeedback", JSON.stringify({ id: Number(button.dataset.importAnalysis) })); window.dispatchEvent(new CustomEvent("app:navigate", { detail: "feedback" })); }); };
    document.getElementById("archiveSort").onchange = paint; paint();
    return;
  }
  const rows = await api.feedbackRecords();
  container.innerHTML = `<section class="list-search"><div class="list-filters"><select id="feedbackSort" aria-label="课堂反馈排序"><option value="newest">最新反馈</option><option value="oldest">最早反馈</option><option value="lesson">教案名称</option></select></div></section><section class="archive-list" id="feedbackRows"></section>`;
  const paintFeedback = () => {
    const sorted = [...rows];
    const sort = document.getElementById("feedbackSort").value;
    if (sort === "oldest") sorted.reverse();
    if (sort === "lesson") sorted.sort((a, b) => a.lesson_title.localeCompare(b.lesson_title, "zh-CN"));
    document.getElementById("feedbackRows").innerHTML = sorted.length ? sorted.map(item => {
      const goals = item.analysis?.goal_observations || [];
      const goalLabel = status => status === "achieved" ? "已达到" : status === "developing" ? "正在形成" : status === "not_observed" ? "本次未观察到" : "暂未记录";
      return `<article class="card archive-item feedback-archive-item"><div><span class="eyebrow">CLASSROOM FEEDBACK</span><h3>${esc(item.lesson_title)}</h3><p>${esc(item.song_name)} · ${esc(item.created_at)} · 整体效果：${esc(item.overall_effect)}</p><dl><dt>音频分析总结</dt><dd>${esc(item.audio_summary || "未带入音频分析")}</dd><dt>课堂亮点</dt><dd>${esc(item.highlights || "—")}</dd><dt>存在问题</dt><dd>${esc(item.problems || "—")}</dd><dt>下次改进</dt><dd>${esc(item.improvement || "—")}</dd></dl>${goals.length ? `<section class="archived-goal-observations"><b>本课目标观察</b><ul>${goals.map(goal => `<li><span>${esc(goal.objective)}</span><small>${goalLabel(goal.status)}</small></li>`).join("")}</ul></section>` : ""}<details class="feedback-inline-edit"><summary>编辑这条反馈</summary><div class="feedback-edit-grid"><label>整体效果<select data-edit-field="overall_effect"><option ${item.overall_effect === "很好" ? "selected" : ""}>很好</option><option ${item.overall_effect === "较好" ? "selected" : ""}>较好</option><option ${item.overall_effect === "一般" ? "selected" : ""}>一般</option><option ${item.overall_effect === "较差" ? "selected" : ""}>较差</option></select></label><label>音频分析总结<textarea data-edit-field="audio_summary">${esc(item.audio_summary || "")}</textarea></label><label>课堂亮点<textarea data-edit-field="highlights">${esc(item.highlights || "")}</textarea></label><label>存在问题<textarea data-edit-field="problems">${esc(item.problems || "")}</textarea></label><label>下次改进<textarea data-edit-field="improvement">${esc(item.improvement || "")}</textarea></label></div>${goals.length ? `<div class="feedback-edit-goals"><b>目标观察</b>${goals.map((goal, index) => `<label><span>${esc(goal.objective)}</span><select data-edit-goal="${index}"><option value="" ${!goal.status ? "selected" : ""}>暂未记录</option><option value="achieved" ${goal.status === "achieved" ? "selected" : ""}>已达到</option><option value="developing" ${goal.status === "developing" ? "selected" : ""}>正在形成</option><option value="not_observed" ${goal.status === "not_observed" ? "selected" : ""}>本次未观察到</option></select></label>`).join("")}</div>` : ""}<button class="btn primary" type="button" data-save-feedback-edit="${item.id}">保存反馈修改</button></details></div>${item.audio_analysis_id ? `<aside class="feedback-audio-link"><b>已关联音频记录</b><span>${esc(item.analysis?.analysis_mode_label || "课堂音频分析")}</span><button class="btn soft" data-open-feedback-audio="${item.audio_analysis_id}">查看完整分析</button><small>包含分段证据、建议与录音回听</small></aside>` : ""}</article>`;
    }).join("") : '<section class="card empty">暂无课堂反馈记录。保存反馈后会完整归档在这里。</section>';
    container.querySelectorAll("[data-open-feedback-audio]").forEach(button => button.onclick = () => { localStorage.setItem("lastAudioAnalysisId", button.dataset.openFeedbackAudio); window.dispatchEvent(new CustomEvent("app:navigate", { detail: "audio" })); });
    container.querySelectorAll("[data-save-feedback-edit]").forEach(button => button.onclick = async () => {
      const item = rows.find(record => record.id === Number(button.dataset.saveFeedbackEdit));
      const card = button.closest(".feedback-archive-item");
      if (!item || !card) return;
      const value = field => card.querySelector(`[data-edit-field="${field}"]`)?.value || "";
      const goal_observations = goalsForItem(item).map((goal, index) => {
        const status = card.querySelector(`[data-edit-goal="${index}"]`)?.value || "";
        return status ? { ...goal, status } : null;
      }).filter(Boolean);
      button.disabled = true;
      try {
        await api.updateFeedback(item.id, {
          lesson_plan_id: item.lesson_plan_id, audio_analysis_id: item.audio_analysis_id || null,
          overall_effect: value("overall_effect"), audio_summary: value("audio_summary"),
          highlights: value("highlights"), problems: value("problems"), improvement: value("improvement"),
          analysis: { ...(item.analysis || {}), goal_observations },
        });
        notify("课堂反馈已更新");
        await renderArchive(container, "feedback");
      } catch (error) {
        button.disabled = false;
        notify(`更新反馈失败：${error.message}`, "error");
      }
    });
  };
  const goalsForItem = item => item.analysis?.goal_observations || [];
  document.getElementById("feedbackSort").onchange = paintFeedback; paintFeedback();
}

function viewPlan(plan) {
  showModal(`<div class="modal-head"><div><h2>完整教案</h2><p>${esc(plan.class_name)} · ${esc(plan.created_at)}</p></div><button class="close" data-close>×</button></div><div class="modal-export"><button class="btn" id="modalPdf">导出 PDF</button><button class="btn" id="modalWord">导出 Word</button></div>${lessonView(plan)}`);
  document.getElementById("modalPdf").onclick = () => exportLessonPdf(plan);
  document.getElementById("modalWord").onclick = () => exportLessonWord(plan);
}

function editPlan(plan, container) {
  const c = plan.content;
  const timeline = (c.timeline || []).map((item, i) => `<section class="edit-stage"><b>${item.minutes} · ${esc(item.stage)}</b><label>教师活动<textarea data-teacher="${i}">${esc(item.teacher)}</textarea></label><label>学生活动<textarea data-student="${i}">${esc(item.students)}</textarea></label></section>`).join("");
  const root = showModal(`<div class="modal-head"><div><h2>编辑教案</h2><p>可直接修订每个教学章节；保存后会更新当前教学档案。</p></div><button class="close" data-close>×</button></div><div class="edit-lesson"><label>教案标题<input id="editTitle" value="${esc(c.title)}"></label><label>教师补充要求<textarea id="editRequirements" placeholder="可修改生成教案时的原始要求">${esc(c.teacher_requirements || plan.teacher_requirements || "")}</textarea></label><label>教学目标（每行一项）<textarea id="editObjectives">${esc((c.objectives || []).join("\n"))}</textarea></label><label>教学重点<textarea id="editKey">${esc(c.key_points)}</textarea></label><label>教学难点<textarea id="editDifficulty">${esc(c.difficulties)}</textarea></label><label>课前准备<textarea id="editPreparation">${esc(c.preparation)}</textarea></label><section class="edit-subsection"><b>课堂流程</b>${timeline}</section><section class="edit-subsection"><b>乐理与纠正练习</b><label>乐理标题<input id="editTheoryTerm" value="${esc(c.theory_explanation?.term || "")}"></label><label>乐理讲解<textarea id="editTheoryScript">${esc(c.theory_explanation?.script || "")}</textarea></label><label>易错表现<textarea id="editMistakeProblem">${esc(c.mistake_practice?.problem || "")}</textarea></label><label>纠正练习<textarea id="editMistakeCorrection">${esc(c.mistake_practice?.correction || "")}</textarea></label></section><label>分层教学（每行一项）<textarea id="editDifferentiation">${esc((c.differentiation || []).join("\n"))}</textarea></label><label>课堂评价<textarea id="editAssessment">${esc(c.assessment)}</textarea></label><button class="btn primary" id="saveLessonEdit">保存修改</button></div>`);
  root.querySelector("#saveLessonEdit").onclick = async () => {
    c.title = document.getElementById("editTitle").value.trim() || c.title;
    c.objectives = document.getElementById("editObjectives").value.split("\n").map(x => x.trim()).filter(Boolean);
    c.key_points = document.getElementById("editKey").value.trim();
    c.difficulties = document.getElementById("editDifficulty").value.trim();
    c.preparation = document.getElementById("editPreparation").value.trim();
    c.theory_explanation = { ...(c.theory_explanation || {}), term: document.getElementById("editTheoryTerm").value.trim(), script: document.getElementById("editTheoryScript").value.trim() };
    c.mistake_practice = { ...(c.mistake_practice || {}), problem: document.getElementById("editMistakeProblem").value.trim(), correction: document.getElementById("editMistakeCorrection").value.trim() };
    c.differentiation = document.getElementById("editDifferentiation").value.split("\n").map(x => x.trim()).filter(Boolean);
    c.assessment = document.getElementById("editAssessment").value.trim();
    c.teacher_requirements = root.querySelector("#editRequirements").value.trim();
    c.timeline.forEach((item, i) => { item.teacher = root.querySelector(`[data-teacher="${i}"]`).value.trim(); item.students = root.querySelector(`[data-student="${i}"]`).value.trim(); });
    await api.updateLesson(plan.id, { song_id: plan.song_id, class_id: plan.class_id, duration_minutes: plan.duration_minutes, teacher_requirements: c.teacher_requirements, generation_mode: plan.generation_mode, content: c });
    document.getElementById("modalRoot").innerHTML = "";
    notify("教案已更新");
    renderLessons(container);
  };
}
