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
    .workbench-head { max-width: 1240px; margin: 0 auto 18px; }.workbench-head h1 { margin: 0 0 6px; }.workbench-head p { margin: 0; color: var(--muted); }.workbench-layout { max-width: 1240px; margin: 0 auto; }.composer-tabs { min-height: 38px; }.score-actions,.sample-pack-controls{display:flex;align-items:center;gap:8px}.sample-score,.file-import,.sample-file-button{display:inline-flex;align-items:center;justify-content:center;border:1px solid #dfc4b4;border-radius:10px;padding:9px 12px;background:#fffdfa;color:#9f4b35;font-size:.84rem;font-weight:750;text-decoration:none;cursor:pointer}.sample-score{color:#706159;border-color:#e6d9cf}.file-import:hover,.sample-file-button:hover{background:#fbefe7}.sample-file-button input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}.sample-file-button:focus-within,.file-import:focus-within{outline:3px solid rgba(191,100,70,.18);outline-offset:2px}.composer-hint{margin-top:12px}.score-import-status{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 14px;align-items:center;margin:10px 0 14px;padding:10px 12px;border:1px solid #eadbd1;border-radius:12px;background:#fffaf5;color:#6d5d55}.score-import-status b{display:block;color:#8f4936;font-size:.88rem}.score-import-status small{display:block;margin-top:3px;color:#8f817a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.score-import-status>span{grid-column:2;grid-row:1/3;color:#a44f38;font-weight:800}.score-import-progress{grid-column:1;height:6px;overflow:hidden;border-radius:9px;background:#eadfd8}.score-import-progress i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#d7845c,#a84d36);transition:width .25s ease}.score-import-status.running .score-import-progress i{animation:score-progress-glow 1.2s ease-in-out infinite}.score-import-status.success{border-color:#c8dfd0;background:#f5fbf6}.score-import-status.success b,.score-import-status.success>span{color:#39734c}.score-import-status.error{border-color:#e7c3bb;background:#fff5f2}.score-import-status.error b,.score-import-status.error>span{color:#b14331}.workbench-project.loading{opacity:.6;cursor:wait}.composer-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #eadfd8;padding-bottom:14px}.composer-tabs>b{font-size:1.05rem}.score-format-hint{margin:10px 0 0;color:#7f7068;font-size:.82rem}.transport-panel{margin:16px 0;padding:16px;border:1px solid #eadbd1;border-radius:16px;background:linear-gradient(120deg,#fffdf9,#fcf6ef)}.transport-label{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:12px}.transport-label span{font-size:.84rem;color:#7f7068}.transport-bar{display:flex!important;flex-wrap:wrap;align-items:center;gap:10px}.transport-bar button,.transport-bar select,.transport-bar input{min-height:38px}.transport-bar label{display:flex;align-items:center;gap:7px;margin:0;white-space:nowrap}.meter-controls{display:flex;align-items:center;gap:7px;padding:5px 9px;border:1px solid #e6d9cf;border-radius:10px;background:#fff}.meter-controls select{min-width:74px}.metronome-toggle{padding:8px 10px;border:1px solid #e6d9cf;border-radius:10px;background:#fff}.piano-roll{max-height:520px;overflow:auto;border:1px solid #eadbd1;border-radius:14px;background:#fffdf9}.roll-head{position:sticky;top:0;z-index:4;display:flex;justify-content:space-between;padding:12px 14px;background:#fffdf9;border-bottom:1px solid #eadbd1}.roll-grid{min-width:max-content}.roll-labels{position:sticky;left:0;z-index:3;background:#fffdf9}.roll-labels span{height:22px;display:block;padding:0 8px;font-size:.72rem;color:#77655b;border-bottom:1px solid #f1e8e0}.roll-cells{display:block}.roll-row{height:22px;display:flex;border-bottom:1px solid #f1e8e0}.roll-cell{width:22px;min-width:22px;height:22px;padding:0;border:0;border-right:1px solid #f1e8e0;background:#fff}.roll-cell:nth-child(4n+1){border-left:1px solid #d9b5a4}.roll-cell.active{background:#b9583d}.roll-cell:hover{background:#f2cfbd}.roll-row:nth-child(12n+1){border-top:1px solid #c9896e}.roll-meter{font-size:.8rem;color:#7f7068}.notation-workspace{margin-top:16px}.keyboard-scroll{overflow-x:auto;padding-bottom:6px}.virtual-keyboard{min-width:960px}.score-import-status.empty{display:none}.staff-clef.bass{font-size:40px}.staff-system{margin-bottom:12px}@keyframes score-progress-glow{50%{filter:brightness(1.18)}}
    .project-rail{min-width:0}.project-row{display:grid;grid-template-columns:minmax(0,1fr) 34px;gap:7px;margin:7px 0}.project-row .workbench-project{margin:0;min-width:0}.project-delete{border:1px solid #ead8cf;background:#fffaf7;color:#a04b36;border-radius:10px;font-size:1rem;cursor:pointer}.project-delete:hover{background:#f8e8e1}.sample-library{background:#fffdf9}.soundfont-binding{align-items:flex-start}.soundfont-bind-options{display:grid!important;grid-template-columns:repeat(5,minmax(92px,1fr));gap:8px;width:100%;justify-content:initial}.soundfont-bind-options label{display:flex!important;align-items:center;gap:6px;min-height:39px;padding:9px 10px;border-radius:10px;background:#fffdf9;white-space:nowrap}.soundfont-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;padding:16px 0}.soundfont-card-main{min-width:0}.soundfont-card-main>div:last-child{min-width:0;width:100%}.soundfont-card-main small{line-height:1.55;word-break:break-word}.soundfont-edit{display:grid;grid-template-columns:minmax(180px,300px) minmax(0,1fr);gap:12px 18px;align-items:start;margin-top:13px;padding-top:13px;border-top:1px dashed #eadbd1}.soundfont-edit>span{padding-top:10px;font-weight:700}.soundfont-edit input{max-width:none!important;width:100%;margin:0!important}.soundfont-edit .soundfont-bind-options{grid-template-columns:repeat(3,minmax(92px,1fr))}.soundfont-actions{align-content:flex-start;justify-content:flex-end;max-width:350px}.soundfont-actions .link{padding:7px 0;white-space:nowrap}.chord-timeline ol{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));overflow:visible!important;gap:9px;padding:12px 0 1px!important}.chord-timeline li{min-width:0!important}.staff-scroll{display:grid;gap:14px;overflow:visible}.staff-system{padding:12px;border:1px solid #eaded3;border-radius:12px;background:#fffdf9}.staff-system-head{display:flex;justify-content:space-between;gap:8px;margin:0 0 7px;color:#796a61;font-size:.78rem}.staff-system svg{display:block;width:100%;height:auto}.staff-empty{fill:#9a8578;font-size:13px}.staff-barline{stroke:#cbb6a8;stroke-width:1.2}.staff-note{fill:#a84d36;stroke:#a84d36}.staff-clef{font-family:serif;font-size:45px}.staff-meter{font-size:14px;fill:#735f54}.staff-label{fill:#89766b;font-size:12px}@media(max-width:860px){.sample-library-head,.soundfont-binding{align-items:stretch;flex-direction:column}.soundfont-bind-options,.soundfont-edit .soundfont-bind-options{grid-template-columns:repeat(2,minmax(120px,1fr))}.soundfont-card{grid-template-columns:1fr}.soundfont-actions{justify-content:flex-start;max-width:none}.soundfont-edit{grid-template-columns:1fr}.soundfont-edit>span{padding-top:0}.chord-timeline ol{grid-template-columns:repeat(2,minmax(0,1fr))}.project-row{grid-template-columns:minmax(0,1fr) 38px}}@media(max-width:700px){.composer-tabs{align-items:flex-start;flex-direction:column}.score-actions{width:100%}.file-import,.sample-file-button{flex:1}.workbench-layout{margin:0}.score-import-status{grid-template-columns:minmax(0,1fr) 42px}.score-import-status>span{font-size:.8rem}.transport-label{display:block}.transport-label span{display:block;margin-top:5px}.soundfont-bind-options,.soundfont-edit .soundfont-bind-options{grid-template-columns:1fr 1fr}.chord-timeline ol{grid-template-columns:1fr 1fr}}
  `;
  // Final overrides intentionally keep the local sound library dense: bindings are
  // available on demand, not a large always-open matrix that pushes the editor down.
  style.textContent += `
    .sample-library{padding:15px 16px}.sample-library-head{margin-bottom:8px}.soundfont-binding{display:flex!important;align-items:center!important;gap:8px;margin:8px 0 10px;padding:0;border:0;background:transparent}.soundfont-binding>b{font-size:.8rem;color:#735f54;white-space:nowrap}.soundfont-bind-options{display:flex!important;flex-wrap:wrap;gap:5px;width:auto}.soundfont-bind-options label{min-height:0!important;padding:4px 7px!important;border-radius:99px!important;font-size:.74rem!important}.soundfont-card{grid-template-columns:minmax(0,1fr) auto!important;gap:12px!important;padding:11px 0!important;border:0!important;border-bottom:1px solid #eee2d9!important;background:transparent!important}.soundfont-card:last-child{border-bottom:0!important}.soundfont-card-main{display:grid;grid-template-columns:28px minmax(0,1fr);gap:8px}.soundfont-file-icon{width:26px;height:26px;display:grid;place-items:center;border-radius:8px;background:#f7e6db;color:#a84d36}.soundfont-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}.soundfont-tags span{font-size:.69rem;padding:2px 6px}.soundfont-edit{display:flex!important;align-items:center;gap:8px;margin-top:8px!important;padding-top:8px!important;border-top:1px dashed #eadbd1}.pack-name-field{display:flex!important;align-items:center;gap:5px;margin:0!important;font-size:.75rem;color:#735f54}.pack-name-field input{width:160px!important;max-width:34vw!important;min-height:30px!important;padding:5px 7px!important}.pack-binding{position:relative}.pack-binding summary{list-style:none;cursor:pointer;padding:5px 7px;border:1px solid #e2d2c7;border-radius:8px;color:#8f4936;font-size:.75rem;font-weight:700;background:#fffdfa}.pack-binding summary::-webkit-details-marker{display:none}.pack-binding summary span{display:inline-grid;place-items:center;margin-left:4px;width:16px;height:16px;border-radius:50%;background:#f4e2d7;font-size:.65rem}.pack-binding .soundfont-bind-options{position:absolute;z-index:8;top:34px;left:0;width:260px;padding:8px;border:1px solid #e2d2c7;border-radius:10px;background:#fffdfa;box-shadow:0 12px 30px rgba(91,63,45,.16)}.soundfont-actions{display:flex!important;align-items:center;align-content:center;gap:7px;max-width:unset!important}.soundfont-actions .link{padding:4px 0!important;font-size:.76rem}.staff-caption{margin-bottom:4px!important}.staff-scroll{display:grid!important;justify-items:start!important;gap:3px!important;overflow:visible!important;padding:0!important}.staff-system{width:100%;max-width:980px;margin:0!important;padding:2px 0 5px!important;border:0!important;border-bottom:1px solid #eaded3!important;border-radius:0!important;background:transparent!important}.staff-system:last-child{border-bottom:0!important}.staff-system-head{margin:0 0 1px!important;font-size:.71rem!important}.staff-system svg{display:block;width:100%;max-width:840px;min-width:0!important;height:auto!important;max-height:none!important;margin:0!important}.staff-accidental{font-family:serif;font-size:14px;fill:#a84d36;stroke:none}.score-panel{padding:8px 10px!important}.chord-timeline{margin:8px 0!important;padding:9px 11px!important}.chord-timeline ol{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(62px,78px))!important;justify-content:start!important;overflow:visible!important;gap:5px!important;padding:7px 0 0!important}.chord-timeline li{min-width:0!important;min-height:42px;padding:5px 7px!important;border-radius:8px!important}.chord-timeline li small{font-size:.63rem!important;white-space:nowrap}.chord-timeline li b{font-size:.95rem!important}.toast{width:min(380px,calc(100vw - 30px));white-space:normal;line-height:1.45;box-shadow:0 12px 30px rgba(45,31,25,.22)}@media(max-width:860px){.soundfont-card{grid-template-columns:1fr!important}.soundfont-actions{justify-content:flex-start!important}.pack-name-field input{max-width:58vw!important}.soundfont-binding{align-items:flex-start!important;flex-direction:column}.pack-binding .soundfont-bind-options{width:min(260px,80vw)}.staff-system{max-width:100%}}@media(max-width:560px){.chord-timeline ol{grid-template-columns:repeat(4,minmax(0,1fr))!important}}
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
function staff(notes, title, meter = meterOf(), tempo = current?.tempo || 96) {
  // 谱面按小节自动分系统，且用七声音级（不是 MIDI 半音的线性坐标）定位。
  // 因此 C2 到 C7 都能落在正确的加线范围，不会被夹到五线谱边缘。
  const safe = [...(notes || [])].filter(n => Number.isFinite(Number(n.pitch))).sort((a, b) => Number(a.start) - Number(b.start)).slice(0, 192);
  const beatSeconds = 60 / Math.max(40, Number(tempo) || 96);
  const barSeconds = beatSeconds * Math.max(2, Number(meter.numerator) || 4);
  const availableWidth = document.querySelector(".workbench-layout")?.clientWidth || window.innerWidth || 840;
  const width = Math.max(320, Math.min(840, availableWidth - 24));
  const barsPerSystem = availableWidth < 560 ? 2 : 4;
  const lastEnd = safe.reduce((last, note) => Math.max(last, Number(note.start || 0) + Number(note.duration || 0)), 0);
  // 预览只显示实际有音符的范围，不按卷帘预留的小节数画空白谱表。
  const count = safe.length ? Math.max(1, Math.ceil(lastEnd / barSeconds)) : 1;
  const systems = Array.from({ length: Math.ceil(count / barsPerSystem) }, (_, index) => ({ start: index * barsPerSystem, end: Math.min(count, index * barsPerSystem + barsPerSystem) }));
  const degree = pitch => (Math.floor(Number(pitch) / 12) - 1) * 7 + [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][((Number(pitch) % 12) + 12) % 12];
  const sharp = pitch => [1, 3, 6, 8, 10].includes(((Number(pitch) % 12) + 12) % 12);
  const oneSystem = ({ start, end }) => {
    const startX = width < 500 ? 42 : 64, finishX = width - 14, gap = 9;
    const secondsStart = start * barSeconds, secondsEnd = end * barSeconds, span = Math.max(barSeconds, secondsEnd - secondsStart);
    const xAt = seconds => startX + Math.max(0, Math.min(1, (Number(seconds || 0) - secondsStart) / span)) * (finishX - startX);
    const notesInSystem = safe.filter(note => Number(note.start || 0) >= secondsStart && Number(note.start || 0) < secondsEnd);
    const hasTreble = !safe.length || notesInSystem.some(note => Number(note.pitch) >= 60);
    const hasBass = notesInSystem.some(note => Number(note.pitch) < 60);
    // Grand staff only when this line actually needs both registers. A single
    // register is vertically centered; this removes the empty half-staff seen
    // on the last line while keeping C2/C7 ledger notes inside the SVG viewport.
    const grand = hasTreble && hasBass;
    const trebleTop = grand ? 62 : 70, bassTop = grand ? 130 : 70;
    const viewHeight = grand ? 220 : 164;
    const stave = (clef, top, bottomDegree, predicate) => {
      const bottom = top + gap * 4, topDegree = bottomDegree + 8;
      const lines = [0, 1, 2, 3, 4].map(i => `<line x1="${startX}" y1="${top + i * gap}" x2="${finishX}" y2="${top + i * gap}"/>`).join("");
      const bars = Array.from({ length: end - start + 1 }, (_, i) => `<line class="staff-barline" x1="${xAt((start + i) * barSeconds)}" y1="${top}" x2="${xAt((start + i) * barSeconds)}" y2="${bottom}"/>`).join("");
      const notesOnStave = notesInSystem.filter(note => predicate(Number(note.pitch))).map(note => {
        const pitch = Number(note.pitch), x = xAt(note.start), noteDegree = degree(pitch), noteY = bottom - (noteDegree - bottomDegree) * (gap / 2);
        const up = noteDegree < bottomDegree + 4;
        const lowerLedger = Array.from({ length: Math.max(0, Math.ceil((bottomDegree - noteDegree) / 2)) }, (_, i) => bottom + (i + 1) * gap).map(y => `<line x1="${x - 10}" y1="${y}" x2="${x + 10}" y2="${y}"/>`).join("");
        const upperLedger = Array.from({ length: Math.max(0, Math.ceil((noteDegree - topDegree) / 2)) }, (_, i) => top - (i + 1) * gap).map(y => `<line x1="${x - 10}" y1="${y}" x2="${x + 10}" y2="${y}"/>`).join("");
        return `<g class="staff-note">${lowerLedger}${upperLedger}${sharp(pitch) ? `<text class="staff-accidental" x="${x - 15}" y="${noteY + 4}">♯</text>` : ""}<ellipse cx="${x}" cy="${noteY}" rx="6" ry="4.5" transform="rotate(-18 ${x} ${noteY})"/><line x1="${x + (up ? 5 : -5)}" y1="${noteY}" x2="${x + (up ? 5 : -5)}" y2="${noteY + (up ? -26 : 26)}"/></g>`;
      }).join("");
      return `<g>${lines}${bars}<text class="staff-clef ${clef === "𝄢" ? "bass" : ""}" x="${startX - 48}" y="${top + 31}">${clef}</text>${notesOnStave}</g>`;
    };
    const trebleMeter = `<text class="staff-meter" x="${startX - 13}" y="${trebleTop + 21}">${meter.numerator}</text><text class="staff-meter" x="${startX - 13}" y="${trebleTop + 34}">4</text>`;
    const bassMeter = grand ? `<text class="staff-meter" x="${startX - 13}" y="${bassTop + 21}">${meter.numerator}</text><text class="staff-meter" x="${startX - 13}" y="${bassTop + 34}">4</text>` : "";
    const empty = !safe.length ? '<text class="staff-empty" x="118" y="109">从键盘、卷帘或乐谱开始</text>' : "";
    return `<section class="staff-system"><div class="staff-system-head"><b>第 ${start + 1}${end > start + 1 ? `–${end}` : ""} 小节</b><span>${meter.numerator}/4 · ${end - start} 小节</span></div><svg class="music-staff" viewBox="0 0 ${width} ${viewHeight}" role="img" aria-label="第 ${start + 1} 到 ${end} 小节五线谱">${hasTreble ? `${trebleMeter}${stave("𝄞", trebleTop, 30, pitch => pitch >= 60)}` : ""}${hasBass ? `${bassMeter}${stave("𝄢", bassTop, 18, pitch => pitch < 60)}` : ""}${empty}</svg></section>`;
  };
  return `<div class="staff-caption"><b>${title}</b><span>${safe.length ? `${safe.length} 个音符 · ${meter.numerator}/4 · ${count} 小节 · 每行最多 ${barsPerSystem} 小节` : "从键盘、卷帘或乐谱开始"}</span></div><div class="staff-scroll">${systems.map(oneSystem).join("")}</div>`;
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
function projectCard(p) { return `<article class="project-row"><button class="workbench-project ${current?.id === p.id ? "active" : ""}" data-project="${p.id}"><b>${esc(p.title)}</b><small>${esc(p.style)} · ${p.tempo} BPM</small></button><button class="project-delete" data-delete-project="${p.id}" title="删除 ${esc(p.title)}" aria-label="删除工程 ${esc(p.title)}">×</button></article>`; }
function formatBytes(size) { return `${Math.max(1, Math.round(Number(size || 0) / 1024 / 1024 * 10) / 10)} MB`; }
function sampleLibrary(packs) {
  const selectable = ["guzheng", "erhu", "guitar", "violin", "drum"];
  const cards = packs.length ? packs.map(pack => `<article class="soundfont-card" data-pack-card="${esc(pack.id)}">
    <div class="soundfont-card-main"><div class="soundfont-file-icon">♫</div><div><b>${esc(pack.displayName || pack.name)}</b><small>本机已保存 · ${formatBytes(pack.size)} · 文件：${esc(pack.name)} · Preset：${esc(pack.presetName || "已解析")}</small><div class="soundfont-tags">${(pack.instruments || []).map(id => `<span>${esc(LABEL[id] || id)}${pack.activeFor?.includes(id) ? " · 当前" : ""}</span>`).join("") || "<span>尚未绑定乐器</span>"}</div>
      <div class="soundfont-edit"><label class="pack-name-field"><span>名称</span><input data-pack-name="${esc(pack.id)}" value="${esc(pack.displayName || pack.name.replace(/\.sf2$/i, ""))}" maxlength="80" aria-label="${esc(pack.name)} 的显示名称"></label><details class="pack-binding"><summary>绑定乐器 <span>${(pack.instruments || []).length || 0}</span></summary><div class="soundfont-bind-options">${selectable.map(id => `<label><input type="checkbox" data-pack-instrument="${esc(pack.id)}" value="${id}" ${(pack.instruments || []).includes(id) ? "checked" : ""}>${LABEL[id]}</label>`).join("")}</div></details></div></div></div>
    <div class="soundfont-actions"><button class="link" data-save-pack="${esc(pack.id)}">保存设置</button><button class="link" data-preview-pack="${esc(pack.id)}">试听音区</button><button class="link" data-preview-melody="${esc(pack.id)}">试听完整旋律</button><button class="link" data-activate-pack="${esc(pack.id)}">设为当前</button><button class="link danger-text" data-remove-pack="${esc(pack.id)}">移除</button></div>
  </article>`).join("") : `<div class="soundfont-empty"><b>还没有本机乐器音色包</b><span>导入后可修改名称、绑定乐器、试听音区与当前完整旋律；数据保存在本浏览器，刷新或重新登录仍保留。</span></div>`;
  return `<section class="sample-library"><div class="sample-library-head"><div><span class="eyebrow">LOCAL SOUND LIBRARY</span><h3>乐器音色包</h3><p id="sampleLoadStatus">音色包保存在此浏览器的本机库中；可在下方修改显示名称与绑定。</p></div><label class="sample-file-button">添加 .sf2 音色包<input id="samplePackUpload" type="file" accept=".sf2" multiple></label></div>
    <div class="soundfont-binding"><b>导入时绑定至</b><div class="soundfont-bind-options" id="samplePackInstruments">${selectable.map((id, index) => `<label><input type="checkbox" value="${id}" ${index === 0 ? "checked" : ""}> ${LABEL[id]}</label>`).join("")}</div></div>
    <div class="soundfont-list" id="soundfontList">${cards}</div></section>`;
}

function importStatusView() {
  if (!importState) return '<div id="scoreImportStatus" class="score-import-status empty" aria-live="polite"></div>';
  const icon = importState.kind === "success" ? "✓" : importState.kind === "error" ? "!" : "…";
  const failed = importState.kind === "error";
  // 原始 Audiveris 日志常有数千字符；页面只保留可读摘要。完整技术文本仍可按需展开，
  // 但不再把工作台撑成一整屏错误框。
  const detail = failed && importState.detail ? `<details class="score-import-detail"><summary>查看技术详情</summary><pre>${esc(String(importState.detail).slice(0, 900))}</pre></details>` : "";
  return `<div id="scoreImportStatus" class="score-import-status ${importState.kind || "running"}" aria-live="polite"><div><b>${icon} ${esc(importState.phase)}</b><small>${esc(importState.fileName || "")}</small>${detail}</div><div class="score-import-progress"><i style="width:${Math.max(0, Math.min(100, Number(importState.progress || 0)))}%"></i></div><span>${failed ? "失败" : `${Math.round(Number(importState.progress || 0))}%`}</span></div>`;
}
function scoreImportFailureSummary(message) {
  const raw = String(message || "");
  if (/No installed OCR languages/i.test(raw)) return "识谱失败：Audiveris 未安装 OCR 语言包。请安装 eng 语言包后重试。";
  if (/transcription did not complete|转录没有完成/i.test(raw)) return "识谱失败：这张乐谱未能完整转录。请使用单页、正向、五线完整且音符清晰的扫描件。";
  if (/找不到 Audiveris|AUDIVERIS_COMMAND|尚未配置/i.test(raw)) return "识谱失败：未找到 Audiveris。请检查本机 AUDIVERIS_COMMAND 配置。";
  if (/没有完成识别|timeout|超时/i.test(raw)) return "识谱超时：请裁剪为单页清晰乐谱后重试。";
  return "乐谱未能导入。请检查文件格式或展开技术详情查看原因。";
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
  return `<section class="workbench-stage"><div class="stage-heading"><div><span>当前工程 · ${project.tempo} BPM · ${esc(project.arrangement?.key || "待推断")}</span><h2>${esc(project.title)}</h2><p>${esc(project.arrangement?.tips || "正在等待生成声部")}</p></div><div class="stage-actions"><button class="button ghost" id="stopArrangement">停止</button><button class="button" id="playArrangement">▶ 从头播放</button></div></div>${chords}<section class="score-panel">${staff(project.melody, "主旋律五线谱 · 已同步到工程", meterOf(project), project.tempo)}</section><div class="track-list">${tracks.map(t => `<article class="music-track"><div class="track-icon">${t.instrument === "drum" ? "◉" : "♫"}</div><div><b>${esc(t.name)}</b><small>${esc(soundSourceLabel(t.instrument))} · ${t.notes.length} 个音符</small></div><label class="track-volume"><span>音量</span><input type="range" data-volume="${t.id}" min="0" max="100" value="82"></label><label class="track-mute"><input type="checkbox" data-mute="${t.id}"> 静音</label><button class="track-preview" data-preview-track="${t.id}">试听</button></article>`).join("")}</div></section>`;
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
  const refresh = () => { const notes = getNotes(), meter = getMeter(); root.querySelector("#notationPreview").innerHTML = staff(notes, "输入旋律预览", meter, +tempoInput.value || 96); root.querySelector("#rollMount").innerHTML = pianoRoll(notes, +tempoInput.value || 96, meter); bindRoll(); };
  bindRoll();
  root.querySelectorAll("[data-project]").forEach(b => b.onclick = async () => {
    const id = b.dataset.project;
    if (String(current?.id) === String(id)) return;
    root.querySelectorAll("[data-project]").forEach(item => item.disabled = true);
    b.classList.add("loading");
    try { current = await api.workbenchProject(id); await renderWorkbench(root); }
    catch (error) { notify(`打开工程失败：${error.message}`, "error"); root.querySelectorAll("[data-project]").forEach(item => item.disabled = false); b.classList.remove("loading"); }
  });
  root.querySelectorAll("[data-delete-project]").forEach(button => button.onclick = async event => {
    event.preventDefault();
    const id = button.dataset.deleteProject;
    const project = projects.find(item => String(item.id) === String(id));
    if (!project || !window.confirm(`删除编曲工程“${project.title}”？\n只删除该工程及其旋律/编曲数据，不删除本机音色包、教案或音频记录。`)) return;
    button.disabled = true;
    try {
      await api.deleteWorkbenchProject(id);
      if (String(current?.id) === String(id)) { current = null; draftNotes = null; draftProjectId = null; }
      notify(`已删除编曲工程：${project.title}`);
      await renderWorkbench(root);
    } catch (error) {
      button.disabled = false;
      notify(`删除工程失败：${error.message}`, "error");
    }
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
      const summary = scoreImportFailureSummary(err.message);
      setImportState(root, { kind: "error", fileName: file.name, phase: summary, progress: 0, detail: err.message });
      notify(summary, "error");
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
