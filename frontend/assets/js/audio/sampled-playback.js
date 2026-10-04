// 真实采样播放层。只在点击播放后再加载，避免音源网络请求拖慢其它页面。
// smplr 为 MIT 许可；钢琴样本、GM 小提琴/吉他和节奏机样本均由其公开样本库提供。
// Pin the player/parser versions together: unversioned CDN imports can silently
// change their ESM export shape and break every local SF2 import at once.
const SMPLR_URL = "https://unpkg.com/smplr@1.0.0/dist/index.mjs";
const SOUNDFONT2_PARSER_URL = "https://esm.sh/soundfont2@0.5.0?bundle";

let audioContext;
let smplrPromise;
const players = new Map();
const customPacks = new Map();
const scheduledStops = [];

const standard = {
  piano: { kind: "piano", label: "采样三角钢琴" },
  violin: { kind: "soundfont", instrument: "violin", label: "采样小提琴" },
  guitar: { kind: "soundfont", instrument: "acoustic_guitar_nylon", label: "采样原声吉他" },
  // 这是节奏机采样，不把它标成非洲鼓。非洲鼓须由教师导入有授权的音源包。
  drum: { kind: "drums", label: "采样课堂节奏鼓" },
};

export const soundSourceLabel = instrument => {
  if (customPacks.has(instrument)) return `${customPacks.get(instrument).name}（自带授权 SF2）`;
  return standard[instrument]?.label || `${instrument}（未配置授权音源）`;
};

function context() {
  return audioContext || (audioContext = new AudioContext());
}

async function smplr() {
  if (!smplrPromise) smplrPromise = import(SMPLR_URL);
  return smplrPromise;
}

function notesFor(trackNotes) {
  return [...new Set((trackNotes || []).map(note => Number(note.pitch)).filter(Number.isFinite))];
}

function drumName(pitch) {
  if (pitch === 36) return "kick";
  if (pitch === 38) return "snare";
  return "hat";
}

async function standardPlayer(instrument, notes, onProgress) {
  const key = `standard:${instrument}`;
  if (players.has(key)) return players.get(key);
  const api = await smplr();
  const options = {
    notesToLoad: { notes, fallback: "nearest" },
    onLoadProgress: ({ loaded, total }) => onProgress?.({ instrument, loaded, total }),
  };
  let player;
  if (standard[instrument]?.kind === "piano") player = api.SplendidGrandPiano(context(), options);
  else if (standard[instrument]?.kind === "soundfont") player = api.Soundfont(context(), { ...options, instrument: standard[instrument].instrument, kit: "FluidR3_GM", loadLoopData: instrument === "violin" });
  else if (standard[instrument]?.kind === "drums") player = api.DrumMachine(context(), { ...options, instrument: "TR-808", notesToLoad: { notes: ["kick", "snare", "hat"] } });
  else return null;
  players.set(key, player);
  await player.ready;
  return player;
}

/**
 * 导入老师拥有授权的单音色 SF2。浏览器只在当前会话读取该文件；不会上传到服务器。
 * SF2 中有多个音色时默认使用第一个，返回的 name 会在界面明确显示。
 */
export async function loadLocalSoundfont(instrument, file, onProgress) {
  if (!file || !instrument) throw new Error("请选择要绑定的乐器和 .sf2 音源包");
  if (!/\.sf2$/i.test(file.name)) throw new Error("目前仅接受 .sf2 音源包；请确认其授权允许课堂使用");
  if (file.size < 16) throw new Error("SF2 文件太小或为空；请重新下载完整音源包");
  // Catch the common case where an SF3/ZIP/HTML download was renamed to .sf2.
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const signature = String.fromCharCode(...header.slice(0, 4));
  const form = String.fromCharCode(...header.slice(8, 12));
  if (signature !== "RIFF" || form !== "sfbk") {
    throw new Error("文件扩展名是 .sf2，但内容不是标准 SoundFont2（缺少 RIFF/sfbk 文件头）；请确认下载到的是 .sf2 而不是 .sf3/.zip/网页错误页");
  }
  const api = await smplr();
  let parser;
  try {
    parser = await import(SOUNDFONT2_PARSER_URL);
  } catch (error) {
    throw new Error(`SoundFont2 解析器加载失败（检查网络/CDN）：${error?.message || error}`);
  }
  // esm.sh may expose the package's named export in different namespace shapes
  // depending on its CJS/ESM wrapper. Resolve only actual constructors.
  const SoundFont2 = [parser.SoundFont2, parser.default?.SoundFont2, parser.default]
    .find(candidate => typeof candidate === "function" && candidate.prototype);
  if (!SoundFont2) {
    throw new Error("SoundFont2 解析器模块未提供可用构造器；请刷新页面重试，或检查 CDN 是否被代理/安全软件替换");
  }
  const url = URL.createObjectURL(file);
  const player = api.Soundfont2(context(), {
    url,
    createSoundfont: data => new SoundFont2(data instanceof Uint8Array ? data : new Uint8Array(data)),
    onLoadProgress: ({ loaded, total }) => onProgress?.({ instrument, loaded, total }),
  });
  try {
    await player.ready;
    const name = player.instrumentNames?.[0];
    if (!name) throw new Error("该 SF2 没有可播放的乐器音色");
    await player.loadInstrument(name);
    const old = customPacks.get(instrument);
    old?.url && URL.revokeObjectURL(old.url);
    customPacks.set(instrument, { player, name, url });
    return name;
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

export function stopSampledPlayback() {
  scheduledStops.splice(0).forEach(stop => { try { stop(); } catch (_) {} });
  [...players.values(), ...[...customPacks.values()].map(item => item.player)].forEach(player => { try { player.stop(); } catch (_) {} });
}

/** 播放可用的真实样本轨道；缺少授权包的传统乐器会明确跳过并返回原因。 */
export async function playSampledTracks(tracks, { muted = new Set(), volume = {}, onProgress } = {}) {
  const ctx = context();
  await ctx.resume();
  stopSampledPlayback();
  const playable = (tracks || []).filter(track => !muted.has(track.id));
  const unavailable = [];
  const now = ctx.currentTime + 0.12;
  for (const track of playable) {
    const instrument = track.instrument;
    let player = customPacks.get(instrument)?.player;
    if (!player) player = await standardPlayer(instrument, notesFor(track.notes), onProgress);
    if (!player) { unavailable.push(instrument); continue; }
    const gain = Math.max(0, Math.min(1, Number(volume[track.id] ?? 1)));
    for (const note of track.notes || []) {
      const stop = player.start({
        note: instrument === "drum" && !customPacks.has(instrument) ? drumName(Number(note.pitch)) : Number(note.pitch),
        time: now + Number(note.start || 0),
        duration: Math.max(0.06, Number(note.duration || 0.2)),
        velocity: Math.max(1, Math.round(Number(note.velocity || 82) * gain)),
      });
      if (typeof stop === "function") scheduledStops.push(stop);
    }
  }
  return { unavailable: [...new Set(unavailable)] };
}
