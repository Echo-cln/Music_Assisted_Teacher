import { api } from "../api/client.js?v=20261009-dialogue-trends";
import { lessonView } from "../components/lesson.js?v=20261007-2";
import { cancelActiveGeneration, getGenerationJob, refreshGeneration, startGeneration } from "../state/generation.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const regions = ["华南地区", "西南地区", "西北地区", "华中地区", "华东地区", "华北地区", "东北地区"];
let selectedSong = null;
let currentPlan = null;
let recommendedSongs = [];
let activeGenerationJobId = null;

function normalizeText(value) {
  if (Array.isArray(value)) return value.join("\n").replace(/\s+/g, " ").trim();
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value || "").replace(/\s+/g, " ").trim();
}
function adjustmentChanges(before, after) {
  const from = before?.content || before || {};
  const to = after?.content || after || {};
  const changes = [];
  const fields = [
    ["title", "教案标题"], ["objectives", "教学目标"], ["key_points", "教学重点"], ["difficulties", "教学难点"],
    ["preparation", "课前准备"], ["theory_explanation", "乐理讲解"], ["mistake_practice", "易错点练习"],
    ["differentiation", "分层教学"], ["assessment", "课堂评价"],
  ];
  fields.forEach(([key, label]) => { if (normalizeText(from[key]) !== normalizeText(to[key])) changes.push({ label, detail: "已按本次要求调整" }); });
  const beforeTimeline = from.timeline || [], afterTimeline = to.timeline || [];
  afterTimeline.forEach((stage, index) => {
    const old = beforeTimeline[index] || {};
    const changed = ["stage", "minutes", "teacher", "students", "device_action", "look_for", "low_device_option"]
      .some(key => normalizeText(old[key]) !== normalizeText(stage[key]));
    if (changed) changes.push({ label: `课堂流程 · ${stage.stage || `第 ${index + 1} 环节`}`, detail: "环节安排、时间或观察任务已更新" });
  });
  return changes.slice(0, 6);
}

function classOptions(classes, includeGeneral = false) {
  const general = includeGeneral ? '<option value="">通用模式（不指定班级）</option>' : "";
  return general + classes.map(item => `<option value="${item.id}">${esc(item.name)} · ${esc(item.rhythm_level)}</option>`).join("");
}

