import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";
import { loadLocalSoundfont, playSampledTracks, soundSourceLabel, stopSampledPlayback } from "../audio/sampled-playback.js";

const LABEL = { piano: "钢琴", violin: "小提琴", guzheng: "古筝", erhu: "二胡", guitar: "原声吉他", drum: "非洲鼓" };
const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const KEYS = Array.from({ length: 61 }, (_, i) => i + 36); // C2–C7
let audioContext, playing = [], current = null;
let importState = null;

function ensureWorkbenchStyle() {
  if (document.getElementById("workbench-refinement")) return;
  const style = document.createElement("style");
  style.id = "workbench-refinement";
  style.textContent = `
    .workbench-head { max-width: 1240px; margin: 0 auto 18px; }.workbench-head h1 { margin: 0 0 6px; }.workbench-head p { margin: 0; color: var(--muted); }.workbench-layout { max-width: 1240px; margin: 0 auto; }.composer-tabs { min-height: 38px; }.score-actions,.sample-pack-controls{display:flex;align-items:center;gap:8px}.sample-score,.file-import,.sample-file-button{display:inline-flex;align-items:center;justify-content:center;border:1px solid #dfc4b4;border-radius:10px;padding:9px 12px;background:#fffdfa;color:#9f4b35;font-size:.84rem;font-weight:750;text-decoration:none;cursor:pointer}.sample-score{color:#706159;border-color:#e6d9cf}.file-import:hover,.sample-file-button:hover{background:#fbefe7}.sample-file-button input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}.sample-file-button:focus-within,.file-import:focus-within{outline:3px solid rgba(191,100,70,.18);outline-offset:2px}.sample-pack{padding:13px 14px;background:#fffdf9}.sample-pack small{max-width:440px}.sample-pack-controls select{min-width:104px;margin:0}.sample-pack input[type=file]{width:1px}.composer-hint{margin-top:12px}.score-import-status{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 14px;align-items:center;margin:10px 0 14px;padding:10px 12px;border:1px solid #eadbd1;border-radius:12px;background:#fffaf5;color:#6d5d55}.score-import-status b{display:block;color:#8f4936;font-size:.88rem}.score-import-status small{display:block;margin-top:3px;color:#8f817a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.score-import-status>span{grid-column:2;grid-row:1/3;color:#a44f38;font-weight:800}.score-import-progress{grid-column:1;height:6px;overflow:hidden;border-radius:9px;background:#eadfd8}.score-import-progress i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#d7845c,#a84d36);transition:width .25s ease}.score-import-status.running .score-import-progress i{animation:score-progress-glow 1.2s ease-in-out infinite}.score-import-status.success{border-color:#c8dfd0;background:#f5fbf6}.score-import-status.success b,.score-import-status.success>span{color:#39734c}.score-import-status.error{border-color:#e7c3bb;background:#fff5f2}.score-import-status.error b,.score-import-status.error>span{color:#b14331}.workbench-project.loading{opacity:.6;cursor:wait}@keyframes score-progress-glow{50%{filter:brightness(1.18)}}@media(max-width:700px){.composer-tabs,.sample-pack{align-items:flex-start;flex-direction:column}.score-actions,.sample-pack-controls{width:100%}.file-import,.sample-file-button{flex:1}.workbench-layout{margin:0}.score-import-status{grid-template-columns:minmax(0,1fr) 42px}.score-import-status>span{font-size:.8rem}}
  `;
  document.head.append(style);
}

