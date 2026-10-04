import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";

const LABEL = { piano: "电子钢琴", violin: "小提琴", guzheng: "古筝", erhu: "二胡", guitar: "原声吉他", drum: "非洲鼓" };
const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const KEYS = Array.from({ length: 61 }, (_, i) => i + 36); // C2–C7
let audioContext, playing = [], current = null;

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
  return `<div class="staff-caption"><b>${title}</b><span>${safe.length ? `${safe.length} 个音符 · 4/4` : "点击琴键、卷帘格或导入乐谱"}</span></div><div class="staff-scroll"><svg class="music-staff" viewBox="0 0 ${width} 144"><text class="staff-clef" x="17" y="94">𝄞</text><text class="staff-meter" x="51" y="60">4</text><text class="staff-meter" x="51" y="88">4</text>${lines}${marks || '<text class="staff-empty" x="95" y="72">从完整电子琴、钢琴卷帘或 MusicXML / MIDI 导入旋律</text>'}</svg></div>`;
}
function keyboard() {
  const whites = KEYS.filter(p => !isBlack(p));
  return `<div class="keyboard-scroll"><div class="virtual-keyboard" style="--white-count:${whites.length}">${whites.map(p => `<button class="key white" data-key="${p}" title="${noteName(p)}"><b>${p % 12 === 0 ? noteName(p) : ""}</b></button>${KEYS.includes(p + 1) && isBlack(p + 1) ? `<button class="key black" data-key="${p + 1}" title="${noteName(p + 1)}"></button>` : ""}`).join("")}</div></div>`;
}
function pianoRoll(notes) {
  const pitches = Array.from({ length: 25 }, (_, i) => 72 - i), steps = Array.from({ length: 16 }, (_, i) => i), active = new Set((notes || []).map(n => `${n.pitch}:${Math.round(n.start / .625)}`));
  return `<section class="piano-roll"><div class="roll-head"><b>钢琴卷帘编辑</b><span>点击格子添加/删除八分音符 · 4 小节</span></div><div class="roll-grid"><div class="roll-labels">${pitches.map(p => `<span>${p % 12 === 0 ? noteName(p) : ""}</span>`).join("")}</div><div class="roll-cells">${pitches.map(p => `<div class="roll-row">${steps.map(s => `<button class="roll-cell ${active.has(`${p}:${s}`) ? "active" : ""}" data-roll-pitch="${p}" data-roll-step="${s}" title="${noteName(p)}"></button>`).join("")}</div>`).join("")}</div></div></section>`;
}

function stop() { playing.forEach(node => { try { node.stop(); } catch (_) {} }); playing = []; }
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
  stop(); if (!tracks?.length) return notify("请先写入旋律", "error"); const ctx = audioContext || (audioContext = new AudioContext()); await ctx.resume?.(); const now = ctx.currentTime + .08;
  if (options.metronome) metronome(ctx, now, options.tempo || 96, options.beats || 16);
  tracks.forEach(track => { if (!muted.has(track.id)) track.notes.forEach(n => tone(track.instrument, n, now + n.start, n.duration, volume[track.id] || 1)); });
}
function projectCard(p) { return `<button class="workbench-project ${current?.id === p.id ? "active" : ""}" data-project="${p.id}"><b>${esc(p.title)}</b><small>${esc(p.style)} · ${p.tempo} BPM</small></button>`; }
function stage(project) {
  if (!project) return `<div class="workbench-empty"><b>从一段旋律开始</b><p>先点击完整电子钢琴、钢琴卷帘，或导入 MusicXML/MIDI/清晰五线谱图片。完成后会生成可以单独试听、静音和调音量的多轨工程。</p></div>`;
  const tracks = project.arrangement?.tracks || [];
  const chordLabels = project.arrangement?.chord_labels || [];
  const chords = chordLabels.length ? `<section class="chord-timeline" aria-label="本曲和弦走向"><div><b>本曲和弦走向</b><span>按每小节主旋律匹配，可作为课堂核验依据</span></div><ol>${chordLabels.map((label, index) => `<li><small>第 ${index + 1} 小节</small><b>${esc(label)}</b></li>`).join("")}</ol></section>` : "";
  return `<section class="workbench-stage"><div class="stage-heading"><div><span>当前工程 · ${project.tempo} BPM · ${esc(project.arrangement?.key || "待推断")}</span><h2>${esc(project.title)}</h2><p>${esc(project.arrangement?.tips || "正在等待生成声部")}</p></div><div class="stage-actions"><button class="button ghost" id="stopArrangement">停止</button><button class="button" id="playArrangement">▶ 从头播放</button></div></div>${chords}<section class="score-panel">${staff(project.melody, "主旋律五线谱 · 已同步到工程")}</section><div class="track-list">${tracks.map(t => `<article class="music-track"><div class="track-icon">${t.instrument === "drum" ? "◉" : "♫"}</div><div><b>${esc(t.name)}</b><small>${LABEL[t.instrument] || t.instrument} · ${t.notes.length} 个音符</small></div><label class="track-volume"><span>音量</span><input type="range" data-volume="${t.id}" min="0" max="100" value="82"></label><label class="track-mute"><input type="checkbox" data-mute="${t.id}"> 静音</label><button class="track-preview" data-preview-track="${t.id}">试听</button></article>`).join("")}</div></section>`;
}

