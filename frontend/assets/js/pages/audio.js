import { api } from "../api/client.js";
import { esc, loading, notify, pageHeader } from "../utils/dom.js";
import { drawWaveform } from "../utils/waveform.js";
import { startAudioJob } from "../state/audio_jobs.js";

const scoreNames = { pitch_stability: "音高稳定", rhythm_regularness: "节拍稳定", dynamics: "力度层次", clarity: "清晰度" };

export async function renderAudio(container) {
  const lessons = await api.lessons();
  container.innerHTML = pageHeader("课堂音频分析", "选择课堂整体分析或单人练唱逐音评测；每次结果和音频都会自动保存。") + `
    <section class="card audio-intro"><div><span class="eyebrow">RECORDING REVIEW</span><h2>用适合的方式评估一段课堂声音</h2><p>课堂整体分析适合合唱与课堂录音；单人练唱逐音评测会将参考旋律转写为音符目标，再计算每个音的实际偏高或偏低。</p></div><span class="status info">可保存分析</span></section>
    <section class="card"><div class="form-grid">
      <label class="full">分析方式<select id="analysisMode"><option value="classroom">课堂整体分析 · 音高稳定、节拍、力度与分段建议</option><option value="solo">单人练唱逐音评测 · 需要参考音频，输出每个音的偏差</option></select><small id="modeHint">适合课堂合唱、带环境声的录音；不输出逐音跑调结论。</small></label>
      <label class="full">关联教案（选填）<select id="lessonPlanId"><option value="">私人练唱 / 不关联课堂教案</option>${lessons.map(item => `<option value="${item.id}">${esc(item.title)} · ${esc(item.class_name)}</option>`).join("")}</select><small>选择后，本次音频分析会绑定至该教案；后续课堂反馈只能带入本教案的分析记录。</small></label>
      <label class="full">对应歌曲<div class="song-picker"><label class="search-field"><span>⌕</span><input id="songSearch" type="search" placeholder="搜索歌曲名称、地区或省份"></label><select id="songId"></select><div class="list-filters"><select id="songGradeFilter"><option value="">全部适用年级</option><option value="1">含 1 年级</option><option value="2">含 2 年级</option><option value="3">含 3 年级</option><option value="4">含 4 年级</option><option value="5">含 5 年级</option><option value="6">含 6 年级</option></select><select id="songRegionFilter"><option value="">全部地区</option></select></div><small id="songSearchCount"></small></div></label>
      <label>课堂录音<input id="recording" class="file-input" type="file" accept="audio/*" required><span class="upload-control"><span class="upload-button">选择课堂录音</span><span class="file-name" id="recordingName">尚未选择文件</span></span><small>支持 WAV、MP3、M4A 等常见格式</small></label>
      <label class="full optional-audio">参考原唱（可选）<input id="original" class="file-input" type="file" accept="audio/*"><span class="upload-control"><span class="upload-button secondary">选择参考原唱</span><span class="file-name" id="originalName">不上传也可分析</span></span><small>仅用于整体参考相似度，不参与音高、节拍等核心评分。</small></label>
    </div><div class="actions"><button class="btn primary" id="analyze">开始分析录音</button></div></section>
    <div id="analysis"></div>`;
  let searchTimer;
  document.getElementById("songSearch").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadSongs, 220); };
  ["songGradeFilter", "songRegionFilter"].forEach(id => document.getElementById(id).onchange = loadSongs);
  await loadSongs();
  const savedAnalysisId = localStorage.getItem("lastAudioAnalysisId");
  if (savedAnalysisId) {
    api.audioAnalysis(savedAnalysisId).then(showResult).catch(() => localStorage.removeItem("lastAudioAnalysisId"));
  }
  document.getElementById("recording").onchange = event => { document.getElementById("recordingName").textContent = event.target.files[0]?.name || "尚未选择文件"; };
  document.getElementById("original").onchange = event => { document.getElementById("originalName").textContent = event.target.files[0]?.name || "不上传也可分析"; };
  document.getElementById("analysisMode").onchange = event => {
    const solo = event.target.value === "solo";
    document.getElementById("modeHint").textContent = solo ? "必须上传参考旋律；建议使用清晰单人声部，分析会生成逐音偏差与命中率。" : "适合课堂合唱、带环境声的录音；不输出逐音跑调结论。";
    document.getElementById("originalName").textContent = solo ? "逐音评测必须选择参考音频" : "不上传也可分析";
  };

  async function loadSongs() {
    const select = document.getElementById("songId");
    const q = document.getElementById("songSearch").value.trim();
    const selected = select.value;
    let songs = await api.songs({ q });
    const grade = document.getElementById("songGradeFilter").value;
    const region = document.getElementById("songRegionFilter");
    const allRegions = [...new Set(songs.map(song => song.region).filter(Boolean))];
    const currentRegion = region.value;
    region.innerHTML = '<option value="">全部地区</option>' + allRegions.map(item => `<option ${item === currentRegion ? "selected" : ""}>${esc(item)}</option>`).join("");
    if (grade) songs = songs.filter(song => String(song.grade || "").includes(grade));
    if (currentRegion) songs = songs.filter(song => song.region === currentRegion);
    select.innerHTML = songs.map(song => `<option value="${song.id}" ${String(song.id) === selected ? "selected" : ""}>${esc(song.name)} · ${esc(song.province)}</option>`).join("");
    document.getElementById("songSearchCount").textContent = `共 ${songs.length} 首${q ? "匹配歌曲" : "可选歌曲"}`;
    select.disabled = !songs.length;
  }

  document.getElementById("analyze").onclick = async () => {
    const recording = document.getElementById("recording").files[0];
    if (!recording) return notify("请先选择课堂录音");
    const songId = document.getElementById("songId").value;
    if (!songId) return notify("请先搜索并选择一首对应歌曲");
    const form = new FormData();
    form.append("song_id", document.getElementById("songId").value);
    if (document.getElementById("lessonPlanId").value) form.append("lesson_plan_id", document.getElementById("lessonPlanId").value);
    const analysisMode = document.getElementById("analysisMode").value;
    form.append("analysis_mode", analysisMode);
    form.append("recording", recording);
    const original = document.getElementById("original").files[0];
    if (analysisMode === "solo" && !original) return notify("单人练唱逐音评测需要上传参考音频");
    if (original) form.append("original", original);
    const area = document.getElementById("analysis");
    area.innerHTML = analysisProgress("音频正在转入后台任务；您可以离开此页，右下角会持续显示真实进度。", 3);
    try {
      await startAudioJob(form);
      area.innerHTML = analysisProgress("后台任务已创建。可切换到任何页面，右下角会显示真实处理阶段与完成状态。", 8);
    } catch (error) {
      area.innerHTML = `<div class="notice">${esc(error.message)}</div>`;
    }
  };

  window.addEventListener("audio-job:complete", event => {
    const result = event.detail?.analysis;
    if (result) showResult(result);
  });

  function showResult(result) {
    const area = document.getElementById("analysis");
    if (!area) return;
    area.innerHTML = resultView(result);
    const recordingWave = document.getElementById("recordingWave");
    if (recordingWave) drawWaveform(recordingWave, result.recording_waveform, "#547785");
    if (result.has_reference_comparison) drawWaveform(document.getElementById("referenceWave"), result.reference_waveform, "#9f4b35");
    document.getElementById("toFeedback").onclick = () => {
      localStorage.setItem("audioAnalysisForFeedback", JSON.stringify({ id: result.id }));
      window.dispatchEvent(new CustomEvent("app:navigate", { detail: "feedback" }));
    };
  }
}

