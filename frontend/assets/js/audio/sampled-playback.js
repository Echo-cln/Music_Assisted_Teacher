// 浏览器本地采样层：老师导入的 SF2 仅保存在本机 IndexedDB，绝不上传服务器。
// 真实播放按轨隔离；任一包或 CDN 失败都不会让其它乐器静音。
const SMPLR_URL = "https://unpkg.com/smplr@1.0.0/dist/index.mjs";
const SOUNDFONT2_PARSER_URLS = [
  "https://esm.sh/soundfont2@0.5.0?bundle",
  "https://cdn.jsdelivr.net/npm/soundfont2@0.5.0/+esm",
];

const DB_NAME = "xiangyin-local-soundfonts";
const DB_VERSION = 1;
const STORE = "packs";
const ACTIVE_KEY = "xiangyin-active-soundfonts";
let activeLoaded = false;
let audioContext;
let smplrPromise;
let catalogPromise;
const players = new Map();
const localPlayers = new Map(); // packId -> { player, url, name }
const activePackIds = new Map(); // instrument -> packId
const catalogNames = new Map();
const scheduledStops = [];

const standard = {
  piano: { kind: "piano", label: "采样三角钢琴" },
  violin: { kind: "soundfont", instrument: "violin", label: "采样小提琴" },
  guitar: { kind: "soundfont", instrument: "acoustic_guitar_nylon", label: "采样原声吉他" },
  drum: { kind: "drums", label: "采样课堂节奏鼓" },
};

function context() { return audioContext || (audioContext = new AudioContext()); }
function smplr() { return smplrPromise || (smplrPromise = import(SMPLR_URL)); }
function openDb() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) return reject(new Error("当前浏览器不支持本地音色库"));
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("无法打开本地音色库"));
  });
}
async function dbAll() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
    req.onsuccess = () => { db.close(); resolve(req.result || []); };
    req.onerror = () => { db.close(); reject(req.error); };
  });
}
async function dbPut(record) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite"); tx.objectStore(STORE).put(record);
    tx.oncomplete = () => { db.close(); resolve(); }; tx.onerror = () => { db.close(); reject(tx.error); };
  });
}
async function dbDelete(id) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite"); tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => { db.close(); resolve(); }; tx.onerror = () => { db.close(); reject(tx.error); };
  });
}
async function catalog() {
  if (!catalogPromise) catalogPromise = dbAll().then(rows => rows.sort((a, b) => b.createdAt - a.createdAt));
  return catalogPromise;
}
function resetCatalog() { catalogPromise = null; }
function restoreActive(packs) {
  if (activeLoaded) return;
  activeLoaded = true;
  try {
    const stored = JSON.parse(localStorage.getItem(ACTIVE_KEY) || "{}");
    Object.entries(stored).forEach(([instrument, id]) => {
      if (packs.some(pack => pack.id === id && (pack.instruments || []).includes(instrument))) activePackIds.set(instrument, id);
    });
  } catch (_) {}
}
function persistActive() { localStorage.setItem(ACTIVE_KEY, JSON.stringify(Object.fromEntries(activePackIds))); }
function packFor(instrument) {
  const id = activePackIds.get(instrument);
  return id ? localPlayers.get(id) : null;
}
function sourceNameFor(instrument) {
  const pack = packFor(instrument);
  const stored = catalogNames.get(activePackIds.get(instrument));
  return pack ? `${pack.displayName || pack.name}（本机 SF2）` : stored ? `${stored.name}（本机 SF2）` : standard[instrument]?.label || `${instrument}（未配置音源）`;
}
export const soundSourceLabel = sourceNameFor;
export async function getLocalSoundfontFile(packId) {
  const packs = await catalog();
  const record = packs.find(item => item.id === packId);
  if (!record?.blob) throw new Error("本机音色包已不存在，请重新导入");
  return record.blob;
}

export async function listLocalSoundfonts() {
  const packs = await catalog();
  restoreActive(packs);
  packs.forEach(pack => catalogNames.set(pack.id, { name: pack.displayName || pack.name }));
  return packs.map(({ blob, ...meta }) => ({ ...meta, activeFor: (meta.instruments || []).filter(id => activePackIds.get(id) === meta.id) }));
}

async function parserConstructor() {
  const failures = [];
  for (const url of SOUNDFONT2_PARSER_URLS) {
    try {
      const parser = await import(url);
      const candidate = [parser.SoundFont2, parser.default?.SoundFont2, parser.default].find(item => typeof item === "function" && item.prototype);
      if (candidate) return candidate;
      failures.push(`${new URL(url).host}：模块没有 SoundFont2 构造器`);
    } catch (error) { failures.push(`${new URL(url).host}：${error?.message || error}`); }
  }
  throw new Error(`SoundFont2 解析器不可用（${failures.join("；")}）。请检查浏览器是否拦截 CDN 或校园网代理。`);
}

