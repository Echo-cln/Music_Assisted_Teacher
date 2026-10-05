import { api, apiUrl } from "../api/client.js";
import { esc, loading, notify, pageHeader } from "../utils/dom.js";
import { drawWaveform } from "../utils/waveform.js";
import { cancelActiveAudioJob, refreshAudioJob, startAudioJob } from "../state/audio_jobs.js";

const scoreNames = { pitch_stability: "音高稳定", rhythm_regularness: "节拍稳定", dynamics: "力度层次", clarity: "清晰度" };

export async function renderAudio(container) {
  const lessons = await api.lessons();
  container.innerHTML = pageHeader("课堂音频分析", "选择课堂整体分析或单人练唱逐音评测；每次结果和音频都会自动保存。") + `
    <section class="card audio-intro"><div><span class="eyebrow">RECORDING REVIEW</span><h2>用清楚的输入，得到可追溯的课堂证据</h2><p>先选分析方式，再选择歌曲、课堂录音与所需参考旋律。课堂整体分析关注班级声音表现；单人练唱逐音评测只依据清晰人声参考音频。</p></div><span class="status info">可保存分析</span></section>
    <section class="card audio-analysis-form">
      <div class="audio-form-section"><div class="audio-form-heading"><span>01</span><div><h3>确定分析目标</h3><p>不同目标使用不同的分析依据和结果呈现。</p></div></div><div class="form-grid">
        <label class="full">分析方式<select id="analysisMode"><option value="classroom">课堂整体分析 · 音高稳定、节拍、力度与分段建议</option><option value="solo">单人练唱逐音评测 · 参考旋律对齐与逐音偏差</option></select><small id="modeHint">适合课堂合唱、带环境声的录音；不输出逐音跑调结论。</small></label>
        <label class="full">关联教案 <span class="field-optional">可选</span><select id="lessonPlanId"><option value="">私人练唱 / 不关联课堂教案</option>${lessons.map(item => `<option value="${item.id}">${esc(item.title)} · ${esc(item.class_name)}</option>`).join("")}</select><small>选择后，本次分析会绑定至该教案；课堂反馈只会显示本课的分析记录。</small></label>
      </div></div>
      <div class="audio-form-section"><div class="audio-form-heading"><span>02</span><div><h3>选择歌曲与课堂录音</h3><p>歌曲用于解释课堂情境；课堂录音是本次分析的必填材料。</p></div></div><div class="form-grid">
        <label class="full">对应歌曲<div class="song-picker"><label class="search-field"><span>⌕</span><input id="songSearch" type="search" placeholder="搜索歌曲名称、地区或省份"></label><select id="songId"></select><div class="list-filters"><select id="songGradeFilter"><option value="">全部适用年级</option><option value="1">含 1 年级</option><option value="2">含 2 年级</option><option value="3">含 3 年级</option><option value="4">含 4 年级</option><option value="5">含 5 年级</option><option value="6">含 6 年级</option></select><select id="songRegionFilter"><option value="">全部地区</option></select></div><small id="songSearchCount"></small></div></label>
        <label class="full audio-file-field"><span>课堂录音 <b>必填</b></span><input id="recording" class="file-input" type="file" accept="audio/*" required><span class="upload-control"><span class="upload-button">选择课堂录音</span><span class="file-name" id="recordingName">尚未选择文件</span></span><small>支持 WAV、MP3、M4A 等常见格式。</small></label>
      </div></div>
      <section class="reference-source-card" id="referenceSection"><div class="reference-source-head"><div><span class="eyebrow">REFERENCE MELODY</span><h3 id="referenceTitle">参考旋律 <em>可选</em></h3><p id="referenceCaption">课堂整体分析可不上传参考旋律；上传后可补充整体轮廓对比。</p></div><label class="reference-kind-field" id="referenceKindField"><span>参考素材类型</span><select id="referenceKind"><option value="mixed">原唱 / 伴奏混音（先分离人声）</option><option value="vocal">清晰单人参考人声（推荐）</option></select></label></div>
        <label class="audio-file-field"><span>参考音频文件</span><input id="original" class="file-input" type="file" accept="audio/*"><span class="upload-control"><span class="upload-button secondary">选择参考旋律</span><span class="file-name" id="originalName">不上传也可分析</span></span><small id="referenceHint">参考音频文件与“参考素材类型”是两个独立选项。</small></label>
      </section>
      <div class="actions"><button class="btn primary" id="analyze">开始分析录音</button></div>
    </section>
    <div id="analysis"></div>`;
  let searchTimer;
  document.getElementById("songSearch").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadSongs, 220); };
  ["songGradeFilter", "songRegionFilter"].forEach(id => document.getElementById(id).onchange = loadSongs);
  await loadSongs();
  const savedAnalysisId = localStorage.getItem("lastAudioAnalysisId");
  if (savedAnalysisId) {
    // 此值只是一次性深链指针：消费后清除，避免以后从侧栏进入时反复显示上一次的旧失败/旧结果。
    api.audioAnalysis(savedAnalysisId).then(showResult).finally(() => localStorage.removeItem("lastAudioAnalysisId"));
  }
  const activeJob = await refreshAudioJob();
  if (activeJob) showJobState(activeJob);
  document.getElementById("recording").onchange = event => { document.getElementById("recordingName").textContent = event.target.files[0]?.name || "尚未选择文件"; };
  document.getElementById("original").onchange = event => { document.getElementById("originalName").textContent = event.target.files[0]?.name || (document.getElementById("analysisMode").value === "solo" ? "逐音评测必须选择参考音频" : "不上传也可分析"); };
  const updateReferenceForm = () => {
    const solo = document.getElementById("analysisMode").value === "solo";
    const title = document.getElementById("referenceTitle");
    const kindField = document.getElementById("referenceKindField");
    const referenceKind = document.getElementById("referenceKind");
    const file = document.getElementById("original");
    document.getElementById("modeHint").textContent = solo
      ? "单人练唱会将课堂录音与参考旋律逐段对齐，输出音符级偏差；可使用清晰人声或原唱/伴奏混音。"
      : "课堂整体分析适合合唱、带环境声的录音；结果描述整体表现，不输出逐音跑调结论。";
    title.innerHTML = solo ? "参考旋律 <b>必填</b>" : "参考旋律 <em>可选</em>";
    document.getElementById("referenceCaption").textContent = solo
      ? "单人练唱必须提供参考旋律。可使用清晰人声，或原唱 / 伴奏混音（系统先分离人声）。"
      : "课堂整体分析可不上传参考旋律；上传后可补充整体轮廓对比。";
    // 单人练唱也要让教师选择混音/人声；混音会在后端先分离人声。
    // 不能静默改为 vocal，否则“原唱+伴奏”的合法使用路径会被隐藏。
    kindField.classList.remove("hidden");
    file.required = solo;
    document.getElementById("originalName").textContent = file.files[0]?.name || (solo ? "逐音评测必须选择参考音频" : "不上传也可分析");
    document.getElementById("referenceHint").textContent = solo
      ? (referenceKind.value === "mixed" ? "将先从混音中分离人声；分离或音高对齐不可靠时会明确显示不可评分，不会给出伪造的 0 分。" : "清晰单人示范会直接作为目标旋律；课堂录音与它分别作为被评测对象和目标旋律。")
      : (referenceKind.value === "vocal" ? "清晰单人示范会直接作为参考旋律。" : "原唱 / 伴奏混音会先分离人声；若无法可靠分离，会明确停在不可评分状态。");
  };
  document.getElementById("analysisMode").onchange = updateReferenceForm;
  document.getElementById("referenceKind").onchange = updateReferenceForm;
  updateReferenceForm();

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
    form.append("reference_kind", document.getElementById("referenceKind").value);
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
  window.addEventListener("audio-job:update", event => showJobState(event.detail));

  function showJobState(task) {
    const area = document.getElementById("analysis");
    if (!area || !task || task.status === "completed") return;
    const failed = task.status === "failed";
    const cancelled = task.status === "cancelled";
    area.innerHTML = `<section class="card analysis-progress ${failed ? "failed" : ""}" aria-live="polite"><div><span class="eyebrow">${failed ? "ANALYSIS ERROR" : "BACKGROUND ANALYSIS"}</span><h3>${failed ? "本次音频分析失败" : cancelled ? "本次音频分析已取消" : "正在分析这份录音"}</h3><p>${esc(task.stage || "正在准备")}</p>${failed ? `<p class="generation-error"><b>具体错误：</b>${esc(task.error_message || "后端未返回错误详情")}</p>` : ""}</div><div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(task.progress || 0)))}%"></i></div>${audioStepView(task)}${!failed && !cancelled ? `<div class="actions"><small>真实阶段：${esc(task.stage || "读取音频")}。你可留在本页等待，也可切换页面。</small><button class="btn soft" id="cancelAudioInPage">取消本次分析</button></div>` : ""}</section>`;
    area.querySelector("#cancelAudioInPage")?.addEventListener("click", async () => {
      try { await cancelActiveAudioJob(); } catch (error) { notify(error.message); }
    });
  }

  function showResult(result) {
    const area = document.getElementById("analysis");
    if (!area) return;
    area.innerHTML = resultView(result);
    const recordingWave = document.getElementById("recordingWave");
    if (recordingWave) drawWaveform(recordingWave, result.recording_waveform, "#547785");
    if (result.has_reference_comparison) drawWaveform(document.getElementById("referenceWave"), result.reference_waveform, "#9f4b35");
    document.getElementById("toFeedback")?.addEventListener("click", () => {
      localStorage.setItem("audioAnalysisForFeedback", JSON.stringify({ id: result.id }));
      window.dispatchEvent(new CustomEvent("app:navigate", { detail: "feedback" }));
    });
  }
}

