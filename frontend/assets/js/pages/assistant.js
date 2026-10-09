import { api } from "../api/client.js?v=20261009-dialogue-reply-limit-3";
import { lessonView } from "../components/lesson.js?v=20261007-2";
import { cancelActiveGeneration, getGenerationJob, refreshGeneration, startGeneration } from "../state/generation.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

const regions = ["华南地区", "西南地区", "西北地区", "华中地区", "华东地区", "华北地区", "东北地区"];
let selectedSong = null;
let currentPlan = null;
let recommendedSongs = [];
let activeGenerationJobId = null;
let dialogueSession = {
  history: [],
  userTurns: [],
  settings: {},
  waitingFor: null,
  phase: "collecting",
  activeJobId: null,
  completedJobId: null,
};

function normalizeText(value) {
  const labels = {
    objective: "目标", evidence: "观察依据", stage: "环节", minutes: "用时",
    teacher: "教师活动", students: "学生活动", low_device_option: "无设备做法",
    device_action: "设备安排", summary: "摘要", title: "标题", status: "进展",
  };
  if (Array.isArray(value)) return value.map(normalizeText).filter(Boolean).join("；").replace(/\s+/g, " ").trim();
  if (value && typeof value === "object") return Object.entries(value)
    .filter(([, item]) => item !== null && item !== undefined && item !== "")
    .map(([key, item]) => `${labels[key] || ""}${labels[key] ? "：" : ""}${normalizeText(item)}`)
    .filter(Boolean).join("；");
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
  fields.forEach(([key, label]) => {
    const oldValue = normalizeText(from[key]) || "未填写";
    const newValue = normalizeText(to[key]) || "未填写";
    if (oldValue !== newValue) changes.push({ label, detail: `${oldValue.slice(0, 90)} → ${newValue.slice(0, 90)}` });
  });
  const beforeTimeline = from.timeline || [], afterTimeline = to.timeline || [];
  afterTimeline.forEach((stage, index) => {
    const old = beforeTimeline[index] || {};
    const changed = ["stage", "minutes", "teacher", "students", "device_action", "look_for", "low_device_option"]
      .some(key => normalizeText(old[key]) !== normalizeText(stage[key]));
    if (changed) {
      const changedFields = ["stage", "minutes", "teacher", "students", "device_action", "look_for", "low_device_option"]
        .filter(key => normalizeText(old[key]) !== normalizeText(stage[key]))
        .map(key => `${key === "minutes" ? "用时" : key === "teacher" ? "教师活动" : key === "students" ? "学生活动" : key === "look_for" ? "观察点" : key === "low_device_option" ? "无设备做法" : key === "device_action" ? "设备安排" : "环节"}：${normalizeText(old[key]) || "未填写"} → ${normalizeText(stage[key]) || "未填写"}`);
      changes.push({ label: `课堂流程 · ${stage.stage || `第 ${index + 1} 环节`}`, detail: changedFields.join("；").slice(0, 240) });
    }
  });
  return changes.slice(0, 6);
}

function classOptions(classes, includeGeneral = false) {
  const general = includeGeneral ? '<option value="">通用模式（不指定班级）</option>' : "";
  return general + classes.map(item => `<option value="${item.id}">${esc(item.name)} · ${esc(item.rhythm_level)}</option>`).join("");
}