export async function renderWorkbench(root) {
  const projects = await api.workbenchProjects(); current = current ? projects.find(p => p.id === current.id) || projects[0] : projects[0] || null;
  const melody = notesText(current?.melody), tempo = current?.tempo || 96;
  const chosenInstruments = current?.arrangement?.instruments || ["piano", "guzheng", "drum"];
  root.innerHTML = `<div class="page-head workbench-head"><div><p class="eyebrow">乡音智谱 · 低设备门槛音乐创作</p><h1>数字乐器与智能编曲工作台</h1><p>完整电子钢琴、可编辑五线谱/钢琴卷帘与多轨播放在同一工程中同步，不需要额外安装收费编曲软件。</p></div></div><div class="workbench-layout"><aside class="project-rail"><div class="rail-title"><b>我的编曲工程</b><span>${projects.length}</span></div><div id="projectList">${projects.map(projectCard).join("") || '<p class="muted">还没有工程</p>'}</div></aside><div class="workbench-main"><section class="composer-card"><div class="composer-tabs"><div><b>创作区</b><span>键盘、五线谱与卷帘同步</span></div><label class="file-import">导入已有乐谱 <input id="scoreUpload" type="file" accept=".musicxml,.xml,.mxl,.mid,.midi,.png,.jpg,.jpeg,.webp,.tif,.tiff,.pdf"></label></div><div class="import-note"><b>支持真实解析：</b>MusicXML/MXL 与 MIDI 可直接转为可编辑音符；PNG/JPG/WEBP/TIFF/PDF 会调用本机 Audiveris 识别成 MusicXML 后导入。识别后必须核对调号、节奏与连音，失败会直接显示 Audiveris 日志摘要。</div><div class="composer-fields"><input id="arrangementTitle" value="${esc(current?.title || "我的乡村音乐作品")}" placeholder="工程名称"><input id="melodyText" value="${esc(melody)}" placeholder="例如 C4 D4 E4 G4 A4"><label class="tempo-box"><span>BPM</span><input id="tempo" type="number" min="40" max="220" value="${tempo}"></label></div><div class="transport-bar"><button id="playMelody">▶ 试听旋律</button><button id="stopMelody">■</button><label>键盘音色 <select id="keyboardTimbre">${Object.entries(LABEL).filter(([id]) => id !== "drum").map(([id, name]) => `<option value="${id}">${name}</option>`).join("")}</select></label><label><input id="metronome" type="checkbox"> 节拍器</label><span>4/4 · 16 格编辑区</span></div><section class="notation-workspace"><div id="notationPreview">${staff(current?.melody || [], "输入旋律预览")}</div><div id="rollMount">${pianoRoll(current?.melody || [])}</div><div class="keyboard-head"><div><b>完整电子钢琴 · C2–C7</b><span>键位总是钢琴音高；音色选择只改变试听声音</span></div><div><button class="link" id="clearMelody">清空旋律</button><button class="link" id="resetComposer">重置工程</button></div></div>${keyboard()}</section><div class="arrange-controls"><div class="style-pills" id="stylePills">${["乡土抒情", "欢快律动", "童谣清新", "器乐合奏"].map((x, i) => `<button data-style="${x}" class="${(!current && i === 0) || current?.style === x ? "selected" : ""}">${x}</button>`).join("")}</div><div class="instrument-pills" id="instrumentPills">${Object.entries(LABEL).map(([id, name]) => `<label><input type="checkbox" value="${id}" ${chosenInstruments.includes(id) ? "checked" : ""}> ${name}</label>`).join("")}</div><button class="button" id="makeArrangement">✦ 生成 / 更新多轨编曲</button></div><p class="composer-hint">和弦按实际旋律逐小节匹配；每个勾选乐器都会生成独立轨道。</p></section><div id="stage">${stage(current)}</div></div></div>`;

  const melodyInput = root.querySelector("#melodyText"), tempoInput = root.querySelector("#tempo");
  const getNotes = () => textMelody(melodyInput.value, +tempoInput.value || 96);
  const bindRoll = () => root.querySelectorAll("[data-roll-pitch]").forEach(cell => cell.onclick = () => { const notes = getNotes(), pitch = +cell.dataset.rollPitch, start = +(+cell.dataset.rollStep * .625).toFixed(3), found = notes.findIndex(n => n.pitch === pitch && Math.abs(n.start - start) < .32); if (found >= 0) notes.splice(found, 1); else notes.push({ pitch, start, duration: .52, velocity: 92 }); melodyInput.value = notesText(notes); refresh(); });
  const refresh = () => { const notes = getNotes(); root.querySelector("#notationPreview").innerHTML = staff(notes, "输入旋律预览"); root.querySelector("#rollMount").innerHTML = pianoRoll(notes); bindRoll(); };
  bindRoll();
  root.querySelectorAll("[data-project]").forEach(b => b.onclick = async () => { current = await api.workbenchProject(b.dataset.project); renderWorkbench(root); });
  root.querySelector("#scoreUpload").onchange = async e => { const file = e.target.files[0]; if (!file) return; const form = new FormData(); form.append("file", file); notify(`正在导入 ${file.name}…`); try { current = await api.importScore(form); notify(current.import_notice || `已解析 ${file.name}，可以继续编辑`); renderWorkbench(root); } catch (err) { notify(err.message, "error"); } finally { e.target.value = ""; } };
  melodyInput.oninput = refresh; tempoInput.onchange = refresh;
  root.querySelector("#clearMelody").onclick = () => { melodyInput.value = ""; refresh(); };
  root.querySelector("#resetComposer").onclick = () => { current = null; renderWorkbench(root); };
  root.querySelectorAll("[data-key]").forEach(b => b.onclick = async () => { const ctx = audioContext || (audioContext = new AudioContext()); await ctx.resume?.(); tone(root.querySelector("#keyboardTimbre").value, { pitch: +b.dataset.key }, ctx.currentTime, .38); melodyInput.value = `${melodyInput.value.trim()} ${noteName(+b.dataset.key)}`.trim(); refresh(); });
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