function audioStepView(task) {
  const progress = Number(task.progress || 0);
  const labels = ["保存录音", "解码与校验格式", "提取音高、起音与节拍", "整理分段声学证据", "分离 / 对齐参考旋律", "汇总分析结果", "保存分析结果"];
  const points = [5, 10, 22, 38, 60, 88, 100];
  return `<ol class="job-step-list">${labels.map((label, index) => {
    const state = task.status === "failed" && progress < points[index] ? "pending" : progress >= points[index] ? "done" : "running";
    return `<li class="${state}"><i>${state === "done" ? "✓" : state === "running" ? "•" : "○"}</i>${label}</li>`;
  }).join("")}</ol>`;
}

function analysisProgress(message, progress) {
  return `<section class="card analysis-progress" aria-live="polite"><div><span class="eyebrow">BACKGROUND ANALYSIS</span><h3>音频分析正在后台运行</h3><p>${esc(message)}</p></div><div class="generation-progress"><i style="width:${progress}%"></i></div><small>进度来自后端实际阶段：保存音频 → 提取音高/节拍 → 计算指标 → 保存结果。</small></section>`;
}

function resultView(result) {
  if (!result.analysis_available) return `<section class="card notice"><h3>本次录音未能完成分析</h3><p>${esc(result.suggestions?.[0] || "请检查录音格式与内容")}</p></section>`;
  const player = `<section class="audio-player-card"><h3>回听本次录音</h3><p class="muted">${esc(result.recording_filename || "课堂录音")}</p><audio controls preload="metadata" src="${esc(apiUrl(result.recording_url))}"></audio>${result.reference_url ? `<p class="muted">参考音频：${esc(result.reference_filename || "参考旋律")}</p><audio controls preload="metadata" src="${esc(apiUrl(result.reference_url))}"></audio>` : ""}</section>`;
  const method = `<details class="method-details"><summary>查看本次分析的方法与边界</summary><ol>${(result.analysis_method || []).map(item => `<li>${esc(item)}</li>`).join("")}</ol></details>`;
  if (result.analysis_mode === "solo") return soloResultView(result, player, method);
  return classroomResultView(result, player, method);
}