export async function renderAssistant(container) {
  const classes = await api.classes();
  container.innerHTML = pageHeader("教案助手", "表单备课保留逐项设置；对话备课可直接描述需求、生成教案并继续修改。") + `
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
            <div class="dialogue-intro"><span class="eyebrow">对话备课</span><h3>像讨论备课一样聊这节课</h3><p>先说你的想法即可。我会结合班级画像；遇到班级、歌曲或设备等关键信息不清楚时，会直接问你。条件齐全后就开始生成，不会再让你填写确认表。</p></div>
            <div id="dialogueMessages" class="dialogue-messages" aria-live="polite">
              <div class="dialogue-message assistant"><span class="dialogue-avatar">助</span><div class="dialogue-bubble"><b>备课助手</b><p>你好。你可以直接说说准备给哪个班上什么内容、希望课堂怎么进行。如果我发现关键信息还不够，会接着问；信息齐了就开始备课。教案出来后，也可以继续告诉我哪里需要调整。</p><small>例如：给三年级1班上《茉莉花》，40分钟，孩子们最近节拍容易越唱越快。教室没有投影，只有钢琴，希望多安排学生参与的活动。</small></div></div>
            </div>
            <div class="dialogue-composer"><label class="sr-only" for="lessonBrief">描述本课需求</label><textarea id="lessonBrief" rows="2" placeholder="描述课堂需求，或直接回答我刚才的问题…（Enter 发送）"></textarea><button class="btn primary" id="extractLessonBrief" aria-label="发送备课需求">发送</button></div>
            <p class="dialogue-privacy-note">你不需要填写条件表。生成后可在下方预览教案，继续发消息修改，或保存到教学档案。</p>
          </div>
          <div id="recommendations"></div>
        </section>
        <div id="lessonArea"></div>
      </div>
      <aside class="side-stack">
        <section class="card" id="lessonActionsPanel"><h3>教案预览与保存</h3><p class="muted" id="lessonActionsHint">生成期间可查看进度。对话备课时，直接在聊天框提出修改要求。</p><label id="manualAdjustmentField">调整要求<textarea id="adjustment" placeholder="写下希望修改的部分"></textarea></label><small class="muted">请勿填写学生姓名、联系方式或其他可识别个人的信息。</small><button class="btn block" id="adjustPlan" disabled>按要求调整预览</button><button class="btn primary block" id="savePlan" disabled>保存教案</button><button class="btn block" id="printPlan" disabled>打印 / 导出 PDF</button></section>
      </aside>
    </div>`;

  bindEquipmentControls(container);
  restoreDialogueHistory();
  container.querySelectorAll("[data-planner-mode]").forEach(button => button.onclick=()=>{
    const dialog=button.dataset.plannerMode==="dialogue";
    container.querySelectorAll("[data-planner-mode]").forEach(item=>{const active=item===button;item.classList.toggle("active",active);item.setAttribute("aria-selected",String(active));});
    document.getElementById("formModePanel").classList.toggle("hidden",dialog);
    const smart=document.querySelector('[data-mode="smart"]').classList.contains("active");
    document.getElementById("smartForm").classList.toggle("hidden",!dialog&&!smart);
    document.getElementById("manualForm").classList.toggle("hidden",!dialog&&smart);
    document.getElementById("recommendations").classList.toggle("hidden",dialog);
    document.getElementById("dialogueModePanel").classList.toggle("hidden",!dialog);
    document.getElementById("manualAdjustmentField").classList.toggle("hidden",dialog);
    document.getElementById("adjustPlan").classList.toggle("hidden",dialog);
    document.getElementById("lessonActionsHint").textContent = dialog
      ? "生成后在下方查看教案；需要调整时直接在聊天框告诉我。保存按钮会保存新教案或更新已有教案。"
      : "生成期间可在右下角查看进度，也可以切换到其他页面。";
  });
  let assistantSeed = null;
  try { assistantSeed = JSON.parse(localStorage.getItem("assistantLessonSeed") || "null"); } catch (_) {}
  if (assistantSeed?.prompt) {
    localStorage.removeItem("assistantLessonSeed");
    container.querySelector('[data-planner-mode="dialogue"]')?.click();
    document.getElementById("lessonBrief").value = assistantSeed.prompt;
  }
  document.getElementById("extractLessonBrief").onclick=()=>sendDialogueMessage(classes);
  document.getElementById("lessonBrief").addEventListener("keydown", event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();sendDialogueMessage(classes);}});
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
    if (!currentPlan || (currentPlan.is_saved && !currentPlan._dirty)) return;
    const button = document.getElementById("savePlan");
    button.disabled = true;
    const editingSaved = Boolean(currentPlan.id);
    button.textContent = editingSaved ? "正在保存修改…" : "正在保存…";
    try {
      const payload = {
        song_id: currentPlan.song_id,
        class_id: currentPlan.class_id,
        duration_minutes: currentPlan.duration_minutes,
        teacher_requirements: currentPlan.content.teacher_requirements || "",
        generation_mode: currentPlan.generation_mode,
        content: currentPlan.content,
      };
      currentPlan = editingSaved
        ? await api.updateLesson(currentPlan.id, payload)
        : await api.saveLesson(payload);
      delete currentPlan._dirty;
      renderPreview(document.getElementById("lessonArea"), false);
      button.textContent = "已保存到教案与课堂记录";
      document.getElementById("adjustPlan").disabled = true;
      if (dialogueSession.phase === "ready") rememberAssistantMessage("教案已保存到教学档案。之后还可以继续告诉我修改意见；保存修改时会更新这条教案记录。");
      notify(editingSaved ? "教案修改已保存" : "教案已保存，现在可在“教学档案”中查看");
    } catch (error) {
      button.disabled = false;
      button.textContent = editingSaved ? "保存修改" : "保存教案";
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

function restoreDialogueHistory() {
  const transcript = document.getElementById("dialogueMessages");
  if (!transcript || !dialogueSession.history.length) return;
  transcript.firstElementChild?.remove();
  dialogueSession.history.forEach(item => appendDialogueMessage(item.role, item.text));
}

function rememberAssistantMessage(text) {
  if (!text) return;
  dialogueSession.history.push({ role: "assistant", text });
  appendDialogueMessage("assistant", text);
}

function rememberAssistantAction(text, buttonLabel, command) {
  dialogueSession.history.push({ role: "assistant", text });
  const node = appendDialogueMessage("assistant", `${esc(text)}<div class="dialogue-actions"><button class="btn primary" type="button" data-dialogue-command="${esc(command)}">${esc(buttonLabel)}</button></div>`, { html: true });
  node?.querySelector("[data-dialogue-command]")?.addEventListener("click", () => {
    const input = document.getElementById("lessonBrief");
    input.value = command;
    document.getElementById("extractLessonBrief")?.click();
  });
}

function normalizedClassName(value) {
  const digits = { "一":"1", "二":"2", "三":"3", "四":"4", "五":"5", "六":"6" };
  return String(value || "").replace(/\s/g, "").replace(/[一二三四五六]/g, digit => digits[digit]).toLowerCase();
}

function resolveClassFromText(text, classes) {
  const value = normalizedClassName(text);
  return classes.find(item => value.includes(normalizedClassName(item.name)));
}

function isDialogueQuestion(message) {
  const text = String(message || "").trim();
  if (/(?:先不生成|先不改|不改了|取消生成|先不要生成)/.test(text)) return false;
  if (/(?:先别改|先不改教案|不要修改|只是问|只问|先解释|仅解释)/.test(text)
      && /(?:教案|生成|调整|修改|为什么|原因|安排)/.test(text)) return true;
  const changeVerb = "(?:调整|修改|改成|改为|改|换成|换为|换|增加|减少|删掉|删除|补充|安排|重写|缩短|延长|加入|替换)";
  const explicitObjectChange = new RegExp(`(?:把|将).{0,45}${changeVerb}`).test(text)
    || new RegExp(`^${changeVerb}`).test(text);
  if (explicitObjectChange) return false;

  const asksHow = /(?:告诉我|解释|说明|为什么|怎么|如何).{0,24}(?:调整|修改|改|换|增加|减少|添加|删除|删|补充|生成|保存|使用|区别|模式)/.test(text);
  if (asksHow) return true;

  const directRequest = new RegExp(`(?:帮我|请|希望|需要|想要|能不能|可以|可否|能否).{0,45}${changeVerb}`).test(text);
  if (directRequest) return false;
  return /[?？]|(?:什么|哪些|哪种|为什么|怎么|如何|区别|是否|有没有|能不能|可以吗|是什么|多少|还有什么)/.test(text);
}

function extractSongTitleFromTurn(message, waitingForSong = false) {
  const text = String(message || "").trim();
  const explicit = text.match(/(?:歌曲(?:名(?:字|称)?)?|歌名(?:字|称)?|曲目(?:名(?:字|称)?)?)\s*(?:就是|是|叫|为|：|:)\s*[《「“]?\s*([^》」”\s，,。！？!?；;]+)/);
  const bracketed = text.match(/《([^》]+)》/)?.[1];
  const raw = explicit?.[1] || bracketed || (waitingForSong
    ? text.replace(/^(?:不是[，,。\s]*)?(?:我的意思是|我是说|我想用|歌曲(?:是|叫)?|那就用|换成|改成|用|选)\s*/, "")
    : "");
  return String(raw || "").replace(/[《》「」“”]/g, "").replace(/[，,。！？!?；;]+$/, "").trim();
}

async function answerDialogueQuestion(prompt) {
  if (Array.from(String(prompt || "")).length > 1100) {
    throw new Error("这条消息比较长，请拆成两条发送；历史对话会自动压缩后再提交。你刚才的原文仍保留在输入记录中。");
  }
  const currentContent = currentPlan?.content || {};
  const response = await api.lessonDialogueReply({
    message: String(prompt || ""),
    history: dialogueSession.history.slice(0, -1).slice(-8).map(item => ({ role: item.role, content: Array.from(String(item.text || "")).slice(0, 1000).join("") })),
    context: {
      phase: dialogueSession.phase,
      waiting_for: dialogueSession.waitingFor,
      settings: {
        class_name: dialogueSession.settings.class_name || null,
        song_name: dialogueSession.settings.song_name || null,
        duration_minutes: dialogueSession.settings.duration_minutes || null,
        equipment_constraints: dialogueSession.settings.equipment_constraints || [],
        generation_strategy: dialogueSession.settings.generation_strategy || "fast",
      },
      plan: currentPlan ? {
        title: currentPlan.title || currentContent.title || "",
        song_name: currentPlan.song_name || "",
        class_name: currentPlan.class_name || "",
        duration_minutes: currentPlan.duration_minutes || null,
        generation_mode: currentPlan.generation_mode || "",
        objectives: currentContent.objectives || [],
        timeline: (currentContent.timeline || []).slice(0, 8).map(item => ({
          stage: item.stage, minutes: item.minutes,
        })),
      } : null,
    },
  });
  return String(response.reply || "").trim();
}

async function sendDialogueMessage(classes) {
  const input = document.getElementById("lessonBrief");
  const prompt = input.value.trim();
  if (!prompt) return;
  if (dialogueSession.phase === "generating" || dialogueSession.phase === "adjusting") {
    rememberAssistantMessage(dialogueSession.phase === "generating"
      ? "教案还在生成，等预览出来后再发修改意见，我会接着调整。"
      : "我正在更新预览，稍等片刻就可以继续讨论。");
    return;
  }

  const waitingFor = dialogueSession.waitingFor;
  dialogueSession.history.push({ role: "user", text: prompt });
  dialogueSession.userTurns.push(prompt);
  appendDialogueMessage("user", prompt);
  input.value = "";
  const sendButton = document.getElementById("extractLessonBrief");
  sendButton.disabled = true;
  const pending = appendDialogueMessage("assistant", "我来看看还需要确认什么…", { pending: true });

  try {
    if (isDialogueQuestion(prompt)) {
      pending && (pending.querySelector(".dialogue-bubble p").textContent = "我先回答你的问题，不会把提问当作教案修改。");
      const answer = await answerDialogueQuestion(prompt);
      pending?.remove();
      rememberAssistantMessage(answer || "我没能整理出可靠的回答。你可以换个说法，或告诉我你希望修改教案的哪一部分。");
      return;
    }

    if (dialogueSession.waitingFor === "generation_confirmation") {
      if (/(?:确认|按这些条件|就这样|开始生成|生成教案|请生成|直接生成)/.test(prompt)) {
        const payload = dialogueSession.pendingGenerationPayload;
        if (!payload) throw new Error("待确认的备课条件已失效，请重新确认班级和歌曲");
        dialogueSession.waitingFor = null;
        dialogueSession.phase = "collecting";
        pending && (pending.querySelector(".dialogue-bubble p").textContent = "好，我按刚才确认的条件开始生成。");
        pending?.remove();
        const started = await generate(false, payload);
        if (!started) dialogueSession.phase = "collecting";
        return;
      }
      if (/(?:取消|先不生成|先不要生成|暂不生成|再想想|先等等)/.test(prompt)) {
        dialogueSession.waitingFor = null;
        dialogueSession.pendingGenerationPayload = null;
        dialogueSession.phase = "collecting";
        pending?.remove();
        rememberAssistantMessage("好，我们先不生成。你可以继续补充或改动条件，准备好时再告诉我。");
        return;
      }
      // A new detail replaces the pending proposal; it never silently confirms it.
      dialogueSession.waitingFor = null;
      dialogueSession.phase = "collecting";
    }

    if (dialogueSession.waitingFor === "adjustment_confirmation" && currentPlan) {
      if (/(?:确认|按这个改|按此修改|就这样|开始调整|可以修改)/.test(prompt)) {
        const instruction = dialogueSession.pendingAdjustmentPrompt;
        dialogueSession.waitingFor = null;
        dialogueSession.phase = "adjusting";
        pending && (pending.querySelector(".dialogue-bubble p").textContent = "好，我按刚才说的方向更新预览。");
        const before = currentPlan;
        const ok = await streamPreviewAdjustment(document.getElementById("lessonArea"), instruction);
        pending?.remove();
        dialogueSession.phase = "ready";
        const changed = currentPlan?.adjustment_changes || [];
        rememberAssistantMessage(ok
          ? (changed.length ? `这次主要改了：${changed.slice(0, 5).map(item => `${item.label}：${item.detail}`).join("；")}。其他未提及部分先保留，完整预览已更新，确认后再保存。` : "预览已更新。系统没有检测到明确的字段差异，请核对正文后再保存。")
          : "这次没有完成调整，原教案仍保留。你可以换个说法，或先在预览里手动编辑。");
        return;
      }
      if (/(?:取消|先不改|不改了|算了)/.test(prompt)) {
        dialogueSession.waitingFor = null;
        dialogueSession.pendingAdjustmentPrompt = null;
        pending?.remove();
        rememberAssistantMessage("好，先保留当前教案，不做修改。你还可以继续问我问题。");
        return;
      }
      dialogueSession.pendingAdjustmentPrompt = prompt;
      pending?.remove();
      rememberAssistantAction(`收到，你的新要求是“${prompt}”。我会按这条最新要求重新整理修改方案，之前那条待确认方案不再执行。`, "确认并更新预览", "确认按最新修改方案调整");
      return;
    }

    if (dialogueSession.phase === "ready" && currentPlan) {
      dialogueSession.pendingAdjustmentPrompt = prompt;
      dialogueSession.waitingFor = "adjustment_confirmation";
      pending?.remove();
      rememberAssistantAction(`我理解你想这样调整：${prompt}。我会保留没有提到的内容。先确认一下，按这个方向更新预览吗？`, "按这个方向修改", "确认按这个方案修改");
      return;
    }

    const directSong = extractSongTitleFromTurn(prompt, waitingFor === "song");
    const directSongCorrection = Boolean(directSong && (waitingFor === "song" || waitingFor === "song_resource"));
    const contextPrompt = "教师本轮消息（只提取本轮明确补充；如果是在纠正上一轮，以本轮说法为准）：" + prompt;
    const response = directSongCorrection
      ? { parsed: {} }
      : await api.extractLessonBrief({
          prompt: contextPrompt.length >= 8 ? contextPrompt : `教师补充说明：${contextPrompt}`,
          class_id: dialogueSession.settings.class_id || null,
        });
    pending?.remove();
    const parsed = response.parsed || {};
    const settings = dialogueSession.settings;
    if (/深度(?:模式|思考)?|用深度|切到深度/.test(prompt)) settings.generation_strategy = "deep";
    if (/快速(?:模式)?|用快速|切到快速/.test(prompt)) settings.generation_strategy = "fast";
    const normalized = value => String(value || "").replace(/[《》\s]/g, "").toLowerCase();
    const explicitGeneral = /通用模式|不指定班级|不绑定班级|没有对应班级/.test(prompt);

    if (explicitGeneral || (waitingFor === "class" && /通用|不指定|不绑定/.test(prompt))) {
      settings.general_class = true;
      settings.class_id = null;
      settings.class_name = "通用模式";
      settings.unresolved_class = "";
    } else {
      const className = parsed.class_name && !/^(null|无|未指定)$/i.test(String(parsed.class_name))
        ? String(parsed.class_name) : "";
      const matchedClass = (waitingFor === "class" ? resolveClassFromText(prompt, classes) : null)
        || (className && classes.find(item => normalizedClassName(item.name) === normalizedClassName(className)))
        || resolveClassFromText(prompt, classes);
      if (matchedClass) {
        settings.class_id = matchedClass.id;
        settings.class_name = matchedClass.name;
        settings.general_class = false;
        settings.unresolved_class = "";
      } else if (className) {
        settings.class_id = null;
        settings.class_name = "";
        settings.general_class = false;
        settings.unresolved_class = className;
      }
    }

    const parsedSong = parsed.song_name && !/^(null|无|未指定|尚未指定)$/i.test(String(parsed.song_name))
      ? String(parsed.song_name).trim() : "";
    const confirmsResourceAdded = waitingFor === "song_resource" && /(?:已|已经|刚刚|刚才)?(?:添加|加入|录入|补充)(?:好了|完成|成功)?|我加好了/.test(prompt);
    const asksToChangeSong = waitingFor === "song_resource" && /(?:换一首|换歌|换个歌曲|不加了)/.test(prompt) && !directSong;
    if (asksToChangeSong) {
      settings.song_name = "";
      dialogueSession.waitingFor = "song";
      rememberAssistantMessage("好，那我们换一首。你想用哪首歌？可以直接说歌名，我会核对资源库。");
      return;
    }
    const explicitSongChange = /(?:换成|改成|改为|换为|歌曲换|歌名改|换一首)/.test(prompt);
    if (directSong && (waitingFor === "song" || waitingFor === "song_resource" || !settings.song_name || explicitSongChange)) settings.song_name = directSong;
    else if (!confirmsResourceAdded && parsedSong && (waitingFor === "song" || !settings.song_name)) settings.song_name = parsedSong;

    const parsedDuration = Number(parsed.duration_minutes);
    if (Number.isFinite(parsedDuration) && parsedDuration >= 20 && parsedDuration <= 90) settings.duration_minutes = parsedDuration;
    if (parsed.activity_preference) settings.activity_preference = String(parsed.activity_preference).trim();
    if (parsed.region_element) settings.region_element = String(parsed.region_element).trim();
    if (parsed.teacher_requirements) settings.teacher_requirements = String(parsed.teacher_requirements).trim();
    if (waitingFor === "equipment") {
      settings.equipment_constraints = Array.isArray(parsed.equipment_constraints) && parsed.equipment_constraints.length
        ? parsed.equipment_constraints.map(value => String(value).trim()).filter(Boolean)
        : [prompt];
      settings.equipment_known = true;
    } else if (Array.isArray(parsed.equipment_constraints) && parsed.equipment_constraints.length) {
      settings.equipment_constraints = parsed.equipment_constraints.map(value => String(value).trim()).filter(Boolean);
      settings.equipment_known = true;
    } else if (/设备|投影|音箱|钢琴|乐器|普通教室|无电子/.test(prompt)) {
      settings.equipment_constraints = [prompt];
      settings.equipment_known = true;
    }

    if (!settings.class_id && !settings.general_class) {
      dialogueSession.waitingFor = "class";
      const reply = settings.unresolved_class
        ? `我没在班级画像里找到“${settings.unresolved_class}”。目前可选：${classes.map(item => item.name).join("、")}。你想用哪个班？也可以说“通用模式”。`
        : "这节课准备给哪个班上？我会结合该班画像安排内容；如果不需要绑定具体班级，也可以说“通用模式”。";
      rememberAssistantMessage(reply);
      return;
    }
    if (!settings.song_name) {
      dialogueSession.waitingFor = "song";
      rememberAssistantMessage("这节课准备教哪首歌？我会先到教学资源库核对，找到后就继续备课。");
      return;
    }
    if (!settings.equipment_known) {
      dialogueSession.waitingFor = "equipment";
      rememberAssistantMessage("这个班的教室目前能用哪些设备？比如钢琴、音箱或投影；如果都没有，告诉我“无电子设备”。");
      return;
    }

    const songs = await api.songs({ q: settings.song_name });
    const exactSong = songs.find(item => normalized(item.name) === normalized(settings.song_name));
    if (!exactSong) {
      dialogueSession.waitingFor = "song_resource";
      const missingTitle = settings.song_name;
      const nearby = songs.slice(0, 4).map(item => `《${item.name}》`).join("、");
      rememberAssistantMessage(nearby
        ? `明白了，歌名是《${missingTitle}》。资源库暂时没有这首歌；可以直接换成已有曲目（例如${nearby}），或先去教学资源库添加后告诉我“已添加”。`
        : `明白了，歌名是《${missingTitle}》。资源库暂时没有这首歌。你可以先去教学资源库添加，完成后告诉我“已添加”；也可以直接告诉我换成哪首已收录的歌曲。`);
      return;
    }
    selectedSong = exactSong;
    const profile = settings.class_id ? classes.find(item => item.id === settings.class_id) : null;
    const generationStrategy = settings.generation_strategy || "fast";
    const activity = settings.activity_preference || profile?.preferred_method || "互动与分组合作";
    const requirements = [
      settings.teacher_requirements,
      settings.region_element ? `地区 / 文化元素：${settings.region_element}` : "",
      `课堂可用设备与限制：${settings.equipment_constraints.join("、")}`,
    ].filter(Boolean).join("\n");
    const payload = {
      song_id: exactSong.id,
      class_id: settings.class_id || null,
      duration_minutes: settings.duration_minutes || 40,
      activity_preference: activity,
      teacher_requirements: requirements,
      generation_strategy: generationStrategy,
    };
    dialogueSession.pendingGenerationPayload = payload;
    dialogueSession.waitingFor = "generation_confirmation";
    dialogueSession.phase = "awaiting_generation_confirmation";
    rememberAssistantAction(
      `我已经核对好备课条件：${settings.class_name || "通用模式"}、《${exactSong.name}》、${payload.duration_minutes}分钟；设备按“${settings.equipment_constraints.join("、") || "无电子设备"}”安排，采用${generationStrategy === "fast" ? "快速" : "深度"}模式。你还可以继续补充或调整；确认后我再生成教案。`,
      "确认并生成教案",
      "确认按当前条件生成教案",
    );
  } catch (error) {
    pending?.remove();
    if (waitingFor) dialogueSession.waitingFor = waitingFor;
    rememberAssistantMessage(`这一步没有完成：${error.message || "暂时无法处理"}。刚才的消息已保留，你可以补充或换种说法。`);
    console.error("对话备课处理失败", error);
  } finally {
    pending?.remove();
    sendButton.disabled = false;
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
    if (!document.getElementById("dialogueModePanel").classList.contains("hidden")) {
      dialogueSession.phase = "generating";
      dialogueSession.activeJobId = activeGenerationJobId;
    }
    const strategy = payload.generation_strategy || strategyElement.value;
    notify(strategy === "fast" ? "正在快速生成完整教案" : "正在生成完整教案（深度模式）");
    return true;
  } catch (error) {
    disableActions(false);
    document.getElementById("lessonArea").innerHTML = `<div class="notice">${esc(error.message)}</div>`;
    return false;
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
    if (dialogueSession.activeJobId && dialogueSession.activeJobId === job.id) {
      dialogueSession.phase = "ready";
      if (dialogueSession.completedJobId !== job.id) {
        dialogueSession.completedJobId = job.id;
        rememberAssistantMessage("教案已生成，完整预览在下方。你可以继续告诉我具体要怎么调整，也可以在右侧保存到教学档案。");
      }
    }
    renderPreview(area, false, job);
    if(previousResult){
      area.insertAdjacentHTML("afterbegin",`<div class="notice previous-plan-notice"><b>上次生成结果</b><span>对应：${esc(currentPlan.class_name||"通用模式")} · ${Number(currentPlan.duration_minutes)||"—"} 分钟。本条不是当前设置下的新结果；请核对班级和课时后再决定是否保存。</span></div>`);
      disableActions(true);
      document.getElementById("printPlan").disabled=false;
    }else disableActions(false);
    return;
  }
  if (job.status === "failed") {
    if (dialogueSession.activeJobId === job.id) dialogueSession.phase = "collecting";
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
  save.textContent = currentPlan?.is_saved && !currentPlan?._dirty
    ? "已保存到教案与课堂记录"
    : currentPlan?.id
      ? generating ? "生成完成后可保存修改" : "保存修改"
      : generating ? "完善完成后可保存" : "保存教案";
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
      : currentPlan.id
        ? "这份已保存的教案有未保存修改；确认预览后点击右侧“保存修改”"
        : "尚未保存：可预览并继续调整，确认后点击右侧“保存教案”";
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
        const nextPlan = { ...metadata, ...event.preview, is_saved: false, _dirty: Boolean(metadata.id) };
        currentPlan = { ...nextPlan, adjustment_changes: adjustmentChanges(metadata, nextPlan) };
        renderPreview(area, false);
      }
    });
    disableActions(false);
    notify("已按要求更新预览；“本次调整重点”已标出实际变更内容，尚未保存。");
    return true;
  } catch (error) {
    currentPlan = metadata;
    renderPreview(area, false);
    disableActions(false);
    notify(error.message);
    return false;
  }
}