export async function renderAssistant(container) {
  const classes = await api.classes();
  container.innerHTML = pageHeader("教案助手", "按班级推荐歌曲，或手动选择歌曲生成教案。") + `
    <div class="grid two">
      <div class="grid">
        <section class="card planner-card">
          <div class="planner-mode-heading"><span class="eyebrow">备课方式</span><p>选择适合本次课堂的准备流程</p></div>
          <div class="planner-mode-tabs" role="tablist" aria-label="备课方式">
            <button class="planner-mode-option active" role="tab" aria-selected="true" data-planner-mode="form"><span class="planner-mode-index">01</span><span><strong>表单备课</strong><small>逐项指定课程条件</small></span></button>
            <button class="planner-mode-option" role="tab" aria-selected="false" data-planner-mode="dialogue"><span class="planner-mode-index">02</span><span><strong>对话备课</strong><small>用自然语言描述需求</small></span></button>
          </div>
          <div id="formModePanel">
            <div class="source-mode-section">
              <div class="source-mode-heading"><span>表单备课 · 歌曲选择</span><strong>选择歌曲来源</strong></div>
              <div id="sourceModeTabs" class="source-mode-tabs" role="tablist" aria-label="歌曲选择方式"><button class="source-mode-option active" role="tab" aria-selected="true" data-mode="smart">智能推荐</button><button class="source-mode-option" role="tab" aria-selected="false" data-mode="manual">手动指定</button></div>
            </div>
          <div id="smartForm" class="form-grid">
            <label>地区歌库<select id="region">${regions.map(region => `<option>${region}</option>`).join("")}</select></label>
            <label>授课班级<select id="classId">${classOptions(classes, true)}</select></label>
            <label>课时长度<select id="duration"><option value="40">40 分钟</option><option value="45">45 分钟</option><option value="30">30 分钟</option></select></label>
            <label>课堂偏好<select id="activity"><option>互动与分组合作</option><option>唱游与律动</option><option>地方文化体验</option><option>基础演唱训练</option></select></label>
            ${equipmentControls("smart")}
            <label>生成模式<select id="strategy"><option value="fast">快速模式 · 更快生成完整教案</option><option value="deep" selected>深度模式 · 生成时间较长</option></select></label>
            <label class="full">本课要求（选填）<textarea id="requirements" placeholder="填写设备条件、学生基础或课堂重点"></textarea></label><small class="muted full">歌曲信息、班级整体特征和本课要求会发送给你配置的模型服务以生成教案；请勿填写学生姓名、联系方式或可识别个人的信息。</small>
            <button class="btn primary" id="recommend">从数据库推荐歌曲</button>
          </div>
          <div id="manualForm" class="form-grid hidden">
            <label>歌曲名称<input id="songName" value="茉莉花"></label>
            <label>授课班级<select id="manualClassId">${classOptions(classes, true)}</select></label>
            <label>课时长度<select id="manualDuration"><option value="40">40 分钟</option><option value="45">45 分钟</option></select></label>
            <label>课堂偏好<select id="manualActivity"><option>互动与分组合作</option><option>唱游与律动</option><option>地方文化体验</option></select></label>
            ${equipmentControls("manual")}
            <label>生成模式<select id="manualStrategy"><option value="fast">快速模式 · 更快生成完整教案</option><option value="deep" selected>深度模式 · 生成时间较长</option></select></label>
            <label class="full">本课要求（选填）<textarea id="manualRequirements" placeholder="填写设备条件、学生基础或课堂重点"></textarea></label><small class="muted full">歌曲信息、班级整体特征和本课要求会发送给你配置的模型服务以生成教案；请勿填写学生姓名、联系方式或可识别个人的信息。</small>
            <button class="btn primary" id="manualGenerate">检索并生成教案</button>
          </div>
          </div>
          <div id="dialogueModePanel" class="dialogue-planning hidden">
            <div class="dialogue-intro"><span class="eyebrow">对话备课</span><h3>说说这节课怎么上</h3><p>可以从这节课最想解决的问题说起。班级、歌曲、课时或设备，想到哪项就先告诉我；我会结合班级画像梳理，再和你一起确认。</p></div>
            <div id="dialogueMessages" class="dialogue-messages" aria-live="polite">
              <div class="dialogue-message assistant"><span class="dialogue-avatar">助</span><div class="dialogue-bubble"><b>备课助手</b><p>你好，我是你的备课小助手。你可以先说说这节课最想解决什么，也可以告诉我班级、歌曲、时间和设备情况。我会参考已有班级画像整理条件，生成前先请你核对。</p><small>比如：三年级的孩子最近拍子总容易快。我想用《茉莉花》上一节40分钟的课，尽量多让他们动起来；教室没有投影，只有一台钢琴。</small></div></div>
            </div>
            <div class="dialogue-composer"><label class="sr-only" for="lessonBrief">描述本课需求</label><textarea id="lessonBrief" rows="2" placeholder="写下这节课的想法或限制…（Enter 发送，Shift + Enter 换行）"></textarea><button class="btn primary" id="extractLessonBrief" aria-label="发送备课需求">发送</button></div>
            <p class="dialogue-privacy-note">生成前会先展示识别出的条件，确认后才开始生成。</p>
          </div>
          <div id="recommendations"></div>
        </section>
        <div id="lessonArea"></div>
      </div>
      <aside class="side-stack">
        <section class="card"><h3>调整与保存</h3><p class="muted">生成期间可在右下角查看进度，也可以切换到其他页面。</p><label>调整要求<textarea id="adjustment" placeholder="写下希望修改的部分"></textarea></label><small class="muted">调整要求也会发送给配置的模型服务；请勿填写学生姓名或其他可识别个人的信息。</small><button class="btn block" id="adjustPlan" disabled>按要求调整预览</button><button class="btn primary block" id="savePlan" disabled>保存教案</button><button class="btn block" id="printPlan" disabled>打印 / 导出 PDF</button></section>
      </aside>
    </div>`;

  bindEquipmentControls(container);
  container.querySelectorAll("[data-planner-mode]").forEach(button => button.onclick=()=>{
    const dialog=button.dataset.plannerMode==="dialogue";
    container.querySelectorAll("[data-planner-mode]").forEach(item=>{const active=item===button;item.classList.toggle("active",active);item.setAttribute("aria-selected",String(active));});
    document.getElementById("formModePanel").classList.toggle("hidden",dialog);
    const smart=document.querySelector('[data-mode="smart"]').classList.contains("active");
    document.getElementById("smartForm").classList.toggle("hidden",!dialog&&!smart);
    document.getElementById("manualForm").classList.toggle("hidden",!dialog&&smart);
    document.getElementById("recommendations").classList.toggle("hidden",dialog);
    document.getElementById("dialogueModePanel").classList.toggle("hidden",!dialog);
  });
  document.getElementById("extractLessonBrief").onclick=()=>extractBrief(classes);
  document.getElementById("lessonBrief").addEventListener("keydown", event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();extractBrief(classes);}});
  container.querySelectorAll("[data-mode]").forEach(button => button.onclick = () => {
    container.querySelectorAll("[data-mode]").forEach(item => {const active=item===button;item.classList.toggle("active",active);item.setAttribute("aria-selected",String(active));});
    document.getElementById("smartForm").classList.toggle("hidden", button.dataset.mode !== "smart");
    document.getElementById("manualForm").classList.toggle("hidden", button.dataset.mode !== "manual");
  });

  document.getElementById("recommend").onclick = async () => {
    const regionValue = document.getElementById("region").value;
    const classValue = document.getElementById("classId").value;
    if (!classValue) return notify("智能推荐需要先选择一个班级；通用模式请使用手动指定");
    const list = await api.recommend({ region: regionValue, class_id: Number(classValue), limit: 3 });
    if (!list.length) return notify("当前地区暂无可推荐歌曲，可在资源库新增后再试");
    recommendedSongs = list;
    selectedSong = recommendedSongs[0];
    document.getElementById("recommendations").innerHTML = `<div class="recommendations">${recommendedSongs.map((song, index) => songCard(song, index === 0)).join("")}</div><p class="selection-status" id="selectionStatus">已选择：${esc(selectedSong.name)}</p><button class="btn primary" id="generateSelected">根据所选歌曲生成详细教案</button>`;
    bindSongCards(document.getElementById("recommendations"));
    document.getElementById("generateSelected").onclick = () => generate(false);
  };

  document.getElementById("manualGenerate").onclick = async () => {
    const songs = await api.songs({ q: document.getElementById("songName").value.trim() });
    if (!songs.length) return notify("数据库中没有找到这首歌曲，可先到教学资源库新增");
    selectedSong = songs[0];
    await generate(true);
  };

  document.getElementById("adjustPlan").onclick = async () => {
    const instruction = document.getElementById("adjustment").value.trim();
    if (!instruction) return notify("请填写修改要求");
    await streamPreviewAdjustment(document.getElementById("lessonArea"), instruction);
  };

  document.getElementById("savePlan").onclick = async () => {
    if (!currentPlan || currentPlan.is_saved) return;
    const button = document.getElementById("savePlan");
    button.disabled = true;
    button.textContent = "正在保存…";
    try {
      currentPlan = await api.saveLesson({
        song_id: currentPlan.song_id,
        class_id: currentPlan.class_id,
        duration_minutes: currentPlan.duration_minutes,
        teacher_requirements: currentPlan.content.teacher_requirements || "",
        generation_mode: currentPlan.generation_mode,
        content: currentPlan.content,
      });
      renderPreview(document.getElementById("lessonArea"), false);
      button.textContent = "已保存到教案与课堂记录";
      document.getElementById("adjustPlan").disabled = true;
      notify("教案已保存，现在可在“教案与课堂记录”中查看");
    } catch (error) {
      button.disabled = false;
      button.textContent = "保存教案";
      const prefix = error?.status ? `保存失败（HTTP ${error.status}）：` : "保存教案失败：";
      notify(`${prefix}${error.message || "请检查后端日志后重试"}`, "error");
    }
  };
  document.getElementById("printPlan").onclick = () => window.print();

  window.addEventListener("generation:update", updateFromGenerationEvent);
  const job = await refreshGeneration();
  restoreJob(job, true);
}