async function buildPlayer(record, onProgress) {
  if (localPlayers.has(record.id)) return localPlayers.get(record.id);
  const [api, SoundFont2] = await Promise.all([smplr(), parserConstructor()]);
  const bytes = new Uint8Array(await record.blob.arrayBuffer());
  const parsed = new SoundFont2(bytes);
  const url = URL.createObjectURL(record.blob);
  try {
    const player = api.Soundfont2(context(), {
      url,
      createSoundfont: () => parsed,
      onLoadProgress: ({ loaded, total }) => onProgress?.({ loaded, total }),
    });
    await player.ready;
    const names = Array.isArray(player.instrumentNames) ? player.instrumentNames.filter(Boolean) : [];
    const name = record.presetName || names[0];
    if (!name) throw new Error("该 SF2 没有可播放的预设；请换用包含乐器 Preset 的标准 SF2 文件");
    await player.loadInstrument(name);
    const runtime = { player, url, name, displayName: record.displayName || record.name };
    localPlayers.set(record.id, runtime);
    return runtime;
  } catch (error) {
    URL.revokeObjectURL(url);
    const detail = error?.message || String(error);
    if (/reading ['\"]?1|undefined/i.test(detail)) throw new Error("该 SF2 使用了当前浏览器解析器不兼容的分区格式；请换用标准 SF2，而不是 SF3、压缩包或网页下载页。");
    throw error;
  }
}

/** 导入一个本机 SF2，可同时绑定到多个乐器；文件保留在当前浏览器的 IndexedDB。 */
export async function loadLocalSoundfont(instruments, file, onProgress) {
  const assigned = [...new Set((Array.isArray(instruments) ? instruments : [instruments]).filter(Boolean))];
  if (!file || !assigned.length) throw new Error("请选择至少一种要绑定的乐器和 .sf2 音源包");
  if (!/\.sf2$/i.test(file.name)) throw new Error("目前仅接受 .sf2 音源包；请确认其授权允许课堂使用");
  if (file.size < 16) throw new Error("SF2 文件太小或为空；请重新下载完整音源包");
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const signature = String.fromCharCode(...header.slice(0, 4));
  const form = String.fromCharCode(...header.slice(8, 12));
  if (signature !== "RIFF" || form !== "sfbk") throw new Error("文件扩展名是 .sf2，但内容不是标准 SoundFont2（缺少 RIFF/sfbk 文件头）。请确认下载的不是 .sf3、.zip 或网页错误页。");

  const record = { id: crypto.randomUUID(), name: file.name, displayName: file.name.replace(/\.sf2$/i, ""), instruments: assigned, blob: file, size: file.size, createdAt: Date.now(), presetName: "" };
  let runtime;
  try {
    runtime = await buildPlayer(record, onProgress);
    record.presetName = runtime.name;
    await dbPut(record);
    assigned.forEach(instrument => activePackIds.set(instrument, record.id));
    persistActive();
    resetCatalog();
    return { ...record, presetName: runtime.name };
  } catch (error) {
    const existing = localPlayers.get(record.id);
    if (existing?.url) URL.revokeObjectURL(existing.url);
    localPlayers.delete(record.id);
    throw error;
  }
}

export async function activateLocalSoundfont(packId, instrument) {
  const packs = await catalog(); restoreActive(packs);
  const record = packs.find(item => item.id === packId);
  if (!record || !(record.instruments || []).includes(instrument)) throw new Error("音色包不存在或未绑定该乐器");
  await buildPlayer(record);
  activePackIds.set(instrument, packId); persistActive();
  return record;
}

export async function previewLocalSoundfont(packId, instrument, onProgress, notes = null) {
  const packs = await catalog();
  const record = packs.find(item => item.id === packId);
  if (!record) throw new Error("找不到该本地音色包");
  const runtime = await buildPlayer(record, onProgress);
  const ctx = context(); await ctx.resume();
  runtime.player.stop?.();
  const now = ctx.currentTime + 0.08;
  // 默认试听覆盖低、中、高音区并包含一段完整乐句；传入 notes 时试听当前完整旋律。
  const phrase = Array.isArray(notes) && notes.length
    ? notes.map(note => ({ note: Number(note.pitch), time: now + Number(note.start || 0), duration: Math.max(.12, Number(note.duration || .3)), velocity: Number(note.velocity || 88) }))
    : [48, 52, 55, 60, 64, 67, 72, 67, 64, 60, 55, 52, 48, 60, 67, 72].map((note, index) => ({ note, time: now + index * .38, duration: .5, velocity: index % 4 === 0 ? 104 : 84 }));
  phrase.forEach(item => {
    const stop = runtime.player.start(item);
    if (typeof stop === "function") scheduledStops.push(stop);
  });
  if (instrument) { activePackIds.set(instrument, record.id); persistActive(); }
  return record;
}

export async function updateLocalSoundfont(packId, patch = {}) {
  const packs = await catalog();
  const record = packs.find(item => item.id === packId);
  if (!record) throw new Error("找不到该本地音色包");
  const displayName = String(patch.displayName ?? record.displayName ?? record.name).trim();
  const instruments = [...new Set((patch.instruments ?? record.instruments ?? []).filter(Boolean))];
  if (!displayName) throw new Error("请填写音色包名称");
  if (!instruments.length) throw new Error("请至少绑定一种乐器");
  record.displayName = displayName.slice(0, 80);
  record.instruments = instruments;
  for (const [instrument, activeId] of activePackIds) {
    if (activeId === record.id && !instruments.includes(instrument)) activePackIds.delete(instrument);
  }
  await dbPut(record); persistActive(); resetCatalog();
  const runtime = localPlayers.get(record.id);
  if (runtime) runtime.displayName = record.displayName;
  return record;
}

export async function removeLocalSoundfont(packId) {
  const packs = await catalog();
  const record = packs.find(item => item.id === packId);
  if (!record) return;
  (record.instruments || []).forEach(instrument => { if (activePackIds.get(instrument) === packId) activePackIds.delete(instrument); });
  persistActive();
  const runtime = localPlayers.get(packId);
  try { runtime?.player.stop?.(); } catch (_) {}
  if (runtime?.url) URL.revokeObjectURL(runtime.url);
  localPlayers.delete(packId);
  await dbDelete(packId); catalogNames.delete(packId); resetCatalog();
}

async function standardPlayer(instrument, notes, onProgress) {
  const key = `standard:${instrument}`;
  if (players.has(key)) return players.get(key);
  const api = await smplr();
  const options = { notesToLoad: { notes, fallback: "nearest" }, onLoadProgress: ({ loaded, total }) => onProgress?.({ instrument, loaded, total }) };
  let player;
  if (standard[instrument]?.kind === "piano") player = api.SplendidGrandPiano(context(), options);
  else if (standard[instrument]?.kind === "soundfont") player = api.Soundfont(context(), { ...options, instrument: standard[instrument].instrument, kit: "FluidR3_GM", loadLoopData: instrument === "violin" });
  else if (standard[instrument]?.kind === "drums") player = api.DrumMachine(context(), { ...options, instrument: "TR-808", notesToLoad: { notes: ["kick", "snare", "hat"] } });
  else return null;
  try { await player.ready; players.set(key, player); return player; }
  catch (error) { players.delete(key); try { player.stop?.(); } catch (_) {} throw error; }
}
function notesFor(trackNotes) { return [...new Set((trackNotes || []).map(note => Number(note.pitch)).filter(Number.isFinite))]; }
function drumName(pitch) { return pitch === 36 ? "kick" : pitch === 38 ? "snare" : "hat"; }
export function stopSampledPlayback() {
  scheduledStops.splice(0).forEach(stop => { try { stop(); } catch (_) {} });
  [...players.values(), ...[...localPlayers.values()].map(item => item.player)].forEach(player => { try { player.stop?.(); } catch (_) {} });
}
export async function playSampledTracks(tracks, { muted = new Set(), volume = {}, onProgress } = {}) {
  const ctx = context(); await ctx.resume(); stopSampledPlayback();
  const unavailable = [], failed = [], now = ctx.currentTime + 0.12;
  for (const track of (tracks || []).filter(track => !muted.has(track.id))) {
    const instrument = track.instrument;
    try {
      let pack = packFor(instrument);
      if (!pack && activePackIds.has(instrument)) {
        const packs = await catalog(); restoreActive(packs);
        const record = packs.find(item => item.id === activePackIds.get(instrument));
        if (record) pack = await buildPlayer(record, ({ loaded, total }) => onProgress?.({ instrument, loaded, total }));
      }
      const player = pack?.player || await standardPlayer(instrument, notesFor(track.notes), onProgress);
      if (!player) { unavailable.push(instrument); continue; }
      const gain = Math.max(0, Math.min(1, Number(volume[track.id] ?? 1)));
      for (const note of track.notes || []) {
        const stop = player.start({
          note: instrument === "drum" && !pack ? drumName(Number(note.pitch)) : Number(note.pitch),
          time: now + Number(note.start || 0), duration: Math.max(0.06, Number(note.duration || .2)),
          velocity: Math.max(1, Math.round(Number(note.velocity || 82) * gain)),
        });
        if (typeof stop === "function") scheduledStops.push(stop);
      }
    } catch (error) { failed.push({ track, message: error?.message || String(error) }); }
  }
  return { unavailable: [...new Set(unavailable)], failed };
}
