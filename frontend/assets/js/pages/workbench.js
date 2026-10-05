import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";
import { activateLocalSoundfont, listLocalSoundfonts, loadLocalSoundfont, playSampledTracks, previewLocalSoundfont, removeLocalSoundfont, soundSourceLabel, stopSampledPlayback, updateLocalSoundfont } from "../audio/sampled-playback.js";

const LABEL = { piano: "钢琴", violin: "小提琴", guzheng: "古筝", erhu: "二胡", guitar: "原声吉他", drum: "非洲鼓" };
const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const KEYS = Array.from({ length: 61 }, (_, i) => i + 36); // C2–C7
let audioContext, playing = [], current = null;
let importState = null;
let soundfontPacks = [];
let draftNotes = null;
let draftProjectId = null;

function ensureWorkbenchStyle() {
  if (document.getElementById("workbench-refinement")) return;
  const style = document.createElement("style");
  style.id = "workbench-refinement";
  style.textContent = `
    .workbench-head { max-width: 1240px; margin: 0 auto 18px; }.workbench-head h1 { margin: 0 0 6px; }.workbench-head p { margin: 0; color: var(--muted); }.workbench-layout { max-width: 1240px; margin: 0 auto; }.composer-tabs { min-height: 38px; }.score-actions,.sample-pack-controls{display:flex;align-items:center;gap:8px}.sample-score,.file-import,.sample-file-button{display:inline-flex;align-items:center;justify-content:center;border:1px solid #dfc4b4;border-radius:10px;padding:9px 12px;background:#fffdfa;color:#9f4b35;font-size:.84rem;font-weight:750;text-decoration:none;cursor:pointer}.sample-score{color:#706159;border-color:#e6d9cf}.file-import:hover,.sample-file-button:hover{background:#fbefe7}.sample-file-button input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}.sample-file-button:focus-within,.file-import:focus-within{outline:3px solid rgba(191,100,70,.18);outline-offset:2px}.sample-pack{padding:13px 14px;background:#fffdf9}.sample-pack small{max-width:440px}.sample-pack-controls select{min-width:104px;margin:0}.sample-pack input[type=file]{width:1px}.composer-hint{margin-top:12px}.score-import-status{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 14px;align-items:center;margin:10px 0 14px;padding:10px 12px;border:1px solid #eadbd1;border-radius:12px;background:#fffaf5;color:#6d5d55}.score-import-status b{display:block;color:#8f4936;font-size:.88rem}.score-import-status small{display:block;margin-top:3px;color:#8f817a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.score-import-status>span{grid-column:2;grid-row:1/3;color:#a44f38;font-weight:800}.score-import-progress{grid-column:1;height:6px;overflow:hidden;border-radius:9px;background:#eadfd8}.score-import-progress i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#d7845c,#a84d36);transition:width .25s ease}.score-import-status.running .score-import-progress i{animation:score-progress-glow 1.2s ease-in-out infinite}.score-import-status.success{border-color:#c8dfd0;background:#f5fbf6}.score-import-status.success b,.score-import-status.success>span{color:#39734c}.score-import-status.error{border-color:#e7c3bb;background:#fff5f2}.score-import-status.error b,.score-import-status.error>span{color:#b14331}.workbench-project.loading{opacity:.6;cursor:wait}.composer-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #eadfd8;padding-bottom:14px}.composer-tabs>b{font-size:1.05rem}.score-format-hint{margin:10px 0 0;color:#7f7068;font-size:.82rem}.transport-panel{margin:16px 0;padding:16px;border:1px solid #eadbd1;border-radius:16px;background:linear-gradient(120deg,#fffdf9,#fcf6ef)}.transport-label{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:12px}.transport-label span{font-size:.84rem;color:#7f7068}.transport-bar{display:flex!important;flex-wrap:wrap;align-items:center;gap:10px}.transport-bar button,.transport-bar select,.transport-bar input{min-height:38px}.transport-bar label{display:flex;align-items:center;gap:7px;margin:0;white-space:nowrap}.meter-controls{display:flex;align-items:center;gap:7px;padding:5px 9px;border:1px solid #e6d9cf;border-radius:10px;background:#fff}.meter-controls select{min-width:74px}.metronome-toggle{padding:8px 10px;border:1px solid #e6d9cf;border-radius:10px;background:#fff}.piano-roll{max-height:520px;overflow:auto;border:1px solid #eadbd1;border-radius:14px;background:#fffdf9}.roll-head{position:sticky;top:0;z-index:4;display:flex;justify-content:space-between;padding:12px 14px;background:#fffdf9;border-bottom:1px solid #eadbd1}.roll-grid{min-width:max-content}.roll-labels{position:sticky;left:0;z-index:3;background:#fffdf9}.roll-labels span{height:22px;display:block;padding:0 8px;font-size:.72rem;color:#77655b;border-bottom:1px solid #f1e8e0}.roll-cells{display:block}.roll-row{height:22px;display:flex;border-bottom:1px solid #f1e8e0}.roll-cell{width:22px;min-width:22px;height:22px;padding:0;border:0;border-right:1px solid #f1e8e0;background:#fff}.roll-cell:nth-child(4n+1){border-left:1px solid #d9b5a4}.roll-cell.active{background:#b9583d}.roll-cell:hover{background:#f2cfbd}.roll-row:nth-child(12n+1){border-top:1px solid #c9896e}.roll-meter{font-size:.8rem;color:#7f7068}.soundfont-card{display:flex;justify-content:space-between;gap:14px;padding:13px 0;border-bottom:1px solid #efe4dc}.soundfont-card-main{display:flex;gap:10px}.soundfont-card-main small{display:block;margin-top:3px}.soundfont-card input[type=text]{max-width:220px;margin-top:8px}.soundfont-actions{display:flex;align-items:start;gap:8px;flex-wrap:wrap}.soundfont-edit{display:grid;grid-template-columns:auto 1fr;gap:6px 10px;align-items:center;margin-top:9px;color:#76665d;font-size:.8rem}.soundfont-edit .soundfont-bind-options{display:flex;flex-wrap:wrap;gap:7px}.soundfont-edit label{white-space:nowrap}.notation-workspace{margin-top:16px}.keyboard-scroll{overflow-x:auto;padding-bottom:6px}.virtual-keyboard{min-width:960px}.score-import-status.empty{display:none}.staff-clef.bass{font-size:40px}.staff-system{margin-bottom:12px}@keyframes score-progress-glow{50%{filter:brightness(1.18)}}@media(max-width:700px){.composer-tabs,.sample-pack{align-items:flex-start;flex-direction:column}.score-actions,.sample-pack-controls{width:100%}.file-import,.sample-file-button{flex:1}.workbench-layout{margin:0}.score-import-status{grid-template-columns:minmax(0,1fr) 42px}.score-import-status>span{font-size:.8rem}.transport-label{display:block}.transport-label span{display:block;margin-top:5px}.soundfont-card{display:block}.soundfont-actions{margin-top:10px}}
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

function meterOf(project = current) {
  const arrangement = project?.arrangement || {};
  return { numerator: Number(arrangement.meter_numerator || 4), division: Number(arrangement.grid_division || 4), bars: Number(arrangement.bars || 4) };
}
function staff(notes, title, meter = meterOf()) {
  const safe = (notes || []).slice(0, 96), width = Math.max(650, 116 + safe.length * 26);
  const makeSystem = (clef, base, yOffset, filter) => {
    const lines = [0, 1, 2, 3, 4].map(i => `<line x1="72" y1="${yOffset + 30 + i * 12}" x2="${width - 18}" y2="${yOffset + 30 + i * 12}"/>`).join("");
    const marks = safe.filter(filter).map((n, i) => { const x = 116 + i * 26, raw = yOffset + base - (n.pitch - 60) * 3, y = Math.max(yOffset + 5, Math.min(yOffset + 107, raw)), stemUp = n.pitch < 71; const ledger = n.pitch < 50 || n.pitch > 76 ? `<line x1="${x-10}" y1="${y}" x2="${x+10}" y2="${y}"/>` : ""; return `<g class="staff-note">${ledger}<ellipse cx="${x}" cy="${y}" rx="6" ry="4.5" transform="rotate(-18 ${x} ${y})"/><line x1="${x + (stemUp ? 5 : -5)}" y1="${y}" x2="${x + (stemUp ? 5 : -5)}" y2="${y + (stemUp ? -26 : 26)}"/></g>`; }).join("");
    return `<g>${lines}<text class="staff-clef ${clef === "𝄢" ? "bass" : ""}" x="24" y="${yOffset + 82}">${clef}</text>${marks}</g>`;
  };
  const treble = makeSystem("𝄞", 82, 0, n => n.pitch >= 60);
  const bass = makeSystem("𝄢", 132, 118, n => n.pitch < 60);
  return `<div class="staff-caption"><b>${title}</b><span>${safe.length ? `${safe.length} 个音符 · ${meter.numerator}/4 · ${meter.bars} 小节` : "从键盘、卷帘或乐谱开始"}</span></div><div class="staff-scroll"><svg class="music-staff" viewBox="0 0 ${width} 236"><text class="staff-meter" x="77" y="58">${meter.numerator}</text><text class="staff-meter" x="77" y="82">4</text><text class="staff-meter" x="77" y="176">${meter.numerator}</text><text class="staff-meter" x="77" y="200">4</text>${treble}${bass}${safe.length ? "" : '<text class="staff-empty" x="118" y="74">从键盘、卷帘或乐谱开始</text>'}</svg></div>`;
}
function keyboard() {
  const whites = KEYS.filter(p => !isBlack(p));
  return `<div class="keyboard-scroll"><div class="virtual-keyboard" style="--white-count:${whites.length}">${whites.map(p => `<button class="key white" data-key="${p}" title="${noteName(p)}"><b>${p % 12 === 0 ? noteName(p) : ""}</b></button>${KEYS.includes(p + 1) && isBlack(p + 1) ? `<button class="key black" data-key="${p + 1}" title="${noteName(p + 1)}"></button>` : ""}`).join("")}</div></div>`;
}
function pianoRoll(notes, tempo, meter) {
  const pitches = Array.from({ length: 61 }, (_, i) => 96 - i), stepSeconds = 60 / tempo / meter.division;
  const steps = Array.from({ length: meter.bars * meter.numerator * meter.division }, (_, i) => i);
  const active = new Set((notes || []).map(n => `${n.pitch}:${Math.round(n.start / stepSeconds)}`));
  return `<section class="piano-roll"><div class="roll-head"><b>钢琴卷帘编辑 · C2–C7</b><span class="roll-meter">${meter.bars} 小节 · ${meter.numerator}/4 · 每拍 ${meter.division} 格 · 可上下滚动</span></div><div class="roll-grid"><div class="roll-labels">${pitches.map(p => `<span>${p % 12 === 0 ? noteName(p) : ""}</span>`).join("")}</div><div class="roll-cells">${pitches.map(p => `<div class="roll-row">${steps.map(s => `<button class="roll-cell ${active.has(`${p}:${s}`) ? "active" : ""}" data-roll-pitch="${p}" data-roll-step="${s}" title="${noteName(p)} · 第 ${Math.floor(s/(meter.numerator*meter.division))+1} 小节"></button>`).join("")}</div>`).join("")}</div></div></section>`;
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
function metronome(ctx, when, tempo, beats, meter = 4) { for (let i = 0; i < beats; i++) tone("drum", { pitch: i % meter === 0 ? 36 : 42 }, when + i * 60 / tempo, .07, i % meter === 0 ? .45 : .25); }
async function playTracks(tracks, muted = new Set(), volume = {}, options = {}) {
  stop(); if (!tracks?.length) return notify("请先写入旋律", "error");
  const ctx = audioContext || (audioContext = new AudioContext()); await ctx.resume?.(); const now = ctx.currentTime + .08;
  if (options.metronome) metronome(ctx, now, options.tempo || 96, options.beats || 16, options.meter || 4);
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
    if (result.unavailable.length) notify(`${result.unavailable.map(id => LABEL[id] || id).join("、")}没有可用音源，已跳过该轨；请在“乐器音色包”导入对应 .sf2。`, "error");
  } catch (error) {
    // AudioContext 被浏览器拒绝等基础错误才会走到这里；仍尽量保留键盘试听。
    const status = document.querySelector("#sampleLoadStatus"); if (status) status.textContent = "浏览器音频启动失败";
    notify(`无法启动浏览器音频：${error.message}`, "error");
  }
}
function projectCard(p) { return `<button class="workbench-project ${current?.id === p.id ? "active" : ""}" data-project="${p.id}"><b>${esc(p.title)}</b><small>${esc(p.style)} · ${p.tempo} BPM</small></button>`; }
function formatBytes(size) { return `${Math.max(1, Math.round(Number(size || 0) / 1024 / 1024 * 10) / 10)} MB`; }
function sampleLibrary(packs) {
  const selectable = ["guzheng", "erhu", "guitar", "violin", "drum"];
  const cards = packs.length ? packs.map(pack => `<article class="soundfont-card" data-pack-card="${esc(pack.id)}">
    <div class="soundfont-card-main"><div class="soundfont-file-icon">♫</div><div><b>${esc(pack.displayName || pack.name)}</b><small>本机已保存 · ${formatBytes(pack.size)} · 文件：${esc(pack.name)} · Preset：${esc(pack.presetName || "已解析")}</small><div class="soundfont-tags">${(pack.instruments || []).map(id => `<span>${esc(LABEL[id] || id)}${pack.activeFor?.includes(id) ? " · 当前" : ""}</span>`).join("")}</div>
      <div class="soundfont-edit"><span>显示名称</span><input data-pack-name="${esc(pack.id)}" value="${esc(pack.displayName || pack.name.replace(/\.sf2$/i, ""))}" maxlength="80"><span>绑定乐器</span><div class="soundfont-bind-options">${selectable.map(id => `<label><input type="checkbox" data-pack-instrument="${esc(pack.id)}" value="${id}" ${(pack.instruments || []).includes(id) ? "checked" : ""}> ${LABEL[id]}</label>`).join("")}</div></div></div></div>
    <div class="soundfont-actions"><button class="link" data-save-pack="${esc(pack.id)}">保存名称/绑定</button><button class="link" data-preview-pack="${esc(pack.id)}">音色测试</button><button class="link" data-preview-melody="${esc(pack.id)}">试听当前旋律</button><button class="link" data-activate-pack="${esc(pack.id)}">设为当前</button><button class="link danger-text" data-remove-pack="${esc(pack.id)}">移除</button></div>
  </article>`).join("") : `<div class="soundfont-empty"><b>还没有本机乐器音色包</b><span>导入后可修改名称、绑定乐器、试听音区与当前完整旋律；数据保存在本浏览器，刷新或重新登录仍保留。</span></div>`;
  return `<section class="sample-library"><div class="sample-library-head"><div><span class="eyebrow">LOCAL SOUND LIBRARY</span><h3>乐器音色包</h3><p id="sampleLoadStatus">音色包保存在此浏览器的本机库中；可在下方修改显示名称与绑定。</p></div><label class="sample-file-button">添加 .sf2 音色包<input id="samplePackUpload" type="file" accept=".sf2" multiple></label></div>
    <div class="soundfont-binding"><div><b>导入时先绑定乐器</b><small>同一个包可勾选多个乐器，导入后还可以单独修改。</small></div><div class="soundfont-bind-options" id="samplePackInstruments">${selectable.map((id, index) => `<label><input type="checkbox" value="${id}" ${index === 0 ? "checked" : ""}> ${LABEL[id]}</label>`).join("")}</div></div>
    <div class="soundfont-list" id="soundfontList">${cards}</div></section>`;
}

function importStatusView() {
  if (!importState) return '<div id="scoreImportStatus" class="score-import-status empty" aria-live="polite"></div>';
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
  try { soundfontPacks = await listLocalSoundfonts(); } catch (error) { soundfontPacks = []; console.warn("local soundfont catalog unavailable", error); }
  const projects = await api.workbenchProjects();
  // 侧栏接口只返回轻量摘要；当前工程才按需取完整音符和多轨数据。
  // 这避免工程数量增加后每次点击都传回、解码并渲染全部声部。
  const hasCurrent = current && projects.some(project => project.id === current.id);
  if (!hasCurrent) current = projects.length ? await api.workbenchProject(projects[0].id) : null;
  const melody = notesText(current?.melody), tempo = current?.tempo || 96;
  const chosenInstruments = current?.arrangement?.instruments || ["piano", "guzheng", "drum"];
  root.innerHTML = `<div class="page-head workbench-head"><div><h1>数字乐器与编曲工作台</h1><p>写旋律、导入乐谱、试听多轨。</p></div></div><div class="workbench-layout"><aside class="project-rail"><div class="rail-title"><b>我的编曲工程</b><span>${projects.length}</span></div><div id="projectList">${projects.map(projectCard).join("") || '<p class="muted">还没有工程</p>'}</div></aside><div class="workbench-main"><section class="composer-card"><div class="composer-tabs"><div><b>乐谱与旋律</b><p class="score-format-hint">推荐 MusicXML / MIDI；图片识谱支持 PNG、JPG、WEBP、TIFF、PDF（≤8MB，需本机 Audiveris）。</p></div><div class="score-actions"><a class="sample-score" href="/assets/samples/score-import-test.musicxml" download>下载示例</a><label class="file-import">导入乐谱 <input id="scoreUpload" type="file" accept=".musicxml,.xml,.mxl,.mid,.midi,.png,.jpg,.jpeg,.webp,.tif,.tiff,.pdf"></label></div></div>${importStatusView()}<div class="composer-fields"><input id="arrangementTitle" value="${esc(current?.title || "我的乡村音乐作品")}" placeholder="工程名称"><input id="melodyText" value="${esc(melody)}" placeholder="例如 C4 D4 E4 G4 A4；R 表示休止"><label class="tempo-box"><span>BPM</span><input id="tempo" type="number" min="40" max="220" value="${tempo}"></label></div><section class="transport-panel"><div class="transport-label"><b>试听控制</b><span>键位始终使用钢琴音高；选择音色只改变听到的乐器。拍号、格数与节拍器同步。</span></div><div class="transport-bar"><button id="playMelody">▶ 试听旋律</button><button id="stopMelody">■ 停止</button><label class="instrument-select"><span>演奏音色</span><select id="keyboardTimbre">${Object.entries(LABEL).filter(([id]) => id !== "drum").map(([id, name]) => `<option value="${id}">${name}</option>`).join("")}</select></label><label class="metronome-toggle"><input id="metronome" type="checkbox"><span>节拍器</span></label><label class="meter-controls"><span>拍号</span><select id="meterNumerator">${[2,3,4,6].map(n => `<option value="${n}" ${meterOf().numerator===n ? "selected" : ""}>${n}/4</option>`).join("")}</select></label><label class="meter-controls"><span>每拍</span><select id="gridDivision">${[[2,"2 格"],[4,"4 格"],[8,"8 格"]].map(([n,t]) => `<option value="${n}" ${meterOf().division===n ? "selected" : ""}>${t}</option>`).join("")}</select></label><label class="meter-controls"><span>小节</span><select id="bars">${[1,2,4,8].map(n => `<option value="${n}" ${meterOf().bars===n ? "selected" : ""}>${n}</option>`).join("")}</select></label></div></section>${sampleLibrary(soundfontPacks)}<section class="notation-workspace"><div id="notationPreview">${staff(current?.melody || [], "输入旋律预览", meterOf())}</div><div id="rollMount">${pianoRoll(current?.melody || [], tempo, meterOf())}</div><div class="keyboard-head"><div><b>完整电子钢琴 · C2–C7</b><span>键位总是钢琴音高；音色选择只改变试听声音</span></div><div><button class="link" id="clearMelody">清空旋律</button><button class="link" id="resetComposer">重置工程</button></div></div>${keyboard()}</section><div class="arrange-controls"><div class="style-pills" id="stylePills">${["乡土抒情", "欢快律动", "童谣清新", "器乐合奏"].map((x, i) => `<button data-style="${x}" class="${(!current && i === 0) || current?.style === x ? "selected" : ""}">${x}</button>`).join("")}</div><div class="instrument-pills" id="instrumentPills">${Object.entries(LABEL).map(([id, name]) => `<label><input type="checkbox" value="${id}" ${chosenInstruments.includes(id) ? "checked" : ""}> ${name}</label>`).join("")}</div><button class="button" id="makeArrangement">✦ 生成 / 更新多轨编曲</button></div><p class="composer-hint">勾选乐器后生成各自声部。</p></section><div id="stage">${stage(current)}</div></div></div>`;

  const melodyInput = root.querySelector("#melodyText"), tempoInput = root.querySelector("#tempo");
  if (draftProjectId !== (current?.id || "new")) { draftProjectId = current?.id || "new"; draftNotes = (current?.melody || []).map(note => ({ ...note })); }
  const getMeter = () => ({ numerator: Number(root.querySelector("#meterNumerator").value), division: Number(root.querySelector("#gridDivision").value), bars: Number(root.querySelector("#bars").value) });
  const getNotes = () => draftNotes || textMelody(melodyInput.value, +tempoInput.value || 96);
  const bindRoll = () => root.querySelectorAll("[data-roll-pitch]").forEach(cell => cell.onclick = () => {
    const notes = [...getNotes()], meter = getMeter(), tempo = +tempoInput.value || 96, stepSeconds = 60 / tempo / meter.division;
    const pitch = +cell.dataset.rollPitch, start = +(+cell.dataset.rollStep * stepSeconds).toFixed(3), found = notes.findIndex(n => n.pitch === pitch && Math.abs(n.start - start) < stepSeconds / 2);
    if (found >= 0) notes.splice(found, 1); else notes.push({ pitch, start, duration: +(stepSeconds * .92).toFixed(3), velocity: 92 });
    draftNotes = notes.sort((a,b) => a.start-b.start || a.pitch-b.pitch); melodyInput.value = notesText(draftNotes); refresh();
  });
  const refresh = () => { const notes = getNotes(), meter = getMeter(); root.querySelector("#notationPreview").innerHTML = staff(notes, "输入旋律预览", meter); root.querySelector("#rollMount").innerHTML = pianoRoll(notes, +tempoInput.value || 96, meter); bindRoll(); };
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
  root.querySelector("#samplePackUpload").onchange = async event => {
    const files = [...(event.target.files || [])]; if (!files.length) return;
    const instruments = [...root.querySelectorAll("#samplePackInstruments input:checked")].map(input => input.value);
    if (!instruments.length) { notify("请先选择至少一种要绑定的乐器", "error"); event.target.value = ""; return; }
    const status = root.querySelector("#sampleLoadStatus");
    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        status.textContent = `正在导入 ${index + 1}/${files.length}：${file.name}`;
        await loadLocalSoundfont(instruments, file, ({ loaded, total }) => { status.textContent = `正在解析 ${file.name} · ${loaded}/${total || "?"}`; });
      }
      soundfontPacks = await listLocalSoundfonts();
      notify(`已将 ${files.length} 个音色包保存到本机音色库，可立即试听。`);
      await renderWorkbench(root);
    } catch (error) { status.textContent = "音色包导入失败"; notify(`音色包导入失败：${error.message}`, "error"); }
    finally { event.target.value = ""; }
  };
  root.querySelectorAll("[data-save-pack]").forEach(button => button.onclick = async () => {
    const pack = soundfontPacks.find(item => item.id === button.dataset.savePack); if (!pack) return;
    const displayName = root.querySelector(`[data-pack-name="${CSS.escape(pack.id)}"]`)?.value || pack.name;
    const instruments = [...root.querySelectorAll(`[data-pack-instrument="${CSS.escape(pack.id)}"]:checked`)].map(item => item.value);
    try { await updateLocalSoundfont(pack.id, { displayName, instruments }); soundfontPacks = await listLocalSoundfonts(); notify("已保存音色包名称和乐器绑定"); await renderWorkbench(root); }
    catch (error) { notify(`无法保存音色包：${error.message}`, "error"); }
  });
  root.querySelectorAll("[data-preview-melody]").forEach(button => button.onclick = async () => {
    const pack = soundfontPacks.find(item => item.id === button.dataset.previewMelody); if (!pack) return;
    const notes = getNotes(); if (!notes.length) return notify("请先写入或导入旋律，再试听当前完整旋律", "error");
    const status = root.querySelector("#sampleLoadStatus"); button.disabled = true; status.textContent = `正在加载 ${pack.displayName || pack.name} 的完整旋律试听…`;
    try { await previewLocalSoundfont(pack.id, pack.instruments?.[0], ({ loaded, total }) => { status.textContent = `正在加载 ${pack.displayName || pack.name} · ${loaded}/${total || "?"}`; }, notes); status.textContent = `正在播放完整旋律：${pack.displayName || pack.name}`; }
    catch (error) { status.textContent = "试听失败"; notify(`无法试听：${error.message}`, "error"); }
    finally { button.disabled = false; }
  });
  root.querySelectorAll("[data-preview-pack]").forEach(button => button.onclick = async () => {
    const pack = soundfontPacks.find(item => item.id === button.dataset.previewPack); if (!pack) return;
    const status = root.querySelector("#sampleLoadStatus"); button.disabled = true; status.textContent = `正在加载 ${pack.name} 试听…`;
    try { await previewLocalSoundfont(pack.id, pack.instruments?.[0], ({ loaded, total }) => { status.textContent = `正在加载 ${pack.name} · ${loaded}/${total || "?"}`; }); status.textContent = `正在试听：${pack.name}`; }
    catch (error) { status.textContent = "试听失败"; notify(`无法试听：${error.message}`, "error"); }
    finally { button.disabled = false; }
  });
  root.querySelectorAll("[data-activate-pack]").forEach(button => button.onclick = async () => {
    const pack = soundfontPacks.find(item => item.id === button.dataset.activatePack); if (!pack) return;
    try { for (const instrument of pack.instruments || []) await activateLocalSoundfont(pack.id, instrument); soundfontPacks = await listLocalSoundfonts(); notify(`${pack.name} 已设为对应乐器的当前音色`); await renderWorkbench(root); }
    catch (error) { notify(`无法启用音色包：${error.message}`, "error"); }
  });
  root.querySelectorAll("[data-remove-pack]").forEach(button => button.onclick = async () => {
    const pack = soundfontPacks.find(item => item.id === button.dataset.removePack); if (!pack) return;
    try { await removeLocalSoundfont(pack.id); soundfontPacks = await listLocalSoundfonts(); notify(`已从本机音色库移除 ${pack.name}`); await renderWorkbench(root); }
    catch (error) { notify(`移除音色包失败：${error.message}`, "error"); }
  });
  melodyInput.oninput = () => { draftNotes = textMelody(melodyInput.value, +tempoInput.value || 96); refresh(); };
  tempoInput.onchange = refresh;
  ["meterNumerator", "gridDivision", "bars"].forEach(id => root.querySelector(`#${id}`).onchange = refresh);
  root.querySelector("#clearMelody").onclick = () => { melodyInput.value = ""; draftNotes = []; refresh(); };
  root.querySelector("#resetComposer").onclick = () => { current = null; renderWorkbench(root); };
  root.querySelectorAll("[data-key]").forEach(b => b.onclick = async () => { await playTracks([{ id: "keyboard", instrument: root.querySelector("#keyboardTimbre").value, notes: [{ pitch: +b.dataset.key, start: 0, duration: .38, velocity: 90 }] }]); const notes = [...getNotes(), { pitch: +b.dataset.key, start: (getNotes().reduce((m,n) => Math.max(m, n.start + n.duration), 0)), duration: 60 / (+tempoInput.value || 96) * .9, velocity: 92 }]; draftNotes = notes; melodyInput.value = notesText(notes); refresh(); });
  root.querySelector("#playMelody").onclick = () => { const notes = getNotes(), meter = getMeter(); if (!notes.length) return notify("请先输入至少一个音符", "error"); playTracks([{ id: "melody", instrument: root.querySelector("#keyboardTimbre").value, notes }], new Set(), {}, { metronome: root.querySelector("#metronome").checked, tempo: +tempoInput.value, beats: meter.bars * meter.numerator, meter: meter.numerator }); };
  root.querySelector("#stopMelody").onclick = stop;
  root.querySelectorAll("#stylePills button").forEach(b => b.onclick = () => { root.querySelectorAll("#stylePills button").forEach(x => x.classList.remove("selected")); b.classList.add("selected"); });
  root.querySelector("#makeArrangement").onclick = async () => { try { const notes = getNotes(); if (!notes.length) return notify("请输入旋律，或先导入 MusicXML / MIDI 乐谱", "error"); const meter = getMeter(); const data = { tempo: +tempoInput.value, style: root.querySelector("#stylePills .selected")?.dataset.style || "乡土抒情", instruments: [...root.querySelectorAll("#instrumentPills input:checked")].map(x => x.value), melody: notes, meter_numerator: meter.numerator, grid_division: meter.division, bars: meter.bars }; current = current ? await api.arrangeProject(current.id, data) : await api.createWorkbenchProject({ title: root.querySelector("#arrangementTitle").value.trim() || "未命名编曲", ...data }); if (!current.arrangement?.tracks?.length) current = await api.arrangeProject(current.id, data); notify("已保存主旋律并更新多轨编曲"); renderWorkbench(root); } catch (err) { notify(err.message, "error"); } };
  const playArrangementButton = root.querySelector("#playArrangement");
  if (playArrangementButton) playArrangementButton.onclick = () => { const muted = new Set([...root.querySelectorAll("[data-mute]:checked")].map(x => x.dataset.mute)); const volumes = Object.fromEntries([...root.querySelectorAll("[data-volume]")].map(x => [x.dataset.volume, +x.value / 100])); playTracks(current.arrangement.tracks, muted, volumes, { tempo: current.tempo, beats: (current.arrangement?.bars || 4) * (current.arrangement?.meter_numerator || 4), meter: current.arrangement?.meter_numerator || 4 }); };
  const stopArrangementButton = root.querySelector("#stopArrangement");
  if (stopArrangementButton) stopArrangementButton.onclick = stop;
  root.querySelectorAll("[data-preview-track]").forEach(b => b.onclick = () => { const track = current.arrangement.tracks.find(t => String(t.id) === b.dataset.previewTrack); if (track) playTracks([track]); });
}