function appendDialogueMessage(role, content, options = {}) {
  const transcript = document.getElementById("dialogueMessages");
  if (!transcript) return null;
  const message = document.createElement("div");
  message.className = `dialogue-message ${role}${options.pending ? " is-pending" : ""}`;
  const avatar = document.createElement("span");
  avatar.className = "dialogue-avatar";
  avatar.textContent = role === "user" ? "我" : "助";
  const bubble = document.createElement("div");
  bubble.className = "dialogue-bubble";
  if (options.html) {
    bubble.innerHTML = `<b>${role === "user" ? "你" : "备课助手"}</b>${content}`;
  } else {
    const heading = document.createElement("b");
    heading.textContent = role === "user" ? "你" : "备课助手";
    const body = document.createElement("p");
    body.textContent = content;
    bubble.append(heading, body);
  }
  message.append(avatar, bubble);
  transcript.append(message);
  transcript.scrollTop = transcript.scrollHeight;
  return message;
}

async function extractBrief(classes) {
  const input = document.getElementById("lessonBrief");
  const prompt = input.value.trim();
  if (prompt.length < 8) return notify("请先描述歌曲、班级或课堂需求");
  const selectedClassId = Number(document.getElementById("classId").value || document.getElementById("manualClassId").value) || null;
  const button = document.getElementById("extractLessonBrief");
  button.disabled = true;
  button.textContent = "整理中…";
  document.querySelectorAll(".brief-confirmation").forEach(item => item.remove());
  appendDialogueMessage("user", prompt);
  input.value = "";
  const pending = appendDialogueMessage("assistant", "我先把班级、歌曲、课时和设备要求整理出来…", { pending: true });
  try {
    const response = await api.extractLessonBrief({ prompt, class_id: selectedClassId });
    pending?.remove();
    const parsed = response.parsed || {};
    const normalized = value => String(value || "").replace(/\s/g, "").toLowerCase();
    let chosenClass = parsed.class_name ? classes.find(item => normalized(item.name) === normalized(parsed.class_name)) : null;
    if (!chosenClass) chosenClass = classes.find(item => item.id === selectedClassId) || classes[0] || null;
    const profile = classes.find(item => item.id === chosenClass?.id) || response.class_profile || {};
    const classMismatch = parsed.class_name && !classes.some(item => normalized(item.name) === normalized(parsed.class_name));
    const currentClass = classes.find(item => item.id === selectedClassId);
    const classConflict = chosenClass && currentClass && chosenClass.id !== currentClass.id;
    const profileText = profile ? [profile.grade ? profile.grade + "年级" : "", profile.province, profile.learning_level, "音准：" + profile.pitch_level, "节奏：" + profile.rhythm_level, "合作：" + profile.cooperation, profile.common_problems].filter(Boolean).join(" · ") : "尚未选择班级画像";
    const currentDuration = Number(document.getElementById("duration").value || document.getElementById("manualDuration").value) || 40;
    const currentActivity = document.getElementById("activity").value || document.getElementById("manualActivity").value;
    const songFallback = selectedSong?.name || document.getElementById("songName").value.trim() || "";
    const regionFallback = profile.province || document.getElementById("region").value;
    const options = classes.map(item => `<option value="${item.id}" ${item.id === chosenClass?.id ? "selected" : ""}>${esc(item.name)} · ${esc(item.grade)}年级 · ${esc(item.province)}</option>`).join("");
    const parsedDevices = Array.isArray(parsed.equipment_constraints) ? parsed.equipment_constraints.join("、") : String(parsed.equipment_constraints || "");
    const activeMode = document.querySelector("#sourceModeTabs [data-mode].active")?.dataset.mode;
    const currentDevicePanel = document.querySelector(`[data-equipment-controls="${activeMode === "manual" ? "manual" : "smart"}"] [data-equipment-summary]`);
    const devices = parsedDevices || currentDevicePanel?.value || "";
    const currentRequirements = document.getElementById("requirements").value.trim() || document.getElementById("manualRequirements").value.trim();
    const requirements = String(parsed.teacher_requirements || currentRequirements || "");
    const strategyFallback = document.getElementById("strategy").value || document.getElementById("manualStrategy").value || "deep";
    const song = parsed.song_name || songFallback || "尚未指定";
    const className = chosenClass?.name || "通用模式";
    const duration = Number(parsed.duration_minutes) || currentDuration;
    const activity = parsed.activity_preference || profile.preferred_method || currentActivity || "互动与分组合作";
    const chips = [className, song === "尚未指定" ? song : `《${song}》`, `${duration} 分钟`, activity].map(item => `<span class="dialogue-condition-chip">${esc(item)}</span>`).join("");
    const warning = classMismatch ? `<div class="notice">识别到“${esc(parsed.class_name)}”，但教师档案中没有同名班级。请选择已有班级，或选通用模式。</div>` : "";
    const conflict = classConflict ? `<div class="notice">对话中识别为“${esc(chosenClass.name)}”，与表单当前选择的“${esc(currentClass.name)}”不同。请核对下面已预选的班级。</div>` : "";
    const confirmationHtml = `<div class="brief-confirmation">
      <div class="brief-confirmation-head"><div><span class="eyebrow">备课条件已整理</span><h3>这节课我理解的是</h3></div><span class="status info">请确认</span></div>
      <div class="dialogue-condition-chips">${chips}</div>
      <p class="dialogue-response-copy">我会结合班级画像安排活动，并把设备限制写进具体教学环节。请确认条件；需要调整时可以展开编辑。</p>
      ${warning}${conflict}
      <div class="brief-profile-context"><b>班级画像参考</b><span>${esc(profileText || "尚未选择班级画像")}</span></div>
      <details class="brief-edit-details"><summary>检查或修改备课条件</summary>
        <div class="form-grid brief-fields">
          <label>授课班级<select id="briefClassId"><option value="">通用模式（不指定班级）</option>${options}</select></label>
          <label>歌曲<input id="briefSong" value="${esc(parsed.song_name || songFallback)}" placeholder="请输入歌名"></label>
          <label>课时（分钟）<input id="briefDuration" type="number" min="20" max="90" value="${Number(parsed.duration_minutes) || currentDuration}"></label>
          <label>课堂偏好<input id="briefActivity" value="${esc(activity)}"></label>
          <label>地区 / 文化元素<input id="briefRegion" value="${esc(parsed.region_element || regionFallback || "")}" placeholder="没有明确要求可留空"></label>
          <label>设备条件与限制<input id="briefDevices" value="${esc(devices)}" placeholder="例如：无投影、无音箱"></label>
          <label class="full">其他课堂要求<textarea id="briefRequirements" rows="2">${esc(requirements)}</textarea></label>
          <label>生成模式<select id="briefStrategy"><option value="fast" ${strategyFallback === "fast" ? "selected" : ""}>快速模式</option><option value="deep" ${strategyFallback !== "fast" ? "selected" : ""}>深度模式</option></select></label>
        </div>
      </details>
      <p class="muted brief-sync-note">确认后会同步到表单备课条件。</p>
      <button class="btn primary" id="confirmBriefGenerate">确认条件并生成教案</button>
    </div>`;
    appendDialogueMessage("assistant", confirmationHtml, { html: true });
    bindBriefSettings(classes);
    bindDialogToForms();
    document.getElementById("confirmBriefGenerate").onclick = async () => {
      const classId = Number(document.getElementById("briefClassId").value) || null;
      const songName = document.getElementById("briefSong").value.trim();
      if (!songName) return notify("请补充歌曲名称");
      const songs = await api.songs({ q: songName });
      if (!songs.length) return notify(`资源库中未找到《${songName}》，请先到教学资源库添加歌曲`);
      selectedSong = songs.find(songItem => normalized(songItem.name) === normalized(songName));
      if (!selectedSong) return notify(`检索到了相近歌曲（${songs.slice(0, 4).map(songItem => songItem.name).join("、")}），请把输入名称改成资源库中的准确歌名后再生成`);
      const duration = Math.max(20, Math.min(90, Number(document.getElementById("briefDuration").value) || 40));
      const confirmedActivity = document.getElementById("briefActivity").value.trim() || profile.preferred_method || "互动与分组合作";
      const region = document.getElementById("briefRegion").value.trim();
      const device = document.getElementById("briefDevices").value.trim() || "未额外指定设备";
      const extra = document.getElementById("briefRequirements").value.trim();
      const strategy = document.getElementById("briefStrategy").value;
      const teacherRequirements = [extra, region ? `地区/文化元素：${region}` : "", `课堂设备条件：${device}`].filter(Boolean).join("\n");
      applyBriefToForms({ classId, songName, duration, activity: confirmedActivity, teacherRequirements, strategy, region });
      await generate(false, { song_id: selectedSong.id, class_id: classId, duration_minutes: duration, activity_preference: confirmedActivity, teacher_requirements: teacherRequirements, generation_strategy: strategy });
    };
  } catch (error) {
    pending?.remove();
    input.value = prompt;
    appendDialogueMessage("assistant", `这次没有整理成功：${error.message || "请检查连接后重试"}`);
    console.error("备课条件整理失败", error);
  } finally {
    button.disabled = false;
    button.textContent = "发送";
  }
}