function analysisProgress(message, progress) {
  return `<section class="card analysis-progress" aria-live="polite"><div><span class="eyebrow">BACKGROUND ANALYSIS</span><h3>音频分析正在后台运行</h3><p>${esc(message)}</p></div><div class="generation-progress"><i style="width:${progress}%"></i></div><small>进度来自后端实际阶段：保存音频 → 提取音高/节拍 → 计算指标 → 保存结果。</small></section>`;
}

function resultView(result) {
  if (!result.analysis_available) return `<section class="card notice"><h3>本次录音未能完成分析</h3><p>${esc(result.suggestions[0])}</p></section>`;
  const scoreCards = Object.entries(result.scores).map(([key, value]) => `<div><b>${value}</b><small>${scoreNames[key]}</small></div>`).join("");
  const comparison = result.intonation_comparison || {};
  const pitchComparison = comparison.available ? `<section class="intonation-card"><div><span class="eyebrow">PITCH COMPARISON</span><h3>参考音频对齐后的音准提示</h3><p>${esc(comparison.message)}</p></div><div class="intonation-score"><b>${comparison.intonation_score}</b><span>${esc(comparison.status)}</span></div><div class="analysis-summary"><span>中位偏差 <b>${comparison.median_deviation_cents} cents</b></span><span>疑似跑调帧 <b>${comparison.off_pitch_ratio}%</b></span></div><div class="segment-list compact">${(comparison.segments || []).map(item => `<div><b>${esc(item.part)}</b><span>${esc(item.status)}</span><p>偏差 ${item.median_deviation_cents} cents · 疑似跑调 ${item.off_pitch_ratio}%</p></div>`).join("")}</div></section>` : `<section class="notice analysis-note"><b>跑调判定暂不可用</b><p>${esc(comparison.message || "请上传参考音频，或使用单独、清晰的人声录音。")}</p></section>`;
  const player = `<section class="audio-player-card"><h3>回听本次录音</h3><p class="muted">${esc(result.recording_filename || "课堂录音")}</p><audio controls preload="metadata" src="${esc(result.recording_url)}"></audio>${result.reference_url ? `<p class="muted">参考音频：${esc(result.reference_filename || "参考原唱")}</p><audio controls preload="metadata" src="${esc(result.reference_url)}"></audio>` : ""}</section>`;
  const noteAssessment = result.note_assessment?.available ? `<section class="note-assessment"><div class="card-head"><div><span class="eyebrow">NOTE-BY-NOTE ASSESSMENT</span><h3>单人练唱逐音评测</h3><p>${esc(result.note_assessment.message)}</p></div><div class="intonation-score"><b>${result.note_assessment.score}</b><span>逐音得分</span></div></div><div class="analysis-summary"><span>匹配音符 <b>${result.note_assessment.matched_notes}</b></span><span>±50 cents 命中 <b>${result.note_assessment.accurate_note_ratio}%</b></span><span>中位偏差 <b>${result.note_assessment.median_deviation_cents} cents</b></span></div><div class="note-table"><table><thead><tr><th>#</th><th>目标音</th><th>时间</th><th>偏差</th><th>判定</th></tr></thead><tbody>${result.note_assessment.events.map(item => `<tr><td>${item.index}</td><td>${esc(item.expected_note)}</td><td>${item.start_seconds}–${item.end_seconds}s</td><td class="${Math.abs(item.deviation_cents) > 50 ? "off-pitch" : ""}">${item.deviation_cents > 0 ? "+" : ""}${item.deviation_cents} cents</td><td>${esc(item.status)}</td></tr>`).join("")}</tbody></table></div></section>` : result.analysis_mode === "solo" ? `<section class="notice analysis-note"><b>逐音组件未完成本次转写</b><p>${esc(result.note_assessment?.message || "请检查专业组件安装和录音质量。")}</p></section>` : "";
  return `<section class="analysis-result"><div class="card"><div class="card-head"><div><span class="eyebrow">ANALYSIS RESULT</span><h2>《${esc(result.song_name)}》${esc(result.analysis_mode_label || "课堂音频分析")}</h2><p class="muted">已保存 · 时长 ${result.duration_seconds} 秒 · 推测速度 ${result.tempo_bpm ?? "—"} BPM</p></div><span class="status ok">分析记录 #${result.id}</span></div><p class="analysis-scope">${esc(result.analysis_scope)}</p><div class="scores professional-scores">${scoreCards}</div>${player}${noteAssessment}${pitchComparison}<h3>分段关注点</h3><div class="segment-list">${result.segment_feedback.map(item => `<div><b>${esc(item.time)}</b><span>${esc(item.focus)} · ${item.pitch_stability ?? "—"} 分</span><p>${esc(item.note)}</p></div>`).join("")}</div><h3>下一步建议</h3><ul>${result.suggestions.map(item => `<li>${esc(item)}</li>`).join("")}</ul><details class="method-details"><summary>查看本次分析的方法与边界</summary><ol>${(result.analysis_method || []).map(item => `<li>${esc(item)}</li>`).join("")}</ol><p>说明：分析记录和音频已保存到“教学档案与课堂记录”。逐音评测适合单人或主声部清晰的录音，不可替代专业声乐考级。</p></details><button class="btn primary" id="toFeedback">将分析总结写入课堂反馈</button></div>${referenceView(result)}</section>`;
}

function referenceView(result) {
  if (!result.has_reference_comparison) return "";
  return `<section class="card reference-panel"><div class="card-head"><div><h3>参考原唱对比</h3><small>仅反映整体能量轮廓相似度，不等同音准评分。</small></div><b class="reference-score">${result.reference_similarity}</b></div><div class="wave"><b>参考音频</b><div id="referenceWave"></div></div><div class="wave"><b>课堂录音</b><div id="recordingWave"></div></div></section>`;
}
