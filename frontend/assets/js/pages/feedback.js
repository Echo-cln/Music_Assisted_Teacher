import { api, apiUrl } from "../api/client.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const scoreLabels = { pitch_stability: "主音高轨迹稳定度", rhythm_regularness: "起音间隔规律", dynamics: "力度变化", clarity: "录音清晰度" };

function openAudioAnalysis(id) {
  if (!id) return notify("这条课堂反馈没有可打开的音频分析记录", "error");
  localStorage.setItem("lastAudioAnalysisId", String(id));
  window.dispatchEvent(new CustomEvent("app:navigate", { detail: "audio" }));
}

export async function renderFeedback(container) {
  const lessons = await api.lessons();
  const analyses = await api.audioAnalyses();
  const pointer = JSON.parse(localStorage.getItem("audioAnalysisForFeedback") || "null");
  let imported = null;
  if (pointer?.id) {
    try { imported = await api.audioAnalysis(pointer.id); } catch (_) { localStorage.removeItem("audioAnalysisForFeedback"); }
  }
  container.innerHTML = pageHeader("课堂反馈", "沉淀教师观察；音频分析会作为可编辑的课堂证据写入反馈正文。") + `
    <div class="feedback-layout">
      <section class="card"><span class="eyebrow">TEACHER REFLECTION</span><h2>本课观察与改进</h2>
        <label>对应教案<select id="lessonId"><option value="">请选择已保存教案</option>${lessons.map(plan => `<option value="${plan.id}" ${imported?.lesson_plan_id === plan.id ? "selected" : ""}>${esc(plan.title)} · ${esc(plan.class_name)}</option>`).join("")}</select></label>
        <label>关联音频分析（选填）<select id="audioAnalysisId"><option value="">不带入音频分析</option></select><small>只显示已绑定当前教案的分析；选择后会把摘要写入下方可编辑文本。</small></label>
        <section class="goal-observation-module hidden" id="goalObservations"><div class="module-head"><div><span class="eyebrow">LEARNING EVIDENCE</span><h3>本课目标观察</h3></div><span class="status info">课后记录</span></div><p class="muted">根据学生实际表现记录进展；未观察到的目标可以留空。</p><div id="goalObservationRows"></div></section>
        <label>整体效果<select id="effect"><option>很好</option><option selected>较好</option><option>一般</option><option>较差</option></select></label>
        <section class="feedback-audio-module"><div class="module-head"><div><span class="eyebrow">AUDIO EVIDENCE</span><h3>音频分析总结</h3></div>${imported ? '<span class="status ok">已带入</span>' : '<span class="status info">可选</span>'}</div><textarea id="audioSummary" placeholder="可从音频分析带入，也可手动填写本节课的音准、节拍或声音表现总结。">${esc(imported ? buildSummary(imported) : "")}</textarea><small>该部分会随课堂反馈一起归档，之后仍可编辑查看。</small></section>
        <label>课堂亮点<textarea id="highlights" placeholder="例如：小组声势合作积极，学生能够主动描述歌曲情绪。"></textarea></label>
        <label>存在问题<textarea id="problems" placeholder="例如：第二乐句进入偏早，长音收尾不够稳定。"></textarea></label>
        <label>下次改进<textarea id="improvement" placeholder="例如：课前增加两分钟恒拍练习，分层安排领唱任务。"></textarea></label>
        <button class="btn primary" id="saveFeedback">保存课堂反馈</button>
      </section>
      <aside class="side-stack"><section class="card feedback-record-card"><div class="module-head"><div><span class="eyebrow">LINKED RECORD</span><h3>已带入的音频记录</h3></div>${imported ? '<span class="status ok">已关联</span>' : '<span class="status info">待选择</span>'}</div>${imported ? summaryView(imported) : '<p class="muted">尚未带入分析记录。可先前往“音频分析”完成录音分析，分析结果会自动保存。</p>'}</section></aside>
    </div>`;
  const lessonSelect = document.getElementById("lessonId");
  const audioSelect = document.getElementById("audioAnalysisId");
  const renderGoalObservations = () => {
    const plan = lessons.find(item => item.id === Number(lessonSelect.value));
    const module = document.getElementById("goalObservations");
    const rows = document.getElementById("goalObservationRows");
    const objectives = plan?.content?.objective_evidence || (plan?.content?.objectives || []).map(objective => ({ objective, evidence: "" }));
    if (!module || !rows) return;
    module.classList.toggle("hidden", !objectives.length);
    rows.innerHTML = objectives.map((item, index) => `<label class="goal-observation-row"><span><b>目标 ${index + 1}</b><strong>${esc(item.objective)}</strong>${item.evidence ? `<small>观察依据：${esc(item.evidence)}</small>` : ""}</span><select data-goal-observation="${index}" aria-label="目标 ${index + 1}进展"><option value="">暂未记录</option><option value="achieved">已达到</option><option value="developing">正在形成</option><option value="not_observed">本次未观察到</option></select></label>`).join("");
  };
  const bindLinkedRecord = () => document.querySelector("[data-open-audio-analysis]")?.addEventListener("click", () => openAudioAnalysis(Number(document.querySelector("[data-open-audio-analysis]").dataset.openAudioAnalysis)));
  bindLinkedRecord();
  function refreshAudioChoices() {
    const lessonId = Number(lessonSelect.value);
    const allowed = analyses.filter(item => item.lesson_plan_id === lessonId);
    audioSelect.innerHTML = '<option value="">不带入音频分析</option>' + allowed.map(item => `<option value="${item.id}" ${item.id === imported?.id ? "selected" : ""}>《${esc(item.song_name)}》· ${esc(item.analysis_mode_label)} · ${esc(item.created_at)}</option>`).join("");
    if (imported && !allowed.some(item => item.id === imported.id)) imported = null;
  }
  refreshAudioChoices();
  renderGoalObservations();
  lessonSelect.onchange = () => { imported = null; refreshAudioChoices(); renderGoalObservations(); document.getElementById("audioSummary").value = ""; const card = document.querySelector(".feedback-record-card"); if (card) card.innerHTML = '<div class="module-head"><div><span class="eyebrow">LINKED RECORD</span><h3>已带入的音频记录</h3></div><span class="status info">待选择</span></div><p class="muted">请选择一条已绑定本教案的分析记录。保存后，课堂反馈会保留它的完整跳转入口。</p>'; };
  audioSelect.onchange = async () => {
    const id = Number(audioSelect.value);
    imported = id ? analyses.find(item => item.id === id) : null;
    if (imported) {
      document.getElementById("audioSummary").value = buildSummary(imported);
      const card = document.querySelector(".feedback-record-card");
      if (card) { card.innerHTML = `<div class="module-head"><div><span class="eyebrow">LINKED RECORD</span><h3>已带入的音频记录</h3></div><span class="status ok">已关联</span></div>${summaryView(imported)}`; bindLinkedRecord(); }
    }
  };
  document.getElementById("saveFeedback").onclick = async () => {
    const lessonId = Number(document.getElementById("lessonId").value);
    if (!lessonId) return notify("请先选择对应教案");
    const goalObservations = [...document.querySelectorAll("[data-goal-observation]")].map(select => {
      const plan = lessons.find(item => item.id === lessonId);
      const goals = plan?.content?.objective_evidence || (plan?.content?.objectives || []).map(objective => ({ objective, evidence: "" }));
      const goal = goals[Number(select.dataset.goalObservation)];
      return goal && select.value ? { objective: goal.objective, evidence: goal.evidence || "", status: select.value } : null;
    }).filter(Boolean);
    await api.feedback({
      lesson_plan_id: lessonId, overall_effect: document.getElementById("effect").value,
      highlights: document.getElementById("highlights").value.trim(), problems: document.getElementById("problems").value.trim(),
      improvement: document.getElementById("improvement").value.trim(), audio_summary: document.getElementById("audioSummary").value.trim(),
      audio_analysis_id: Number(audioSelect.value) || null, analysis: { ...(imported || {}), goal_observations: goalObservations },
    });
    localStorage.removeItem("audioAnalysisForFeedback");
    notify("课堂反馈与音频分析总结已归档");
  };
}