function applyBriefToForms(settings) {
  for(const id of ["classId","manualClassId"]) { const el=document.getElementById(id); if(el)el.value=settings.classId?String(settings.classId):""; }
  for(const id of ["duration","manualDuration"]) { const el=document.getElementById(id); if(el)el.value=String(settings.duration); }
  for(const id of ["activity","manualActivity"]) { const el=document.getElementById(id); if(el)el.value=settings.activity; }
  for(const id of ["requirements","manualRequirements"]) { const el=document.getElementById(id); if(el)el.value=settings.teacherRequirements; }
  document.getElementById("songName").value=settings.songName;

  for(const panel of document.querySelectorAll("[data-equipment-summary]")) panel.value=settings.device||"未额外指定设备";
  for(const id of ["strategy","manualStrategy"]) { const el=document.getElementById(id); if(el)el.value=settings.strategy; }
  const briefClass=document.getElementById("briefClassId");if(briefClass)briefClass.value=settings.classId?String(settings.classId):"";
  const briefDuration=document.getElementById("briefDuration");if(briefDuration)briefDuration.value=String(settings.duration);
  const briefActivity=document.getElementById("briefActivity");if(briefActivity)briefActivity.value=settings.activity;

  const briefRegion=document.getElementById("briefRegion");if(briefRegion)briefRegion.value=settings.region||"";
  const briefStrategy=document.getElementById("briefStrategy");if(briefStrategy)briefStrategy.value=settings.strategy;
}