function classroomResultView(result, player, method) {
  const scoreCards = Object.entries(result.scores || {}).map(([key, value]) => `<div><b>${value}</b><small>${scoreNames[key] || key}</small></div>`).join("");
  const evidence = result.classroom_evidence || {};
  const evidencePanel = evidence.summary ? `<section class="classroom-evidence"><span class="eyebrow">EVIDENCE SUMMARY</span><h3>课堂分析依据</h3><p>${esc(evidence.summary)}</p>${(evidence.limitations || []).map(item => `<small>${esc(item)}</small>`).join("")}</section>` : "";
  const findings = result.findings || [];
  const findingPanel = findings.length ? `<h3>按录音证据排出的本次优先动作</h3><div class="segment-list evidence-actions">${findings.map(item => `<div><b>${esc(item.priority)} · ${esc(item.time)}</b><span>${esc(item.metric)}</span><p class="segment-evidence">${esc(item.evidence)}</p><p>${esc(item.action)}</p></div>`).join("")}</div>` : "";
  const insight = result.model_insight || {};
  const modelPanel = insight.status === "ready" ? `<section class="model-insight"><div><span class="eyebrow">EVIDENCE-GROUNDED TEACHING REVIEW</span><h3>结合本课目标的教学解读</h3><p>${esc(insight.summary)}</p></div><small>模型仅解释下方已有的时间段与声学证据，不替代音准判定。</small><div class="model-insight-list">${(insight.priorities || []).map(item => `<article><b>${esc(item.time)} · ${esc(item.headline)}</b><p>${esc(item.interpretation)}</p><span><strong>下一步：</strong>${esc(item.action)}</span></article>`).join("")}</div></section>` : `<section class="model-insight muted-insight"><span class="eyebrow">TEACHING REVIEW STATUS</span><h3>模型教学解读暂不可用</h3><p>${esc(insight.message || "这是历史分析记录；重新提交一次课堂分析后，会生成基于分段证据的教学解读。")}</p></section>`;
  return `<section class="analysis-result"><div class="card"><div class="card-head"><div><span class="eyebrow">CLASSROOM EVIDENCE</span><h2>《${esc(result.song_name)}》课堂整体分析</h2><p class="muted">已保存 · 时长 ${result.duration_seconds} 秒 · 推测速度 ${result.tempo_bpm ?? "—"} BPM</p></div><span class="status ok">分析记录 #${result.id}</span></div><p class="analysis-scope">${esc(result.analysis_scope)}</p><div class="scores professional-scores">${scoreCards}</div>${evidencePanel}${player}${findingPanel}${modelPanel}<h3>分段关注点</h3><div class="segment-list">${(result.segment_feedback || []).map(item => `<div><b>${esc(item.time)}</b><span>${esc(item.focus)} · ${item.pitch_stability ?? "—"} 分</span><p class="segment-evidence">${esc(item.evidence || "")}</p><p>${esc(item.note)}</p></div>`).join("")}</div>${method}<button class="btn primary" id="toFeedback">将分析总结写入课堂反馈</button></div>${referenceView(result)}</section>`;
}

