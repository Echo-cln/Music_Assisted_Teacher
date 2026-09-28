import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";

const LABEL = { piano: "电子钢琴", violin: "小提琴", guzheng: "古筝", erhu: "二胡", drum: "非洲鼓" };
let audioContext, playing = [], current = null;

const KEYBOARD = [60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76];
const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
function noteName(pitch) { return `${NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`; }
function tokenPitch(token) {
  const match = String(token).trim().match(/^([A-Ga-g])([#♯b♭]?)([0-8])$/);
  if (!match) return null;
  const base = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[match[1].toUpperCase()];
  const accidental = ["#", "♯"].includes(match[2]) ? 1 : ["b", "♭"].includes(match[2]) ? -1 : 0;
  return (Number(match[3]) + 1) * 12 + base + accidental;
}
function textMelody(text) { return String(text || "").split(/[\s,，]+/).map(tokenPitch).filter(Number.isFinite).map((pitch, index) => ({ pitch, start: index * .5, duration: .45 })); }
function staffSvg(notes, label = "旋律五线谱") {
  const safe = (notes || []).slice(0, 48);
  const width = Math.max(530, 76 + safe.length * 31);
  const lines = [34, 50, 66, 82, 98].map(y => `<line x1="46" y1="${y}" x2="${width - 18}" y2="${y}"/>`).join("");
  const heads = safe.map((note, index) => {
    const x = 70 + index * 31;
    const y = Math.max(16, Math.min(116, 98 - (Number(note.pitch) - 60) * 4));
    const stem = Number(note.pitch) < 71 ? `<line x1="${x + 6}" y1="${y}" x2="${x + 6}" y2="${y - 31}"/>` : `<line x1="${x - 6}" y1="${y}" x2="${x - 6}" y2="${y + 31}"/>`;
    const ledger = y <= 27 || y >= 105 ? `<line x1="${x - 10}" y1="${y}" x2="${x + 10}" y2="${y}"/>` : "";
    return `<g class="staff-note" data-staff-index="${index}">${ledger}<ellipse cx="${x}" cy="${y}" rx="7" ry="5" transform="rotate(-18 ${x} ${y})"/>${stem}<text x="${x}" y="132">${noteName(Number(note.pitch))}</text></g>`;
  }).join("");
  return `<div class="staff-caption"><b>${label}</b><span>${safe.length ? `${safe.length} 个音符` : "点击下方琴键输入旋律"}</span></div><div class="staff-scroll"><svg class="music-staff" viewBox="0 0 ${width} 144" role="img" aria-label="${label}"><text class="staff-clef" x="17" y="93">𝄞</text>${lines}${heads || '<text class="staff-empty" x="70" y="72">从下方电子琴输入音符，或导入 MusicXML / MIDI</text>'}</svg></div>`;
}
function keyboard() { return `<div class="virtual-keyboard" aria-label="电子钢琴">${KEYBOARD.map(pitch => `<button type="button" class="key ${noteName(pitch).includes("♯") ? "black" : "white"}" data-key="${pitch}"><b>${noteName(pitch).replace("♯", "#")}</b></button>`).join("")}</div>`; }

function stop() { playing.forEach(node => { try { node.stop(); } catch (_) {} }); playing = []; }
function tone(instrument, note, when, duration) {
  const ctx = audioContext || (audioContext = new AudioContext());
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  const hz = 440 * Math.pow(2, (note.pitch - 69) / 12);
  osc.frequency.value = instrument === "drum" ? (note.pitch === 36 ? 92 : 170) : hz;
  osc.type = instrument === "violin" || instrument === "erhu" ? "sawtooth" : instrument === "guzheng" ? "triangle" : "sine";
  const volume = instrument === "drum" ? .12 : .075;
  gain.gain.setValueAtTime(0.0001, when); gain.gain.exponentialRampToValueAtTime(volume, when + .015);
  gain.gain.exponentialRampToValueAtTime(.0001, when + Math.max(.06, duration * .9));
  osc.connect(gain).connect(ctx.destination); osc.start(when); osc.stop(when + Math.max(.08, duration)); playing.push(osc);
}
function play(project, muted = new Set()) {
  stop();
  if (!project?.arrangement?.tracks?.length) return notify("请先生成编曲");
  const ctx = audioContext || (audioContext = new AudioContext()), now = ctx.currentTime + .08;
  project.arrangement.tracks.forEach(track => { if (!muted.has(track.id)) track.notes.forEach(n => tone(track.instrument, n, now + n.start, n.duration)); });
  notify("正在试听，可随时点击“停止播放”");
}
function projectCard(p) { return `<button class="workbench-project ${current?.id === p.id ? "active" : ""}" data-project="${p.id}"><b>${esc(p.title)}</b><small>${esc(p.style)} · ${p.tempo} BPM</small></button>`; }
function stage(project) {
  if (!project) return `<div class="workbench-empty"><b>先在上方五线谱输入旋律</b><p>可直接点击电子琴、键入 C4 D4 E4，或导入 MusicXML / MIDI；生成后会出现可试听、可静音的多声部。</p></div>`;
  const tracks = project.arrangement?.tracks || [];
  return `<section class="workbench-stage"><div class="stage-heading"><div><span>当前工程</span><h2>${esc(project.title)}</h2><p>${esc(project.arrangement?.tips || "正在等待生成声部")}</p></div><div class="stage-actions"><button class="button ghost" id="stopArrangement">停止播放</button><button class="button" id="playArrangement">▶ 试听全曲</button></div></div><section class="score-panel">${staffSvg(project.melody, "主旋律 · 可试听五线谱")}</section><div class="track-list">${tracks.map(t => `<article class="music-track" data-track="${t.id}"><div class="track-icon">${t.instrument === "drum" ? "◉" : "♫"}</div><div><b>${esc(t.name)}</b><small>${LABEL[t.instrument] || t.instrument} · ${t.notes.length} 个音符</small></div><label class="track-mute"><input type="checkbox" data-mute="${t.id}"> 静音</label><button class="track-preview" data-preview-track="${t.id}">试听声部</button></article>`).join("") || `<p class="muted">尚未生成轨道。</p>`}</div></section>`; }

export async function renderWorkbench(root) {
  const projects = await api.workbenchProjects(); current = projects[0] || null;
  root.innerHTML = `<div class="page-head workbench-head"><div><p class="eyebrow">乡音智谱 · 低设备门槛音乐创作</p><h1>数字乐器与智能编曲工作台</h1><p>先用可点击的电子琴或导入五线谱写出旋律，再生成可独立试听、静音的课堂合奏声部。</p></div></div><div class="workbench-layout"><aside class="project-rail"><div class="rail-title"><b>我的编曲工程</b><span>${projects.length}</span></div><div id="projectList">${projects.map(projectCard).join("") || '<p class="muted">还没有工程</p>'}</div></aside><div class="workbench-main"><section class="composer-card"><div class="composer-tabs"><b>写入旋律</b><span>或</span><label class="file-import">导入 MusicXML / MIDI <input id="scoreUpload" type="file" accept=".musicxml,.xml,.mid,.midi"></label></div><div class="composer-fields"><input id="arrangementTitle" value="${esc(current?.title || "我的乡村音乐作品")}" placeholder="工程名称"><input id="melodyText" value="${esc((current?.melody || []).map(n => noteName(n.pitch)).join(" "))}" placeholder="例如：C4 D4 E4 G4 A4 G4 E4 D4"><select id="tempo"><option value="80">80 BPM · 舒缓</option><option value="96" selected>96 BPM · 课堂常用</option><option value="120">120 BPM · 活泼</option></select></div><section class="notation-workspace"><div id="notationPreview">${staffSvg(current?.melody || [], "输入旋律预览")}</div><div class="keyboard-head"><b>电子钢琴</b><span>点击琴键试听并写入旋律</span><button class="link" id="clearMelody">清空</button></div>${keyboard()}</section><div class="arrange-controls"><div class="style-pills" id="stylePills">${["乡土抒情", "欢快律动", "童谣清新", "器乐合奏"].map((x,i) => `<button data-style="${x}" class="${(!current && i===0) || current?.style === x ? "selected" : ""}">${x}</button>`).join("")}</div><div class="instrument-pills" id="instrumentPills">${Object.entries(LABEL).map(([id, name]) => `<label><input type="checkbox" value="${id}" ${["piano","guzheng","drum"].includes(id) ? "checked" : ""}> ${name}</label>`).join("")}</div><button class="button" id="makeArrangement">✦ 生成可试听声部</button></div><p class="composer-hint">五线谱、键盘输入和 MusicXML/MIDI 导入使用同一条旋律；生成后可反复更换速度、风格和乐器。</p></section><div id="stage">${stage(current)}</div></div></div>`;
  const tempo = root.querySelector('#tempo'); if (current) tempo.value = String(current.tempo);
  root.querySelectorAll('[data-project]').forEach(btn => btn.onclick = async () => { current = await api.workbenchProject(btn.dataset.project); renderWorkbench(root); });
  root.querySelector('#scoreUpload').onchange = async event => { const file = event.target.files[0]; if (!file) return; const form = new FormData(); form.append('file', file); try { current = await api.importScore(form); notify(`已导入 ${file.name}`); renderWorkbench(root); } catch (e) { notify(e.message, 'error'); } };
  const melodyInput = root.querySelector('#melodyText');
  const preview = () => { root.querySelector('#notationPreview').innerHTML = staffSvg(textMelody(melodyInput.value), "输入旋律预览"); };
  melodyInput.addEventListener('input', preview);
  root.querySelector('#clearMelody').onclick = () => { melodyInput.value = ''; preview(); };
  root.querySelectorAll('[data-key]').forEach(button => button.onclick = async () => { const pitch = Number(button.dataset.key); const ctx = audioContext || (audioContext = new AudioContext()); await ctx.resume?.(); tone('piano', { pitch }, ctx.currentTime, .42); melodyInput.value = `${melodyInput.value.trim()} ${noteName(pitch)}`.trim(); preview(); });
  root.querySelector('#makeArrangement').onclick = async () => { try { const title = root.querySelector('#arrangementTitle').value.trim() || '未命名编曲'; const chosen = [...root.querySelectorAll('#instrumentPills input:checked')].map(x => x.value); const style = root.querySelector('#stylePills .selected')?.dataset.style || '乡土抒情'; const value = root.querySelector('#melodyText').value.trim(); let melody = current?.melody || []; if (value) melody = (await api.parseNotes({ notes: value, tempo: +tempo.value })).melody; if (!melody.length) return notify('请输入旋律，或先导入乐谱', 'error'); current = current ? await api.arrangeProject(current.id, { tempo:+tempo.value, style, instruments:chosen, melody }) : await api.createWorkbenchProject({title, tempo:+tempo.value, style, melody}); if (current) current = await api.arrangeProject(current.id, {tempo:+tempo.value, style, instruments:chosen, melody}); notify('已生成可编辑声部'); renderWorkbench(root); } catch (e) { notify(e.message, 'error'); } };
  root.querySelectorAll('#stylePills button').forEach(b => b.onclick = () => { root.querySelectorAll('#stylePills button').forEach(x => x.classList.remove('selected')); b.classList.add('selected'); });
  root.querySelector('#playArrangement')?.addEventListener('click', () => play(current, new Set([...root.querySelectorAll('[data-mute]:checked')].map(x => x.dataset.mute))));
  root.querySelector('#stopArrangement')?.addEventListener('click', () => { stop(); notify('已停止播放'); });
  root.querySelectorAll('[data-preview-track]').forEach(button => button.onclick = () => { const track = current?.arrangement?.tracks?.find(item => item.id === button.dataset.previewTrack); if (track) play({ arrangement: { tracks: [track] } }); });
}