function bindBriefSettings(classes) {
  const pairs=[["classId","manualClassId","briefClassId"],["duration","manualDuration","briefDuration"],["activity","manualActivity","briefActivity"],["requirements","manualRequirements","briefRequirements"]];
  pairs.forEach(group=>group.forEach(id=>{
    const field=document.getElementById(id);if(!field)return;
    field.addEventListener("input",()=>syncGroup(group,id));
    field.addEventListener("change",()=>syncGroup(group,id));
  }));
  function syncGroup(group,sourceId){
    const source=document.getElementById(sourceId);
    group.forEach(id=>{const target=document.getElementById(id);if(target&&target!==source)target.value=source.value;});
    const classId=Number(document.getElementById("briefClassId")?.value||document.getElementById("classId").value)||null;
    const profileName=[...document.getElementById("briefClassId")?.options||[]].find(o=>Number(o.value)===classId)?.textContent||"";
    const fact=document.querySelector(".brief-profile-context span");
    if(fact&&sourceId.toLowerCase().includes("class")){
      const profile=classes.find(item=>item.id===classId);
      fact.textContent=profile?[profile.grade+"年级",profile.province,profile.learning_level,"音准："+profile.pitch_level,"节奏："+profile.rhythm_level,"合作："+profile.cooperation,profile.common_problems].filter(Boolean).join(" · "):"通用模式（不指定班级）";
    }
  }
  [["strategy","manualStrategy","briefStrategy"],["songName","songName","briefSong"]].forEach(group=>group.forEach(id=>{
    const field=document.getElementById(id);if(!field)return;
    field.addEventListener("input",()=>syncGroup(group,id));field.addEventListener("change",()=>syncGroup(group,id));
  }));
  const region=document.getElementById("region"), briefRegion=document.getElementById("briefRegion");
  region?.addEventListener("change",()=>{if(briefRegion)briefRegion.value=region.value;});
  document.querySelectorAll("[data-equipment-summary]").forEach(field=>field.addEventListener("change",()=>{
    const devices=document.getElementById("briefDevices");if(devices)devices.value=field.value;
  }));
}

function bindDialogToForms(){
  const dialogIds=["briefClassId","briefSong","briefDuration","briefActivity","briefRegion","briefDevices","briefRequirements","briefStrategy"];
  const sync=()=>{
    const raw=document.getElementById("briefRequirements").value.trim();
    const region=document.getElementById("briefRegion").value.trim();
    const device=document.getElementById("briefDevices").value.trim()||"未额外指定设备";
    const requirements=[raw,region?`地区/文化元素：${region}`:"",`课堂设备条件：${device}`].filter(Boolean).join("\\n");
    applyBriefToForms({
      classId:Number(document.getElementById("briefClassId").value)||null,
      songName:document.getElementById("briefSong").value.trim(),
      duration:Number(document.getElementById("briefDuration").value)||40,
      activity:document.getElementById("briefActivity").value.trim(),
      teacherRequirements:requirements,device,
      strategy:document.getElementById("briefStrategy").value,
    });
  };
  dialogIds.forEach(id=>{const field=document.getElementById(id);field?.addEventListener("input",sync);field?.addEventListener("change",sync);});
}

function songCard(song, active) {
  return `<article class="song-card ${active ? "selected" : ""}" data-song-id="${song.id}" tabindex="0" role="button" aria-pressed="${active}"><div><span class="eyebrow">规则适配分 ${song.match_score}/100</span><h3>《${esc(song.name)}》</h3><p>${esc(song.province)} · ${esc(song.grade)} · ${esc(song.mood)} · ${esc(song.difficulty)}</p><small>${esc(song.reason)}</small></div><button type="button" class="btn soft" data-choose-song="${song.id}">${active ? "已选择" : "选择"}</button></article>`;
}

function bindSongCards(root) {
  const choose = id => {
    selectedSong = recommendedSongs.find(song => song.id === Number(id));
    if (!selectedSong) return;
    const manualSong=document.getElementById("songName"), briefSong=document.getElementById("briefSong");
    if(manualSong)manualSong.value=selectedSong.name;
    if(briefSong)briefSong.value=selectedSong.name;
    root.querySelectorAll(".song-card").forEach(card => {
      const active = Number(card.dataset.songId) === selectedSong.id;
      card.classList.toggle("selected", active);
      card.setAttribute("aria-pressed", String(active));
      const button = card.querySelector("[data-choose-song]");
      if (button) button.textContent = active ? "已选择" : "选择";
    });
    const status = root.querySelector("#selectionStatus");
    if (status) status.textContent = `已选择：${selectedSong.name}`;
  };
  root.querySelectorAll(".song-card").forEach(card => {
    card.onclick = event => { if (!event.target.closest("button") || event.target.matches("[data-choose-song]")) choose(card.dataset.songId); };
    card.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(card.dataset.songId); } };
  });
}

function equipmentControls(id) {
  return '<fieldset class="equipment-panel full" data-equipment-controls="' + id + '">' +
    '<legend>课堂可用设备（可多选）</legend><p>只勾选本节确实能用的设备，教案会据此安排播放、投影或无设备替代活动。</p>' +
    '<label class="equipment-preset">快速选择<select data-equipment-preset><option value="custom">自定义设备</option><option value="none">无电子设备</option><option value="phone">手机播放</option><option value="computer">电脑播放</option><option value="computer-speaker">电脑 + 音箱</option><option value="classroom">电脑 + 投影 + 音箱</option></select></label>' +
    '<div class="equipment-options">' +
    '<label class="check-pill"><input type="checkbox" data-equipment="phone"><span>手机 / 平板</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="computer"><span>电脑</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="speaker"><span>外接音箱</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="projector"><span>投影 / 大屏</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="instrument"><span>课堂乐器 / 节奏乐器</span></label>' +
    '<label class="check-pill"><input type="checkbox" data-equipment="offline"><span>音频已下载，可离线播放</span></label>' +
    '</div><div class="tag-editor equipment-tag-editor" data-equipment-tag-editor><div class="tag-chip-list" data-tag-list></div><input type="text" data-tag-input placeholder="其他设备或音源，按回车添加"><input type="hidden" data-equipment-custom-tags></div>' +
    '<input type="hidden" data-equipment-summary></fieldset>';
}