function readableReferenceFailure(message) {
  const text = String(message || "");
  // Older saved records may contain Demucs/tqdm's raw model-download output.
  // Keep it out of the teacher-facing card while preserving the concise cause.
  if (text.length > 320 || /(?:\d+%\|.*(?:kB\/s|MB\/s)|urlopen error|https?:\/\/|\d+\.\d+\/\d+\.\d+M)/i.test(text)) {
    return "混音参考的人声分离未完成，因此本次不生成逐音分数。请上传清晰单人参考人声，或检查后端 Demucs 模型下载日志后重试。";
  }
  return text || "参考旋律不可用；请检查参考类型和录音质量。";
}

function soloResultView(result, player, method) {
  const comparison = result.intonation_comparison || {};
  const note = result.note_assessment || {};
  const diagnostics = result.solo_diagnostics || {};
  const quality = diagnostics.recording_voiced_ratio;
  const reference = diagnostics.reference || {};
  const alignment = diagnostics.alignment || {};
  const hasPitchScore = Boolean(comparison.available || note.available);
  const recordingQuality = quality == null ? "—" : `${Math.round(quality * 100)}%`;
  const referenceLabel = reference.source === "demucs_vocals" ? "已分离出参考人声" : reference.source === "clean_vocal" ? "清晰单人参考人声" : reference.available === false ? "混音分离失败" : "待确认";
  const separationFailed = reference.available === false || referenceLabel === "混音分离失败";
  const diagnosticsPanel = `<section class="solo-check-panel"><div class="solo-check-heading"><span class="eyebrow">ASSESSMENT CHECK</span><h3>本次逐音评测条件</h3></div><div class="solo-check-grid"><div><small>练唱人声可用度 <span>（不是得分）</span></small><b>${recordingQuality}</b></div><div><small>参考主旋律来源</small><b>${esc(referenceLabel)}</b></div>${alignment.reference_voiced_ratio != null ? `<div><small>参考音频可用人声</small><b>${Math.round(alignment.reference_voiced_ratio * 100)}%</b></div><div><small>练唱对齐可用人声</small><b>${alignment.recording_voiced_ratio == null ? "—" : `${Math.round(alignment.recording_voiced_ratio * 100)}%`}</b></div>` : ""}</div></section>`;
  const noScoreCopy = separationFailed
    ? `练唱人声可用度 ${recordingQuality} 不是得分。参考文件是混音，但没有分离出可用的人声音轨，因此系统没有进行逐音对齐。可先上传清晰的单人参考人声；若要继续用混音，请检查后端 Demucs 分离日志后重试。`
    : readableReferenceFailure(note.message || comparison.message || reference.message);
  const referenceStatus = !hasPitchScore ? `<section class="solo-no-score"><div><span class="eyebrow">PITCH ASSESSMENT</span><h3>本次未生成逐音分数</h3></div><p>${esc(noScoreCopy)}</p></section>` : "";
  const comparisonCard = comparison.available ? `<section class="intonation-card"><div><span class="eyebrow">PITCH ALIGNMENT</span><h3>参考主旋律对齐</h3><p>${esc(comparison.message)}</p></div><div class="intonation-score"><b>${comparison.intonation_score}</b><span>${esc(comparison.status)}</span></div><div class="analysis-summary"><span>中位偏差 <b>${comparison.median_deviation_cents} cents</b></span><span>偏差帧 <b>${comparison.off_pitch_ratio}%</b></span></div></section>` : "";
  const noteAssessment = note.available ? `<section class="note-assessment"><div class="card-head"><div><span class="eyebrow">NOTE-BY-NOTE ASSESSMENT</span><h3>逐音结果</h3><p>${esc(note.message)}</p></div><div class="intonation-score"><b>${note.score}</b><span>逐音得分</span></div></div><div class="analysis-summary"><span>匹配音符 <b>${note.matched_notes}</b></span><span>±50 cents 命中 <b>${note.accurate_note_ratio}%</b></span><span>中位偏差 <b>${note.median_deviation_cents} cents</b></span></div><div class="note-table"><table><thead><tr><th>#</th><th>目标音</th><th>时间</th><th>偏差</th><th>判定</th></tr></thead><tbody>${(note.events || []).map(item => `<tr><td>${item.index}</td><td>${esc(item.expected_note)}</td><td>${item.start_seconds}–${item.end_seconds}s</td><td class="${Math.abs(item.deviation_cents) > 50 ? "off-pitch" : ""}">${item.deviation_cents > 0 ? "+" : ""}${item.deviation_cents} cents</td><td>${esc(item.status)}</td></tr>`).join("")}</tbody></table></div></section>` : "";
  return `<section class="analysis-result solo-analysis-result"><div class="card"><div class="card-head"><div><span class="eyebrow">SOLO VOICE ASSESSMENT</span><h2>《${esc(result.song_name)}》单人练唱逐音评测</h2><p class="muted">录音已保存 · ${hasPitchScore ? "逐音评测已完成" : "逐音评测未完成"} · 时长 ${result.duration_seconds} 秒 · 不使用课堂整体分数</p></div><span class="status ok">录音 #${result.id} 已保存</span></div><p class="analysis-scope">${esc(result.analysis_scope)}</p>${player}${diagnosticsPanel}${comparisonCard}${referenceStatus}${noteAssessment}${method}</div></section>`;
}

function referenceView(result) {
  if (!result.has_reference_comparison) return "";
  const solo = result.analysis_mode === "solo";
  const title = solo ? "参考旋律与我的练唱" : "参考音频与课堂录音";
  const note = solo ? "红色为可用于逐音评测的人声参考，蓝色为我的练唱；整体轮廓仅辅助查看，音准以逐音对齐结果为准。" : "仅反映整体能量轮廓相似度，不等同音准评分。";
  return `<section class="card reference-panel"><div class="card-head"><div><h3>${title}</h3><small>${note}</small></div><b class="reference-score">${result.reference_similarity ?? "—"}</b></div><div class="wave"><b>${esc(result.reference_waveform_label || "参考音频（红）")}</b><div id="referenceWave"></div></div><div class="wave"><b>${esc(result.recording_waveform_label || (solo ? "我的练唱（蓝）" : "课堂录音（蓝）"))}</b><div id="recordingWave"></div></div></section>`;
}