const noteName = pitch => `${NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
const isBlack = pitch => [1, 3, 6, 8, 10].includes(pitch % 12);
function tokenPitch(token) {
  const m = String(token).trim().match(/^([A-Ga-g])([#♯b♭]?)([0-8])$/); if (!m) return null;
  const base = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1].toUpperCase()];
  return (Number(m[3]) + 1) * 12 + base + (["#", "♯"].includes(m[2]) ? 1 : ["b", "♭"].includes(m[2]) ? -1 : 0);
}
function textMelody(text, tempo = 96) { const beat = 60 / tempo; return String(text || "").split(/[\s,，]+/).map(tokenPitch).filter(Number.isFinite).map((pitch, i) => ({ pitch, start: +(i * beat).toFixed(3), duration: +(beat * .88).toFixed(3), velocity: 92 })); }
function notesText(notes) { return (notes || []).sort((a, b) => a.start - b.start || a.pitch - b.pitch).map(n => noteName(Number(n.pitch))).join(" "); }

function staff(notes, title) {
  const safe = (notes || []).slice(0, 64), width = Math.max(610, 94 + safe.length * 30);
  const lines = [35, 51, 67, 83, 99].map(y => `<line x1="48" y1="${y}" x2="${width - 18}" y2="${y}"/>`).join("");
  const marks = safe.map((n, i) => { const x = 78 + i * 30, y = Math.max(15, Math.min(119, 99 - (n.pitch - 60) * 4)), up = n.pitch < 71; return `<g class="staff-note"><ellipse cx="${x}" cy="${y}" rx="7" ry="5" transform="rotate(-18 ${x} ${y})"/><line x1="${x + (up ? 6 : -6)}" y1="${y}" x2="${x + (up ? 6 : -6)}" y2="${y + (up ? -31 : 31)}"/></g>`; }).join("");
  return `<div class="staff-caption"><b>${title}</b><span>${safe.length ? `${safe.length} 个音符 · 4/4` : "从键盘、卷帘或乐谱开始"}</span></div><div class="staff-scroll"><svg class="music-staff" viewBox="0 0 ${width} 144"><text class="staff-clef" x="17" y="94">𝄞</text><text class="staff-meter" x="51" y="60">4</text><text class="staff-meter" x="51" y="88">4</text>${lines}${marks || '<text class="staff-empty" x="95" y="72">从键盘、卷帘或乐谱开始</text>'}</svg></div>`;
}
function keyboard() {
  const whites = KEYS.filter(p => !isBlack(p));
  return `<div class="keyboard-scroll"><div class="virtual-keyboard" style="--white-count:${whites.length}">${whites.map(p => `<button class="key white" data-key="${p}" title="${noteName(p)}"><b>${p % 12 === 0 ? noteName(p) : ""}</b></button>${KEYS.includes(p + 1) && isBlack(p + 1) ? `<button class="key black" data-key="${p + 1}" title="${noteName(p + 1)}"></button>` : ""}`).join("")}</div></div>`;
}
function pianoRoll(notes) {
  const pitches = Array.from({ length: 25 }, (_, i) => 72 - i), steps = Array.from({ length: 16 }, (_, i) => i), active = new Set((notes || []).map(n => `${n.pitch}:${Math.round(n.start / .625)}`));
  return `<section class="piano-roll"><div class="roll-head"><b>钢琴卷帘编辑</b><span>点击格子添加/删除八分音符 · 4 小节</span></div><div class="roll-grid"><div class="roll-labels">${pitches.map(p => `<span>${p % 12 === 0 ? noteName(p) : ""}</span>`).join("")}</div><div class="roll-cells">${pitches.map(p => `<div class="roll-row">${steps.map(s => `<button class="roll-cell ${active.has(`${p}:${s}`) ? "active" : ""}" data-roll-pitch="${p}" data-roll-step="${s}" title="${noteName(p)}"></button>`).join("")}</div>`).join("")}</div></div></section>`;
}

function stop() { playing.forEach(node => { try { node.stop(); } catch (_) {} }); playing = []; stopSampledPlayback(); }
function tone(instrument, note, when, duration, volume = 1) {
  const ctx = audioContext || (audioContext = new AudioContext()), freq = instrument === "drum" ? (note.pitch === 36 ? 92 : 170) : 440 * Math.pow(2, (note.pitch - 69) / 12), gain = ctx.createGain();
  const sustained = ["violin", "erhu"].includes(instrument), attack = sustained ? .09 : .012, release = sustained ? Math.max(.12, duration * .96) : Math.max(.08, duration * .76), amplitude = (instrument === "drum" ? .13 : .08) * volume;
  gain.gain.setValueAtTime(.0001, when); gain.gain.exponentialRampToValueAtTime(amplitude, when + attack); gain.gain.exponentialRampToValueAtTime(.0001, when + release);
  const shapes = instrument === "piano" ? [["sine", 1, 1], ["triangle", 2, .22]] : instrument === "guzheng" ? [["triangle", 1, 1], ["sine", 2.01, .38]] : instrument === "guitar" ? [["triangle", 1, 1], ["sine", 2, .18], ["sine", 3, .08]] : instrument === "violin" ? [["sawtooth", 1, .7], ["triangle", 2, .22]] : instrument === "erhu" ? [["triangle", 1, .82], ["sawtooth", 1.01, .17]] : [["square", 1, 1]];
  const nodes = shapes.map(([type, ratio, level]) => { const osc = ctx.createOscillator(), part = ctx.createGain(); osc.type = type; osc.frequency.setValueAtTime(freq * ratio, when); part.gain.value = level; osc.connect(part).connect(gain); osc.start(when); osc.stop(when + Math.max(.09, duration)); return osc; });
  if (sustained) { const lfo = ctx.createOscillator(), depth = ctx.createGain(); lfo.frequency.value = instrument === "erhu" ? 5.2 : 5.8; depth.gain.value = 5; lfo.connect(depth); nodes.forEach(osc => depth.connect(osc.detune)); lfo.start(when); lfo.stop(when + duration); nodes.push(lfo); }
  gain.connect(ctx.destination); playing.push(...nodes);
}
function metronome(ctx, when, tempo, beats) { for (let i = 0; i < beats; i++) tone("drum", { pitch: i % 4 === 0 ? 36 : 42 }, when + i * 60 / tempo, .07, i % 4 === 0 ? .45 : .25); }
async function playTracks(tracks, muted = new Set(), volume = {}, options = {}) {
  stop(); if (!tracks?.length) return notify("请先写入旋律", "error");
  const ctx = audioContext || (audioContext = new AudioContext()); await ctx.resume?.(); const now = ctx.currentTime + .08;
  if (options.metronome) metronome(ctx, now, options.tempo || 96, options.beats || 16);
  try {
    const result = await playSampledTracks(tracks, { muted, volume, onProgress: ({ instrument, loaded, total }) => {
      const status = document.querySelector("#sampleLoadStatus"); if (status) status.textContent = `正在加载${LABEL[instrument] || instrument}采样 ${loaded}/${total}`;
    } });
    const status = document.querySelector("#sampleLoadStatus"); if (status) status.textContent = "真实采样已就绪";
    const fallback = result.failed || [];
    // 标准采样加载失败（离线、CDN 被拦截或某个 SF2 不兼容）时，保留可听的本地合成试听。
    // 每条失败轨独立回退，不能让一份坏 SF2 静音整首作品或电子钢琴。
    fallback.forEach(({ track }) => {
      const gain = Math.max(0, Math.min(1, Number(volume[track.id] ?? 1)));
      (track.notes || []).forEach(note => tone(track.instrument, note, Math.max(now, ctx.currentTime + .02) + Number(note.start || 0), Math.max(.06, Number(note.duration || .2)), gain));
    });
    if (fallback.length) {
      const names = [...new Set(fallback.map(item => LABEL[item.track.instrument] || item.track.instrument))].join("、");
      if (status) status.textContent = `采样暂不可用，已用本地试听音色播放：${names}`;
      notify(`部分真实采样未加载，已继续播放本地试听音色：${names}`);
    } else if (status) status.textContent = "真实采样已就绪";
    if (result.unavailable.length) notify(`${result.unavailable.map(id => LABEL[id] || id).join("、")}没有可用音源，已跳过该轨；请在“传统音色包”导入对应 .sf2。`, "error");
  } catch (error) {
    // AudioContext 被浏览器拒绝等基础错误才会走到这里；仍尽量保留键盘试听。
    const status = document.querySelector("#sampleLoadStatus"); if (status) status.textContent = "浏览器音频启动失败";
    notify(`无法启动浏览器音频：${error.message}`, "error");
  }
}
function projectCard(p) { return `<button class="workbench-project ${current?.id === p.id ? "active" : ""}" data-project="${p.id}"><b>${esc(p.title)}</b><small>${esc(p.style)} · ${p.tempo} BPM</small></button>`; }
function importStatusView() {
  if (!importState) return '<div id="scoreImportStatus" class="score-import-status" aria-live="polite"></div>';
  const icon = importState.kind === "success" ? "✓" : importState.kind === "error" ? "!" : "…";
  return `<div id="scoreImportStatus" class="score-import-status ${importState.kind || "running"}" aria-live="polite"><div><b>${icon} ${esc(importState.phase)}</b><small>${esc(importState.fileName || "")}</small></div><div class="score-import-progress"><i style="width:${Math.max(0, Math.min(100, Number(importState.progress || 0)))}%"></i></div><span>${Math.round(Number(importState.progress || 0))}%</span></div>`;
}
function setImportState(root, next) {
  importState = next;
  const old = root.querySelector("#scoreImportStatus");
  if (!old) return;
  const holder = document.createElement("div");
  holder.innerHTML = importStatusView();
  old.replaceWith(holder.firstElementChild);
}
function stage(project) {
  if (!project) return `<div class="workbench-empty"><b>从一段旋律开始</b><p>先点击完整电子钢琴、钢琴卷帘，或导入 MusicXML/MIDI/清晰五线谱图片。完成后会生成可以单独试听、静音和调音量的多轨工程。</p></div>`;
  const tracks = project.arrangement?.tracks || [];
  const chordLabels = project.arrangement?.chord_labels || [];
  const chords = chordLabels.length ? `<section class="chord-timeline" aria-label="本曲和弦走向"><div><b>本曲和弦走向</b><span>按每小节主旋律匹配，可作为课堂核验依据</span></div><ol>${chordLabels.map((label, index) => `<li><small>第 ${index + 1} 小节</small><b>${esc(label)}</b></li>`).join("")}</ol></section>` : "";
  return `<section class="workbench-stage"><div class="stage-heading"><div><span>当前工程 · ${project.tempo} BPM · ${esc(project.arrangement?.key || "待推断")}</span><h2>${esc(project.title)}</h2><p>${esc(project.arrangement?.tips || "正在等待生成声部")}</p></div><div class="stage-actions"><button class="button ghost" id="stopArrangement">停止</button><button class="button" id="playArrangement">▶ 从头播放</button></div></div>${chords}<section class="score-panel">${staff(project.melody, "主旋律五线谱 · 已同步到工程")}</section><div class="track-list">${tracks.map(t => `<article class="music-track"><div class="track-icon">${t.instrument === "drum" ? "◉" : "♫"}</div><div><b>${esc(t.name)}</b><small>${esc(soundSourceLabel(t.instrument))} · ${t.notes.length} 个音符</small></div><label class="track-volume"><span>音量</span><input type="range" data-volume="${t.id}" min="0" max="100" value="82"></label><label class="track-mute"><input type="checkbox" data-mute="${t.id}"> 静音</label><button class="track-preview" data-preview-track="${t.id}">试听</button></article>`).join("")}</div></section>`;
}

export async function renderWorkbench(root) {
  ensureWorkbenchStyle();
  const projects = await api.workbenchProjects();
  // 侧栏接口只返回轻量摘要；当前工程才按需取完整音符和多轨数据。
  // 这避免工程数量增加后每次点击都传回、解码并渲染全部声部。
  const hasCurrent = current && projects.some(project => project.id === current.id);
  if (!hasCurrent) current = projects.length ? await api.workbenchProject(projects[0].id) : null;
  const melody = notesText(current?.melody), tempo = current?.tempo || 96;
  const chosenInstruments = current?.arrangement?.instruments || ["piano", "guzheng", "drum"];
  root.innerHTML = `<div class="page-head workbench-head"><div><h1>数字乐器与编曲工作台</h1><p>写旋律、导入乐谱、试听多轨。</p></div></div><div class="workbench-layout"><aside class="project-rail"><div class="rail-title"><b>我的编曲工程</b><span>${projects.length}</span></div><div id="projectList">${projects.map(projectCard).join("") || '<p class="muted">还没有工程</p>'}</div></aside><div class="workbench-main"><section class="composer-card"><div class="composer-tabs"><b>乐谱与旋律</b><div class="score-actions"><a class="sample-score" href="/assets/samples/score-import-test.musicxml" download>下载示例</a><label class="file-import">导入乐谱 <input id="scoreUpload" type="file" accept=".musicxml,.xml,.mxl,.mid,.midi,.png,.jpg,.jpeg,.webp,.tif,.tiff,.pdf"></label></div></div>${importStatusView()}<div class="composer-fields"><input id="arrangementTitle" value="${esc(current?.title || "我的乡村音乐作品")}" placeholder="工程名称"><input id="melodyText" value="${esc(melody)}" placeholder="例如 C4 D4 E4 G4 A4"><label class="tempo-box"><span>BPM</span><input id="tempo" type="number" min="40" max="220" value="${tempo}"></label></div><div class="transport-bar"><button id="playMelody">▶ 试听旋律</button><button id="stopMelody">■</button><label>键盘音色 <select id="keyboardTimbre">${Object.entries(LABEL).filter(([id]) => id !== "drum").map(([id, name]) => `<option value="${id}">${name}</option>`).join("")}</select></label><label><input id="metronome" type="checkbox"> 节拍器</label><span>4/4 · 16 格编辑区</span></div><div class="sample-pack"><div><b>传统乐器音色</b><small id="sampleLoadStatus">选择古筝、二胡或非洲鼓的 .sf2 音色包</small></div><div class="sample-pack-controls"><select id="samplePackInstrument" aria-label="选择乐器"><option value="guzheng">古筝</option><option value="erhu">二胡</option><option value="drum">非洲鼓</option></select><label class="sample-file-button">选择 .sf2<input id="samplePackUpload" type="file" accept=".sf2"></label></div></div><section class="notation-workspace"><div id="notationPreview">${staff(current?.melody || [], "输入旋律预览")}</div><div id="rollMount">${pianoRoll(current?.melody || [])}</div><div class="keyboard-head"><div><b>完整电子钢琴 · C2–C7</b><span>键位总是钢琴音高；音色选择只改变试听声音</span></div><div><button class="link" id="clearMelody">清空旋律</button><button class="link" id="resetComposer">重置工程</button></div></div>${keyboard()}</section><div class="arrange-controls"><div class="style-pills" id="stylePills">${["乡土抒情", "欢快律动", "童谣清新", "器乐合奏"].map((x, i) => `<button data-style="${x}" class="${(!current && i === 0) || current?.style === x ? "selected" : ""}">${x}</button>`).join("")}</div><div class="instrument-pills" id="instrumentPills">${Object.entries(LABEL).map(([id, name]) => `<label><input type="checkbox" value="${id}" ${chosenInstruments.includes(id) ? "checked" : ""}> ${name}</label>`).join("")}</div><button class="button" id="makeArrangement">✦ 生成 / 更新多轨编曲</button></div><p class="composer-hint">勾选乐器后生成各自声部。</p></section><div id="stage">${stage(current)}</div></div></div>`;

  const melodyInput = root.querySelector("#melodyText"), tempoInput = root.querySelector("#tempo");
  const getNotes = () => textMelody(melodyInput.value, +tempoInput.value || 96);
  const bindRoll = () => root.querySelectorAll("[data-roll-pitch]").forEach(cell => cell.onclick = () => { const notes = getNotes(), pitch = +cell.dataset.rollPitch, start = +(+cell.dataset.rollStep * .625).toFixed(3), found = notes.findIndex(n => n.pitch === pitch && Math.abs(n.start - start) < .32); if (found >= 0) notes.splice(found, 1); else notes.push({ pitch, start, duration: .52, velocity: 92 }); melodyInput.value = notesText(notes); refresh(); });
  const refresh = () => { const notes = getNotes(); root.querySelector("#notationPreview").innerHTML = staff(notes, "输入旋律预览"); root.querySelector("#rollMount").innerHTML = pianoRoll(notes); bindRoll(); };
  bindRoll();
  root.querySelectorAll("[data-project]").forEach(b => b.onclick = async () => {
    const id = b.dataset.project;
    if (String(current?.id) === String(id)) return;
    root.querySelectorAll("[data-project]").forEach(item => item.disabled = true);
    b.classList.add("loading");
    try { current = await api.workbenchProject(id); await renderWorkbench(root); }
    catch (error) { notify(`打开工程失败：${error.message}`, "error"); root.querySelectorAll("[data-project]").forEach(item => item.disabled = false); b.classList.remove("loading"); }
  });
  root.querySelector("#scoreUpload").onchange = async e => {
    const file = e.target.files[0]; if (!file) return;
    const form = new FormData(); form.append("file", file);
    setImportState(root, { kind: "running", fileName: file.name, phase: "准备上传乐谱", progress: 0 });
    try {
      current = await api.importScore(form, update => setImportState(root, { kind: "running", fileName: file.name, ...update }));
      importState = { kind: "success", fileName: file.name, phase: current.import_notice || "导入成功，已载入钢琴卷帘", progress: 100 };
      await renderWorkbench(root);
    } catch (err) {
      setImportState(root, { kind: "error", fileName: file.name, phase: `导入失败：${err.message}`, progress: 100 });
      notify(`导入失败：${err.message}`, "error");
    } finally { e.target.value = ""; }
  };
  root.querySelector("#samplePackUpload").onchange = async e => { const file = e.target.files[0]; if (!file) return; const instrument = root.querySelector("#samplePackInstrument").value, status = root.querySelector("#sampleLoadStatus"); status.textContent = `正在读取 ${file.name}…`; try { const name = await loadLocalSoundfont(instrument, file, ({ loaded, total }) => { status.textContent = `正在读取 ${LABEL[instrument]}音源 ${loaded}/${total}`; }); status.textContent = `${LABEL[instrument]}已绑定 ${name}（仅本浏览器当前会话）`; notify(`${LABEL[instrument]}真实音源已导入；重新打开页面后需再次选择。`); } catch (error) { status.textContent = "音源包导入失败"; notify(`音源包导入失败：${error.message}`, "error"); } finally { e.target.value = ""; } };
  melodyInput.oninput = refresh; tempoInput.onchange = refresh;
  root.querySelector("#clearMelody").onclick = () => { melodyInput.value = ""; refresh(); };
  root.querySelector("#resetComposer").onclick = () => { current = null; renderWorkbench(root); };
  root.querySelectorAll("[data-key]").forEach(b => b.onclick = async () => { await playTracks([{ id: "keyboard", instrument: root.querySelector("#keyboardTimbre").value, notes: [{ pitch: +b.dataset.key, start: 0, duration: .38, velocity: 90 }] }]); melodyInput.value = `${melodyInput.value.trim()} ${noteName(+b.dataset.key)}`.trim(); refresh(); });
  root.querySelector("#playMelody").onclick = () => { const notes = getNotes(); if (!notes.length) return notify("请先输入至少一个音符", "error"); playTracks([{ id: "melody", instrument: root.querySelector("#keyboardTimbre").value, notes }], new Set(), {}, { metronome: root.querySelector("#metronome").checked, tempo: +tempoInput.value, beats: Math.max(4, notes.length) }); };
  root.querySelector("#stopMelody").onclick = stop;
  root.querySelectorAll("#stylePills button").forEach(b => b.onclick = () => { root.querySelectorAll("#stylePills button").forEach(x => x.classList.remove("selected")); b.classList.add("selected"); });
  root.querySelector("#makeArrangement").onclick = async () => { try { const notes = getNotes(); if (!notes.length) return notify("请输入旋律，或先导入 MusicXML / MIDI 乐谱", "error"); const data = { tempo: +tempoInput.value, style: root.querySelector("#stylePills .selected")?.dataset.style || "乡土抒情", instruments: [...root.querySelectorAll("#instrumentPills input:checked")].map(x => x.value), melody: notes }; current = current ? await api.arrangeProject(current.id, data) : await api.createWorkbenchProject({ title: root.querySelector("#arrangementTitle").value.trim() || "未命名编曲", ...data }); if (!current.arrangement?.tracks?.length) current = await api.arrangeProject(current.id, data); notify("已保存主旋律并更新多轨编曲"); renderWorkbench(root); } catch (err) { notify(err.message, "error"); } };
  const playArrangementButton = root.querySelector("#playArrangement");
  if (playArrangementButton) playArrangementButton.onclick = () => { const muted = new Set([...root.querySelectorAll("[data-mute]:checked")].map(x => x.dataset.mute)); const volumes = Object.fromEntries([...root.querySelectorAll("[data-volume]")].map(x => [x.dataset.volume, +x.value / 100])); playTracks(current.arrangement.tracks, muted, volumes); };
  const stopArrangementButton = root.querySelector("#stopArrangement");
  if (stopArrangementButton) stopArrangementButton.onclick = stop;
  root.querySelectorAll("[data-preview-track]").forEach(b => b.onclick = () => { const track = current.arrangement.tracks.find(t => String(t.id) === b.dataset.previewTrack); if (track) playTracks([track]); });
}