function bindTagEditor(editor) {
  const input = editor.querySelector("[data-tag-input]");
  const list = editor.querySelector("[data-tag-list]");
  const hidden = editor.querySelector("[data-equipment-custom-tags], [data-student-difference-custom]");
  let tags = (hidden?.value || "").split(/[、,，;；\n]+/).map(value => value.trim()).filter(Boolean);
  const render = () => {
    if (hidden) hidden.value = tags.join("、");
    list.innerHTML = tags.map(value => `<span class="custom-tag-chip">${esc(value)}<button type="button" data-remove-tag="${esc(value)}" aria-label="删除标签">×</button></span>`).join("");
    list.querySelectorAll("[data-remove-tag]").forEach(button => button.onclick = () => {
      tags = tags.filter(value => value !== button.dataset.removeTag);
      render();
      editor.dispatchEvent(new CustomEvent("tags:change"));
    });
  };
  const add = raw => {
    for (const value of raw.split(/[、,，;；\n]+/).map(item => item.trim()).filter(Boolean)) {
      if (!tags.includes(value)) tags.push(value);
    }
    input.value = "";
    render();
    editor.dispatchEvent(new CustomEvent("tags:change"));
  };
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === "," || event.key === "，") {
      event.preventDefault();
      add(input.value);
    }
  });
  input.addEventListener("blur", () => { if (input.value.trim()) add(input.value); });
  render();
  return () => [...tags];
}

function bindEquipmentControls(root) {
  const labels = { phone: "手机", computer: "电脑", speaker: "外接音箱", projector: "投影/大屏", instrument: "课堂乐器/节奏乐器", offline: "音频已下载可离线播放" };
  const presets = {
    none: [],
    phone: ["phone", "offline"],
    computer: ["computer", "offline"],
    "computer-speaker": ["computer", "speaker", "offline"],
    classroom: ["computer", "speaker", "projector", "offline"],
  };
  root.querySelectorAll("[data-equipment-controls]").forEach(panel => {
    const boxes = [...panel.querySelectorAll("[data-equipment]")];
    const summary = panel.querySelector("[data-equipment-summary]");
    const preset = panel.querySelector("[data-equipment-preset]");
    const customTags = bindTagEditor(panel.querySelector("[data-equipment-tag-editor]"));
    const syncSummary = () => {
      const selected = boxes.filter(box => box.checked).map(box => labels[box.dataset.equipment]);
      summary.value = [...selected, ...customTags()].join("、") || "无电子设备（教师清唱与身体声势）";
      summary.dispatchEvent(new Event("change", { bubbles: true }));
    };
    boxes.forEach(box => box.addEventListener("change", () => {
      preset.value = "custom";
      syncSummary();
    }));
    panel.querySelector("[data-equipment-tag-editor]").addEventListener("tags:change", syncSummary);
    preset.addEventListener("change", () => {
      const chosen = presets[preset.value];
      if (!chosen) return;
      boxes.forEach(box => { box.checked = chosen.includes(box.dataset.equipment); });
      syncSummary();
    });
    syncSummary();
  });
}

async function generate(manual, override = null) {
  if (!selectedSong) return notify("请先选择歌曲");
  const classElement = document.getElementById(manual ? "manualClassId" : "classId");
  const durationElement = document.getElementById(manual ? "manualDuration" : "duration");
  const activityElement = document.getElementById(manual ? "manualActivity" : "activity");
  const requirementsElement = document.getElementById(manual ? "manualRequirements" : "requirements");
  const equipmentElement = document.querySelector(`[data-equipment-controls="${manual ? "manual" : "smart"}"] [data-equipment-summary]`);
  const strategyElement = document.getElementById(manual ? "manualStrategy" : "strategy");
  const payload = override || {
    song_id: selectedSong.id,
    class_id: classElement.value ? Number(classElement.value) : null,
    duration_minutes: Number(durationElement.value),
    activity_preference: activityElement.value,
    teacher_requirements: [requirementsElement.value.trim(), `[课堂设备条件：${equipmentElement.value || "无电子设备（教师清唱与身体声势）"}]`].filter(Boolean).join("\n"),
    generation_strategy: strategyElement.value,
  };
  payload.song_id = selectedSong.id;
  disableActions(true);
  try {
    const job = await startGeneration(payload);
    activeGenerationJobId = job.id || job.job_id || null;
    currentPlan = job.preview;
    renderPreview(document.getElementById("lessonArea"), true, job);
    notify(strategyElement.value === "fast" ? "正在快速生成完整教案" : "正在生成完整教案（深度模式）");
  } catch (error) {
    disableActions(false);
    document.getElementById("lessonArea").innerHTML = `<div class="notice">${esc(error.message)}</div>`;
  }
}

function updateFromGenerationEvent(event) {
  restoreJob(event.detail);
}

