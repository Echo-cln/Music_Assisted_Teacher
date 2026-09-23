import { api } from "../api/client.js";
import { esc, loading, notify, pageHeader } from "../utils/dom.js";
import { drawWaveform } from "../utils/waveform.js";

export async function renderFeedback(container) {
  const [songs, lessons] = await Promise.all([api.songs({}), api.lessons()]);
  container.innerHTML = pageHeader("音频对比与课后反馈", "有原唱时进行真实双波形对比；无原唱时显示明确标注的 80% 示意结果。") + `
    <div class="grid two">
      <div class="grid">
        <section class="card"><div class="form-grid">
          <label>对应歌曲<select id="songId">${songs.map(song => `<option value="${song.id}">${esc(song.name)} · ${esc(song.province)}</option>`).join("")}</select></label>
          <label>对应教案<select id="lessonId"><option value="">暂不关联</option>${lessons.map(plan => `<option value="${plan.id}">${esc(plan.title)} · ${esc(plan.class_name)}</option>`).join("")}</select></label>
          <label class="upload">课堂录音<input id="recording" type="file" accept="audio/*" required><small>必选，支持常见音频格式</small></label>
          <label class="upload">原唱音频<input id="original" type="file" accept="audio/*"><small>可选；数据库已有时无需重复上传</small></label>
        </div><button class="btn primary" id="analyze">生成波形与建议</button></section>
        <div id="analysis"></div>
      </div>
      <aside class="side-stack"><section class="card"><h3>课后反馈</h3><label>整体效果<select id="effect"><option>很好</option><option selected>较好</option><option>一般</option><option>较差</option></select></label><label>课堂亮点<textarea id="highlights"></textarea></label><label>存在问题<textarea id="problems"></textarea></label><label>下次改进<textarea id="improvement"></textarea></label><button class="btn primary block" id="saveFeedback" disabled>提交并回填班级画像</button></section><div class="notice">没有原唱时，80% 重叠和各项分数仅用于演示完整流程，不会标注为真实测量。</div></aside>
    </div>`;
  let latest = null;
  document.getElementById("analyze").onclick = async () => {
    const recording = document.getElementById("recording").files[0];
    if (!recording) return notify("请先上传课堂录音");
    const form = new FormData();
    form.append("song_id", document.getElementById("songId").value);
    form.append("recording", recording);
    const original = document.getElementById("original").files[0];
    if (original) form.append("original", original);
    const area = document.getElementById("analysis");
    area.innerHTML = loading("正在提取波形并分析");
    latest = await api.analyzeAudio(form);
    area.innerHTML = resultView(latest);
    drawWaveform(document.getElementById("referenceWave"), latest.reference_waveform, "#9f4b35");
    drawWaveform(document.getElementById("recordingWave"), latest.recording_waveform, "#547785");
    document.getElementById("saveFeedback").disabled = !document.getElementById("lessonId").value;
    notify(latest.is_demo ? "已生成明确标注的示意分析" : "真实双波形分析完成");
  };
  document.getElementById("saveFeedback").onclick = async () => {
    if (!latest) return;
    await api.feedback({ lesson_plan_id: Number(document.getElementById("lessonId").value), overall_effect: document.getElementById("effect").value, highlights: document.getElementById("highlights").value, problems: document.getElementById("problems").value, improvement: document.getElementById("improvement").value, analysis: latest });
    notify("反馈已归档并更新班级画像");
  };
}

function resultView(result) {
  return `<section class="card"><div class="card-head"><div><h3>《${esc(result.song_name)}》波形对比</h3><small>${result.is_demo ? "暂无原唱，以下为示意性对比" : "原唱与课堂录音真实对齐"}</small></div><span class="status ${result.is_demo ? "warn" : "ok"}">${result.is_demo ? "示意分析" : "真实分析"}</span></div>${result.is_demo ? '<div class="notice">参考波形不是原唱音频，重叠率与分数不代表真实测量。</div>' : ""}<div class="wave"><b>${result.is_demo ? "示意参考波形" : "数据库原唱"}</b><div id="referenceWave"></div></div><div class="wave"><b>课堂上传录音</b><div id="recordingWave"></div></div><div class="scores"><div><b>${result.overlap_percent}%</b><small>波形重叠</small></div>${Object.entries(result.scores).map(([key, value]) => `<div><b>${value}</b><small>${({pitch:"音准",rhythm:"节奏",volume:"音量",emotion:"情绪",participation:"参与度"})[key]}</small></div>`).join("")}</div><h3>改进建议</h3><ul>${result.suggestions.map(item => `<li>${esc(item)}</li>`).join("")}</ul></section>`;
}
