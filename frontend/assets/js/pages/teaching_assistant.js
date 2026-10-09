import { api } from "../api/client.js?v=20261009-teaching-assistant";
import { esc, notify, pageHeader } from "../utils/dom.js";

let conversations = [];
let activeConversation = null;
let classes = [];

function contextLabel(context = {}) {
  if (context.class_name) return context.class_name;
  const found = classes.find(item => item.id === Number(context.class_id));
  return found?.name || "";
}

export async function renderTeachingAssistant(container) {
  [classes, conversations] = await Promise.all([api.classes(), api.assistantConversations()]);
  let pending = null;
  try { pending = JSON.parse(localStorage.getItem("teachingAssistantContext") || "null"); } catch (_) {}
  localStorage.removeItem("teachingAssistantContext");
  if (pending) {
    activeConversation = await api.createAssistantConversation({ title: "新对话", context: pending });
    conversations.unshift(activeConversation);
  } else if (conversations.length) {
    activeConversation = await api.assistantConversation(conversations[0].id);
  }

  container.innerHTML = pageHeader(
    "教学助手",
    "想找一份旧教案、回看某个班的课堂情况，或聊聊下一节课怎么准备，都可以从这里开始。",
    '<button class="btn primary" id="newTeachingConversation">新建对话</button>'
  ) + `
    <section class="teaching-assistant-shell">
      <aside class="teaching-assistant-sidebar">
        <div class="assistant-sidebar-top"><b>最近对话</b><small>自动保存，可随时回来继续</small></div>
        <div id="assistantConversationList"></div>
      </aside>
      <section class="teaching-assistant-main">
        <div class="assistant-context-bar">
          <label>本次讨论的班级
            <select id="assistantClass"><option value="">不限班级 · 可查全部授权资料</option>${classes.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join("")}</select>
          </label>
          <span id="assistantContextBadge"></span>
          <button class="link" id="clearAssistantContext">清除当前来源</button>
          <button class="btn soft" id="openLessonPlanner">去教案生成</button>
        </div>
        <div class="assistant-chat-scroll" id="assistantChat" aria-live="polite"></div>
        <form class="assistant-hub-composer" id="assistantHubForm">
          <textarea id="assistantHubInput" rows="2" maxlength="4000" placeholder="可以直接提问、找历史教案或资源，也可以说说你想怎样调整课堂……"></textarea>
          <div class="assistant-composer-bottom"><small>提问和检索不会修改教案；需要生成或调整时，会带入教案助手继续处理。</small><button class="btn primary" id="assistantHubSend">发送</button></div>
        </form>
      </section>
    </section>`;

  if (activeConversation?.context?.class_id) {
    document.getElementById("assistantClass").value = String(activeConversation.context.class_id);
  }
  renderConversationList();
  bindShell();
  if (activeConversation) paintConversation();
  else showWelcome();

  function renderConversationList() {
    const list = document.getElementById("assistantConversationList");
    list.innerHTML = conversations.length ? conversations.map(item => `
      <div class="assistant-session-row ${activeConversation?.id === item.id ? "active" : ""}">
        <button class="assistant-session-open" data-session-id="${item.id}"><b>${esc(item.title)}</b><small>${esc(item.updated_at || "")}</small></button>
        <button class="assistant-session-rename" aria-label="重命名对话" data-rename-session="${item.id}">✎</button>
        <button class="assistant-session-delete" aria-label="删除对话" data-delete-session="${item.id}">×</button>
      </div>`).join("") : '<p class="assistant-empty-history">新对话会保存在这里。</p>';
    list.querySelectorAll("[data-session-id]").forEach(button => button.onclick = async () => {
      activeConversation = await api.assistantConversation(Number(button.dataset.sessionId));
      document.getElementById("assistantClass").value = activeConversation.context?.class_id || "";
      renderConversationList();
      paintConversation();
    });
    list.querySelectorAll("[data-rename-session]").forEach(button => button.onclick = async () => {
      const item = conversations.find(row => row.id === Number(button.dataset.renameSession));
      if (!item) return;
      const title = prompt("给这段对话取个名字", item.title)?.trim();
      if (!title) return;
      const updated = await api.updateAssistantConversation(item.id, { title });
      conversations = conversations.map(row => row.id === updated.id ? updated : row);
      if (activeConversation?.id === updated.id) activeConversation = { ...activeConversation, ...updated };
      renderConversationList();
    });
    list.querySelectorAll("[data-delete-session]").forEach(button => button.onclick = async () => {
      if (!confirm("删除这段对话？删除后无法恢复。")) return;
      await api.deleteAssistantConversation(Number(button.dataset.deleteSession));
      conversations = conversations.filter(item => item.id !== Number(button.dataset.deleteSession));
      if (activeConversation?.id === Number(button.dataset.deleteSession)) {
        activeConversation = null;
        showWelcome();
      }
      renderConversationList();
    });
  }

  function showWelcome() {
    document.getElementById("assistantChat").innerHTML = `
      <div class="assistant-welcome">
        <span class="assistant-welcome-mark">乡</span>
        <h2>今天想从哪件事开始？</h2>
        <p>你可以问我问题，也可以让我帮你翻找已有资料。需要改教案时，我会先把相关内容带过去，不会在这里悄悄改动。</p>
        <div class="assistant-suggestions">
          <button data-suggestion="找一下之前给四年级1班做过的音乐教案">找一份历史教案</button>
          <button data-suggestion="看看这个班最近的课堂反馈里，节奏方面反复出现什么情况">回看班级反馈</button>
          <button data-suggestion="教学资源库里有没有适合节奏练习的音乐游戏">查找教学资源</button>
        </div>
      </div>`;
    document.querySelectorAll("[data-suggestion]").forEach(button => button.onclick = () => {
      document.getElementById("assistantHubInput").value = button.dataset.suggestion;
      document.getElementById("assistantHubInput").focus();
    });
  }

  function paintConversation() {
    if (!activeConversation) return showWelcome();
    const context = activeConversation.context || {};
    document.getElementById("assistantContextBadge").textContent =
      context.source_label ? `正在参考：${context.source_label}` : (contextLabel(context) ? `班级：${contextLabel(context)}` : "");
    const chat = document.getElementById("assistantChat");
    const messages = activeConversation.messages || [];
    chat.innerHTML = messages.map(item => `
      <article class="assistant-hub-message ${item.role === "user" ? "user" : "assistant"}">
        <span class="assistant-hub-avatar">${item.role === "user" ? "我" : "助"}</span>
        <div class="assistant-hub-message-body"><div class="assistant-hub-message-content">${esc(item.content).replace(/\n/g, "<br>")}</div>
        ${item.sources?.length ? `<details class="assistant-source-list"><summary>参考了 ${item.sources.length} 条资料</summary><div>${item.sources.map(source => `
          <div class="assistant-source-card"><span>${esc(source.kind)}</span><b>${esc(source.label)}</b><p>${esc(source.detail)}</p><small>${source.updated_at ? "记录时间：" + esc(source.updated_at) : "来自项目现有资料"}</small></div>`).join("")}</div></details>` : ""}
        ${item.actions?.map(action => `<button class="btn soft assistant-action" data-assistant-action="${esc(action.type)}" data-song-name="${esc(action.song_name || "")}">${esc(action.label)}</button>`).join("") || ""}
        </div>
      </article>`).join("");
    chat.scrollTop = chat.scrollHeight;
    chat.querySelectorAll('[data-assistant-action="open_lesson_planner"]').forEach(button => button.onclick = () => {
      const messageNode = button.closest(".assistant-hub-message");
      const messageIndex = [...chat.querySelectorAll(".assistant-hub-message")].indexOf(messageNode);
      const assistantItem = messages[messageIndex];
      const lastUser = [...messages.slice(0, messageIndex)].reverse().find(item => item.role === "user")?.content || "";
      const sourceText = assistantItem?.sources?.map(item => item.kind + "：" + item.label + "。" + item.detail).join("\n") || "";
      const pickedSong = button.dataset.songName;
      localStorage.setItem("assistantLessonSeed", JSON.stringify({
        prompt: `${pickedSong ? `我想围绕《${pickedSong}》备课。` : "请先参考以下资料，并与我确认准备怎样处理，再继续。"}\n我的要求：${lastUser}\n参考资料：\n${sourceText}`,
        context: { ...context, ...(pickedSong ? { song_name: pickedSong } : {}) },
      }));
      window.dispatchEvent(new CustomEvent("app:navigate", { detail: "assistant" }));
    });
  }

  function bindShell() {
    document.getElementById("newTeachingConversation").onclick = async () => {
      activeConversation = await api.createAssistantConversation({
        context: { class_id: Number(document.getElementById("assistantClass").value) || null },
      });
      conversations.unshift(activeConversation);
      renderConversationList();
      paintConversation();
      document.getElementById("assistantHubInput").focus();
    };
    document.getElementById("assistantClass").onchange = async event => {
      if (!activeConversation) return;
      const id = Number(event.target.value) || null;
      const profile = classes.find(item => item.id === id);
      const oldContext = activeConversation.context || {};
      const classChanged = Number(oldContext.class_id || 0) !== Number(id || 0);
      const context = classChanged
        ? { class_id: id, class_name: profile?.name || null }
        : { ...oldContext, class_id: id, class_name: profile?.name || null };
      activeConversation = await api.updateAssistantConversation(activeConversation.id, { context });
      paintConversation();
    };
    document.getElementById("clearAssistantContext").onclick = async () => {
      if (!activeConversation) return notify("先新建一段对话");
      activeConversation = await api.updateAssistantConversation(activeConversation.id, { context: {} });
      document.getElementById("assistantClass").value = "";
      paintConversation();
    };
    document.getElementById("openLessonPlanner").onclick = () => {
      const context = activeConversation?.context || {};
      localStorage.setItem("assistantLessonSeed", JSON.stringify({
        prompt: "我想继续讨论一份教案。请先问清楚我是否要生成或修改，再进行操作。",
        context,
      }));
      window.dispatchEvent(new CustomEvent("app:navigate", { detail: "assistant" }));
    };
    const form = document.getElementById("assistantHubForm");
    form.onsubmit = async event => {
      event.preventDefault();
      const input = document.getElementById("assistantHubInput");
      const message = input.value.trim();
      if (!message) return;
      const send = document.getElementById("assistantHubSend");
      send.disabled = true;
      input.disabled = true;
      try {
        if (!activeConversation) {
          activeConversation = await api.createAssistantConversation({
            context: { class_id: Number(document.getElementById("assistantClass").value) || null },
          });
        }
        // Paint the user's turn immediately; the server response remains the source of truth.
        activeConversation.messages = [...(activeConversation.messages || []), { role: "user", content: message }];
        input.value = "";
        paintConversation();
        const result = await api.sendAssistantMessage(activeConversation.id, message);
        activeConversation = result.conversation;
        conversations = [activeConversation, ...conversations.filter(item => item.id !== activeConversation.id)];
        renderConversationList();
        paintConversation();
      } catch (error) {
        input.value = message;
        if (activeConversation?.id) {
          try { activeConversation = await api.assistantConversation(activeConversation.id); paintConversation(); } catch (_) {}
        }
        notify("这条消息没发出去。内容还留在输入框里，你可以检查后重试。" + (error.message ? " " + error.message : ""), "error");
      } finally {
        send.disabled = false;
        input.disabled = false;
        input.focus();
      }
    };
    document.getElementById("assistantHubInput").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  }
}