function restoreJob(job, restoredFromCenter = false) {
  const area = document.getElementById("lessonArea");
  if (!area || !job) return;
  const previousResult = restoredFromCenter || (activeGenerationJobId && job.id && job.id !== activeGenerationJobId);
  if (job.status === "completed" && job.result) {
    currentPlan = job.result;
    renderPreview(area, false, job);
    if(previousResult){
      area.insertAdjacentHTML("afterbegin",`<div class="notice previous-plan-notice"><b>上次生成结果</b><span>对应：${esc(currentPlan.class_name||"通用模式")} · ${Number(currentPlan.duration_minutes)||"—"} 分钟。本条不是当前设置下的新结果；请核对班级和课时后再决定是否保存。</span></div>`);
      disableActions(true);
      document.getElementById("printPlan").disabled=false;
    }else disableActions(false);
    return;
  }
  if (job.status === "failed") {
    currentPlan = job.preview || null;
    if (currentPlan) renderPreview(area, false, job);
    if(previousResult) area.insertAdjacentHTML("afterbegin",`<div class="notice previous-plan-notice">上次生成任务对应：${esc(currentPlan?.class_name||"未指定班级")}，不是当前设置的结果。</div>`);
    area.insertAdjacentHTML("afterbegin", `<div class="notice">教案完善未完成：${esc(job.error_message || "请稍后重试")}。下方仍保留规则生成的可用教案骨架。</div>`);
    disableActions(previousResult);
    if(previousResult){document.getElementById("savePlan").textContent="请按当前条件重新生成";document.getElementById("printPlan").disabled=false;}
    return;
  }
  if (job.preview) {
    currentPlan = job.preview;
    renderPreview(area, true, job);
    if(previousResult)area.insertAdjacentHTML("afterbegin",`<div class="notice previous-plan-notice">恢复中的任务对应：${esc(currentPlan.class_name||"未指定班级")} · ${Number(currentPlan.duration_minutes)||"—"} 分钟。</div>`);
    disableActions(previousResult);
  }
}

function disableActions(generating) {
  const adjust = document.getElementById("adjustPlan");
  const save = document.getElementById("savePlan");
  const print = document.getElementById("printPlan");
  if (!adjust || !save || !print) return;
  adjust.disabled = generating || !currentPlan;
  save.disabled = generating || !currentPlan || currentPlan.is_saved;
  print.disabled = !currentPlan;
  save.textContent = currentPlan?.is_saved ? "已保存到教案与课堂记录" : generating ? "完善完成后可保存" : "保存教案";
}


function manualEditorField(label, path, value, rows) {
  const text = Array.isArray(value) ? value.join("\n") : String(value ?? "");
  return '<label class="full">' + esc(label) + '<textarea data-content-path="' + esc(path) + '" rows="' + (rows || 3) + '">' + esc(text) + '</textarea></label>';
}
function manualStageField(label, key, value, rows) {
  return '<label class="full">' + esc(label) + '<textarea data-stage-field="' + esc(key) + '" rows="' + (rows || 3) + '">' + esc(value == null ? "" : value) + '</textarea></label>';
}
function manualStageEditor(item, index) {
  item = item || {};
  const val = key => esc(item[key] == null ? "" : item[key]);
  return '<article class="manual-stage-editor" data-manual-stage data-original-index="' + index + '">' +
    '<header><b>' + esc(item.stage || ("教学环节 " + (index + 1))) + '</b><button class="link danger-link" type="button" data-manual-remove-stage>移除此环节</button></header>' +
    '<div class="form-grid"><label>环节名称<input data-stage-field="stage" value="' + val("stage") + '"></label>' +
    '<label>计划时长（分钟）<input data-stage-field="minutes" type="number" min="1" max="120" value="' + esc(item.minutes == null ? 5 : item.minutes) + '"></label>' +
    manualStageField("教师活动", "teacher", item.teacher, 4) +
    manualStageField("学生活动", "students", item.students, 4) +
    manualStageField("设备安排", "device_action", item.device_action, 2) +
    manualStageField("本段观察", "look_for", item.look_for, 2) +
    manualStageField("设备不足时的替代做法", "low_device_option", item.low_device_option, 2) + '</div></article>';
}
function manualEditorMarkup(content) {
  content = content || {};
  const theory = content.theory_explanation || {};
  const mistake = content.mistake_practice || {};
  const stages = Array.isArray(content.timeline) ? content.timeline : [];
  return '<section class="manual-plan-editor" data-manual-editor>' +
    '<div class="manual-editor-intro"><span class="eyebrow">TEACHER EDIT</span><h3>手动编辑教案</h3><p>可直接修改教案正文和课堂环节。应用后先检查预览，再点击“保存教案”写入档案。</p></div>' +
    '<div class="form-grid"><label class="full">教案标题<input data-content-path="title" value="' + esc(content.title || "") + '"></label>' +
    manualEditorField("教师补充要求", "teacher_requirements", content.teacher_requirements, 2) +
    manualEditorField("教学目标（每行一项）", "objectives", content.objectives, 4) +
    manualEditorField("教学重点", "key_points", content.key_points, 3) +
    manualEditorField("教学难点", "difficulties", content.difficulties, 3) +
    manualEditorField("课前准备", "preparation", content.preparation, 3) +
    manualEditorField("乐理标题", "theory_explanation.term", theory.term, 2) +
    manualEditorField("乐理讲解", "theory_explanation.script", theory.script, 4) +
    manualEditorField("易错表现", "mistake_practice.problem", mistake.problem, 2) +
    manualEditorField("纠正练习", "mistake_practice.correction", mistake.correction, 3) +
    manualEditorField("分层教学（每行一项）", "differentiation", content.differentiation, 3) +
    manualEditorField("课堂评价", "assessment", content.assessment, 3) + '</div>' +
    '<div class="manual-timeline-head"><div><h4>课堂流程</h4><p>环节名称、时间、师生活动、设备安排和无设备替代做法都可以编辑。</p></div><button class="btn soft" type="button" data-manual-add-stage>＋ 添加环节</button></div>' +
    '<div class="manual-timeline-list" data-manual-timeline>' + stages.map((item, index) => manualStageEditor(item, index)).join("") + '</div>' +
    '<div class="manual-editor-actions"><button class="btn primary" type="button" data-manual-apply>应用修改到预览</button><button class="btn soft" type="button" data-manual-cancel>取消</button></div></section>';
}
function applyManualEditor(area) {
  const editor = area.querySelector("[data-manual-editor]");
  if (!editor || !currentPlan) return;
  const before = currentPlan;
  const original = before.content || {};
  const content = JSON.parse(JSON.stringify(original));
  editor.querySelectorAll("[data-content-path]").forEach(field => {
    const parts = field.dataset.contentPath.split(".");
    let target = content;
    let source = original;
    parts.slice(0, -1).forEach(part => {
      target[part] = target[part] || {};
      target = target[part];
      source = source && source[part];
    });
    const last = parts[parts.length - 1];
    const oldValue = source && source[last];
    const value = field.value.trim();
    target[last] = Array.isArray(oldValue) ? value.split(/\n+/).map(item => item.trim()).filter(Boolean) : value;
  });
  const timeline = Array.from(editor.querySelectorAll("[data-manual-stage]")).map(node => {
    const oldIndex = Number(node.dataset.originalIndex);
    const oldStage = Number.isInteger(oldIndex) && oldIndex >= 0 ? (original.timeline || [])[oldIndex] || {} : {};
    const value = key => {
      const field = node.querySelector('[data-stage-field="' + key + '"]');
      return field ? field.value.trim() : "";
    };
    return {
      ...oldStage,
      stage: value("stage"),
      minutes: Number(value("minutes")),
      teacher: value("teacher"),
      students: value("students"),
      device_action: value("device_action"),
      look_for: value("look_for"),
      low_device_option: value("low_device_option"),
    };
  });
  if (!String(content.title || "").trim()) return notify("教案标题不能为空", "error");
  if (!timeline.length) return notify("课堂流程至少保留一个环节", "error");
  if (timeline.some(item => !item.stage || !Number.isFinite(item.minutes) || item.minutes < 1)) {
    return notify("请填写每个环节的名称和大于 0 的分钟数", "error");
  }
  content.timeline = timeline;
  currentPlan = { ...before, content, is_saved: false };
  currentPlan.adjustment_changes = adjustmentChanges(before, currentPlan);
  manualEditing = false;
  renderPreview(area, false);
  disableActions(false);
  notify("修改已应用到预览；点击“保存教案”后才会写入档案。");
}
let manualEditing = false;