function buildSummary(result) {
  const scores = result.scores || {};
  const base = `《${result.song_name}》课堂录音自动声学线索（非个人成绩）：主音高轨迹稳定度 ${scores.pitch_stability ?? "—"}/100，起音间隔规律 ${scores.rhythm_regularness ?? "—"}/100，力度变化 ${scores.dynamics ?? "—"}/100，录音清晰度 ${scores.clarity ?? "—"}/100。`;
  const compare = result.intonation_comparison;
  const note = result.note_assessment;
  if (note?.available) return `${base} 单人练唱逐音评测：得分 ${note.score} 分，匹配 ${note.matched_notes} 个音，±50 cents 命中率 ${note.accurate_note_ratio}%，中位偏差 ${note.median_deviation_cents} cents。${result.suggestions?.[0] || ""}`;
  if (compare?.available) return `${base} 参考音频对齐后：${compare.status}，中位音高偏差 ${compare.median_deviation_cents} cents，疑似跑调帧 ${compare.off_pitch_ratio}%。${result.suggestions?.[0] || ""}`;
  return `${base} ${compare?.message || "未进行参考音频音准对齐。"} ${result.suggestions?.[0] || ""}`;
}

function summaryView(result) {
  const scores = Object.entries(result.scores || {}).map(([key, value]) => `<span>${scoreLabels[key] || key} <b>${value}</b></span>`).join("");
  const comparison = result.intonation_comparison;
  const detail = comparison?.available ? `${comparison.status} · 偏差 ${comparison.median_deviation_cents} cents` : comparison?.message || "已带入录音分析";
  return `<p class="linked-record-title"><b>《${esc(result.song_name)}》</b><small>${esc(result.analysis_mode_label || "课堂音频分析")} · ${esc(result.created_at || "")}</small></p><div class="analysis-summary">${scores}</div><p class="muted">${esc(detail)}</p><audio controls preload="metadata" src="${esc(apiUrl(result.recording_url))}"></audio><button class="btn soft block linked-record-button" data-open-audio-analysis="${result.id}">查看完整音频分析</button><small class="linked-record-help">将打开这一次录音的完整指标、分段证据、练习建议与音频回听。</small>`;
}
