import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";

const LABEL = { piano: "电子钢琴", violin: "小提琴", guzheng: "古筝", erhu: "二胡", drum: "非洲鼓" };
let audioContext, playing = [], current = null;

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
  if (!project) return `<div class="workbench-empty"><b>从一段旋律开始</b><p>输入 C4 D4 E4，或导入 MusicXML / MIDI。系统将生成可试听、可静音、可继续编辑的多个声部。</p></div>`;
  const tracks = project.arrangement?.tracks || [];
  return `<section class="workbench-stage"><div class="stage-heading"><div><span>当前工程</span><h2>${esc(project.title)}</h2><p>${esc(project.arrangement?.tips || "正在等待生成声部")}</p></div><div class="stage-actions"><button class="button ghost" id="stopArrangement">停止播放</button><button class="button" id="playArrangement">▶ 试听全曲</button></div></div><div class="track-list">${tracks.map(t => `<article class="music-track" data-track="${t.id}"><div class="track-icon">${t.instrument === "drum" ? "◉" : "♫"}</div><div><b>${esc(t.name)}</b><small>${LABEL[t.instrument] || t.instrument} · ${t.notes.length} 个音符</small></div><label class="track-mute"><input type="checkbox" data-mute="${t.id}"> 静音</label><div class="note-line">${t.notes.slice(0, 22).map(n => `<i style="height:${10 + (n.pitch % 18)}px"></i>`).join("")}</div></article>`).join("") || `<p class="muted">尚未生成轨道。</p>`}</div></section>`; }

export async function renderWorkbench(root) {
  const projects = await api.workbenchProjects(); current = projects[0] || null;
  root.innerHTML = `<div class="page-head workbench-head"><div><p class="eyebrow">乡音智谱 · 低设备门槛音乐创作</p><h1>数字乐器与智能编曲工作台</h1><p>把一条旋律变成可分声部演奏的课堂作品。内置电子钢琴、小提琴、古筝、二胡与非洲鼓，无需购买音源软件。</p></div></div><div class="workbench-layout"><aside class="project-rail"><div class="rail-title"><b>我的编曲工程</b><span>${projects.length}</span></div><div id="projectList">${projects.map(projectCard).join("") || '<p class="muted">还没有工程</p>'}</div></aside><div class="workbench-main"><section class="composer-card"><div class="composer-tabs"><b>输入旋律</b><span>或</span><label class="file-import">导入 MusicXML / MIDI <input id="scoreUpload" type="file" accept=".musicxml,.xml,.mid,.midi"></label></div><div class="composer-fields"><input id="arrangementTitle" value="${esc(current?.title || "我的乡村音乐作品")}" placeholder="工程名称"><input id="melodyText" placeholder="例如：C4 D4 E4 G4 A4 G4 E4 D4"><select id="tempo"><option value="80">80 BPM · 舒缓</option><option value="96" selected>96 BPM · 课堂常用</option><option value="120">120 BPM · 活泼</option></select></div><div class="arrange-controls"><div class="style-pills" id="stylePills">${["乡土抒情", "欢快律动", "童谣清新", "器乐合奏"].map((x,i) => `<button data-style="${x}" class="${(!current && i===0) || current?.style === x ? "selected" : ""}">${x}</button>`).join("")}</div><div class="instrument-pills" id="instrumentPills">${Object.entries(LABEL).map(([id, name]) => `<label><input type="checkbox" value="${id}" ${["piano","guzheng","drum"].includes(id) ? "checked" : ""}> ${name}</label>`).join("")}</div><button class="button" id="makeArrangement">✦ 智能生成声部</button></div><p class="composer-hint">导入后的旋律会保留在工程中；你可以重新选择速度、风格与乐器，反复生成不同的伴奏方案。</p></section><div id="stage">${stage(current)}</div></div></div>`;
  const tempo = root.querySelector('#tempo'); if (current) tempo.value = String(current.tempo);
  root.querySelectorAll('[data-project]').forEach(btn => btn.onclick = async () => { current = await api.workbenchProject(btn.dataset.project); renderWorkbench(root); });
  root.querySelector('#scoreUpload').onchange = async event => { const file = event.target.files[0]; if (!file) return; const form = new FormData(); form.append('file', file); try { current = await api.importScore(form); notify(`已导入 ${file.name}`); renderWorkbench(root); } catch (e) { notify(e.message, 'error'); } };
  root.querySelector('#makeArrangement').onclick = async () => { try { const title = root.querySelector('#arrangementTitle').value.trim() || '未命名编曲'; const chosen = [...root.querySelectorAll('#instrumentPills input:checked')].map(x => x.value); const style = root.querySelector('#stylePills .selected')?.dataset.style || '乡土抒情'; const value = root.querySelector('#melodyText').value.trim(); let melody = current?.melody || []; if (value) melody = (await api.parseNotes({ notes: value, tempo: +tempo.value })).melody; if (!melody.length) return notify('请输入旋律，或先导入乐谱', 'error'); current = current ? await api.arrangeProject(current.id, { tempo:+tempo.value, style, instruments:chosen, melody }) : await api.createWorkbenchProject({title, tempo:+tempo.value, style, melody}); if (current) current = await api.arrangeProject(current.id, {tempo:+tempo.value, style, instruments:chosen, melody}); notify('已生成可编辑声部'); renderWorkbench(root); } catch (e) { notify(e.message, 'error'); } };
  root.querySelectorAll('#stylePills button').forEach(b => b.onclick = () => { root.querySelectorAll('#stylePills button').forEach(x => x.classList.remove('selected')); b.classList.add('selected'); });
  root.querySelector('#playArrangement')?.addEventListener('click', () => play(current, new Set([...root.querySelectorAll('[data-mute]:checked')].map(x => x.dataset.mute))));
  root.querySelector('#stopArrangement')?.addEventListener('click', () => { stop(); notify('已停止播放'); });
}