function renderPreview(area, generating = false, job = null) {
  if (!currentPlan) return;
  if (generating) manualEditing = false;
  const status = generating
    ? `<div class="ai-preview-banner"><div><b>正在完善教案</b><span>${esc(job?.stage || "切换页面后任务仍会继续")}</span></div><button class="btn soft" id="cancelGenerationInPage">取消本次生成</button></div><div class="generation-progress"><i style="width:${Math.min(100, Math.max(0, Number(job?.progress || 0)))}%"></i></div>${generationStepView(job)}`
    : "";
  const editButton = !generating && !currentPlan.is_saved && !manualEditing
    ? '<button class="btn soft" type="button" data-manual-edit-open>手动编辑教案</button>'
    : "";
  const previewBody = manualEditing
    ? manualEditorMarkup(currentPlan.content || {})
    : '<div class="lesson-preview-scroll">' + lessonView(currentPlan) + '</div>';
  const hint = currentPlan.is_saved
    ? "已保存到教案与课堂记录"
    : generating
      ? "当前显示教案初稿，完善完成后会自动更新"
      : "未保存：可手动编辑，也可填写调整要求；完成后点击右侧“保存教案”";
  area.innerHTML = status + '<section class="card lesson-preview-card"><div class="card-head"><div><h3>教案预览</h3><p class="muted">' + hint + '</p></div>' + editButton + '</div>' + previewBody + '</section>';
  area.querySelector("#cancelGenerationInPage")?.addEventListener("click", async () => {
    try { await cancelActiveGeneration(); } catch (error) { notify(error.message); }
  });
  area.querySelector("[data-manual-edit-open]")?.addEventListener("click", () => {
    manualEditing = true;
    renderPreview(area, false);
  });
  area.querySelector("[data-manual-apply]")?.addEventListener("click", () => applyManualEditor(area));
  area.querySelector("[data-manual-cancel]")?.addEventListener("click", () => {
    manualEditing = false;
    renderPreview(area, false);
  });
  area.querySelector("[data-manual-add-stage]")?.addEventListener("click", () => {
    const list = area.querySelector("[data-manual-timeline]");
    list.insertAdjacentHTML("beforeend", manualStageEditor({ stage: "新教学环节", minutes: 5 }, -1));
  });
  area.querySelector("[data-manual-timeline]")?.addEventListener("click", event => {
    const button = event.target.closest("[data-manual-remove-stage]");
    if (!button) return;
    const list = area.querySelector("[data-manual-timeline]");
    if (list.querySelectorAll("[data-manual-stage]").length <= 1) return notify("课堂流程至少保留一个环节");
    button.closest("[data-manual-stage]")?.remove();
  });
}
function generationStepView(job) {
  const steps = job?.steps || [];
  if (!steps.length) return "";
  return `<ol class="job-step-list">${steps.map(item => `<li class="${esc(item.state || "pending")}"><i>${item.state === "done" ? "✓" : item.state === "error" ? "!" : item.state === "running" ? "•" : "○"}</i>${esc(item.label)}</li>`).join("")}</ol>`;
}

async function streamPreviewAdjustment(area, instruction) {
  const metadata = { ...currentPlan };
  document.getElementById("adjustPlan").disabled = true;
  document.getElementById("savePlan").disabled = true;
  try {
    area.innerHTML = `<section class="card lesson-stream-panel"><h3>正在调整教案</h3><p class="muted">正在根据你的要求调整教案。</p><div class="loading">正在根据你的要求调整教案<i></i><i></i><i></i></div></section>`;
    await api.adjustPreviewStream({ content: currentPlan.content, instruction }, event => {
      if (event.type === "complete") {
        const nextPlan = { ...metadata, ...event.preview, is_saved: false };
        currentPlan = { ...nextPlan, adjustment_changes: adjustmentChanges(metadata, nextPlan) };
        renderPreview(area, false);
      }
    });
    disableActions(false);
    notify("已按要求更新预览；“本次调整重点”已标出实际变更内容，尚未保存。");
  } catch (error) {
    currentPlan = metadata;
    renderPreview(area, false);
    disableActions(false);
    notify(error.message);
  }
}
