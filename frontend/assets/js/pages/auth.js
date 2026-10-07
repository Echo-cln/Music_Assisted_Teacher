import { api } from "../api/client.js";
import { notify } from "../utils/dom.js";

function showFormError(form, message = "") {
  const box = form.querySelector(".auth-message");
  if (!box) return;
  box.textContent = message;
  box.classList.toggle("hidden", !message);
}

function setBusy(button, busy) {
  if (!button.dataset.idleLabel) button.dataset.idleLabel = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? button.dataset.busyLabel : button.dataset.idleLabel;
}

export function renderAuth(container, onSuccess) {
  document.body.classList.add("auth-mode");
  container.innerHTML = [
    '<div class="auth-shell">',
      '<section class="auth-brand-panel" aria-label="乡音智谱介绍">',
        '<div class="auth-brand-lockup"><span class="auth-brand-symbol">乡</span><span><b>乡音智谱</b><small>乡村音乐课堂工作台</small></span></div>',
        '<div class="auth-brand-copy">',
          '<span class="auth-eyebrow">备课 · 记录 · 创作</span>',
          '<h1>让每一堂音乐课<br><em>都有自己的旋律</em></h1>',
          '<p>从班级画像、歌曲备课，到课堂记录与数字编曲，让教学工作在一处接续完成。</p>',
        '</div>',
        '<div class="auth-score-art" aria-hidden="true">',
          '<div class="auth-score-art-head"><span>乡音智谱 <i>·</i> 音乐课堂</span><span>课堂灵感</span></div>',
          '<svg viewBox="0 0 620 170" role="presentation" focusable="false">',
            '<g class="auth-staff"><path d="M8 36H612"/><path d="M8 61H612"/><path d="M8 86H612"/><path d="M8 111H612"/><path d="M8 136H612"/></g>',
            '<path class="auth-melody" d="M27 110 C78 108 75 46 129 48 S188 122 239 99 S310 44 361 69 S425 134 474 105 S538 54 590 66"/>',
            '<g class="auth-notes"><ellipse cx="80" cy="92" rx="8" ry="5" transform="rotate(-18 80 92)"/><path d="M87 91V45"/><ellipse cx="177" cy="78" rx="8" ry="5" transform="rotate(-18 177 78)"/><path d="M184 77V31"/><ellipse cx="272" cy="88" rx="8" ry="5" transform="rotate(-18 272 88)"/><path d="M279 87V42"/><ellipse cx="367" cy="73" rx="8" ry="5" transform="rotate(-18 367 73)"/><path d="M374 72V27"/><ellipse cx="463" cy="100" rx="8" ry="5" transform="rotate(-18 463 100)"/><path d="M470 99V54"/><ellipse cx="553" cy="65" rx="8" ry="5" transform="rotate(-18 553 65)"/><path d="M560 64V19"/></g>',
            '<circle class="auth-note-dot" cx="129" cy="48" r="4"/><circle class="auth-note-dot" cx="239" cy="99" r="4"/><circle class="auth-note-dot" cx="361" cy="69" r="4"/><circle class="auth-note-dot" cx="474" cy="105" r="4"/>',
          '</svg>',
          '<div class="auth-score-art-foot"><b>把课堂观察，留给下一次备课</b><span>班级 · 教案 · 音频 · 编曲</span></div>',
        '</div>',
      '</section>',
      '<section class="auth-card" aria-label="教师账号">',
        '<div class="auth-card-heading"><span class="auth-card-mark">♫</span><div><b id="authHeadingTitle">欢迎回来</b><small id="authHeadingSubtitle">登录后继续使用工作台</small></div></div>',
        '<div class="tabs auth-tabs" role="tablist" aria-label="账号操作">',
          '<button class="tab active" type="button" data-auth-mode="login" role="tab" aria-selected="true">登录</button>',
          '<button class="tab" type="button" data-auth-mode="register" role="tab" aria-selected="false">注册</button>',
        '</div>',
        '<form id="loginForm" class="form-grid auth-form">',
          '<label class="full">用户名或邮箱<input name="account" autocomplete="username" placeholder="输入用户名或邮箱" required></label>',
          '<label class="full">密码<input name="password" type="password" autocomplete="current-password" placeholder="输入密码" required></label>',
          '<div class="auth-message full hidden" role="alert" aria-live="polite"></div>',
          '<button class="btn primary full auth-submit" type="submit" data-busy-label="正在登录…">登录工作台</button>',
        '</form>',
        '<form id="registerForm" class="form-grid auth-form hidden">',
          '<label>用户名<input name="username" minlength="3" pattern="[A-Za-z0-9_.-]+" autocomplete="username" placeholder="至少 3 位" required></label>',
          '<label>教师姓名<input name="display_name" autocomplete="name" placeholder="填写姓名" required></label>',
          '<label>邮箱<input name="email" type="email" autocomplete="email" placeholder="用于接收验证码" required></label>',
          '<label>学校（选填）<input name="school" autocomplete="organization" placeholder="填写学校名称"></label>',
          '<label>密码<input name="password" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" required></label>',
          '<label>确认密码<input name="password_confirm" type="password" minlength="8" autocomplete="new-password" placeholder="再次输入密码" required></label>',
          '<label class="full">邮箱验证码<div class="input-action"><input name="verification_code" inputmode="numeric" maxlength="6" placeholder="6 位验证码" required><button type="button" class="btn" id="sendCode" data-busy-label="发送中…">发送验证码</button></div><small>验证码有效期为 10 分钟。</small></label>',
          '<div class="auth-message full hidden" role="alert" aria-live="polite"></div>',
          '<button class="btn primary full auth-submit" type="submit" data-busy-label="正在创建账号…">创建账号</button>',
        '</form>',
        '<div class="auth-card-foot"><span></span><small>账号信息仅用于本工作台登录与数据归属。</small></div>',
      '</section>',
    '</div>'
  ].join("");

  container.querySelectorAll("[data-auth-mode]").forEach(button => button.onclick = () => {
    const registering = button.dataset.authMode === "register";
    container.querySelectorAll("[data-auth-mode]").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    document.getElementById("loginForm").classList.toggle("hidden", registering);
    document.getElementById("registerForm").classList.toggle("hidden", !registering);
    document.getElementById("authHeadingTitle").textContent = registering ? "创建教师账号" : "欢迎回来";
    document.getElementById("authHeadingSubtitle").textContent = registering ? "填写资料并验证邮箱" : "登录后继续使用工作台";
    container.querySelectorAll(".auth-message").forEach(box => {
      box.textContent = "";
      box.classList.add("hidden");
    });
  });

  document.getElementById("loginForm").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    showFormError(form);
    setBusy(button, true);
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const teacher = await api.login(payload);
      document.body.classList.remove("auth-mode");
      notify("欢迎回来，" + teacher.display_name);
      await onSuccess(teacher);
    } catch (error) {
      showFormError(form, error.message || "登录失败，请检查账号信息与服务连接。");
    } finally {
      setBusy(button, false);
    }
  };

  document.getElementById("registerForm").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    showFormError(form);
    setBusy(button, true);
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const teacher = await api.register(payload);
      document.body.classList.remove("auth-mode");
      notify("账号已创建，欢迎 " + teacher.display_name);
      await onSuccess(teacher);
    } catch (error) {
      showFormError(form, error.message || "注册失败，请检查填写内容与服务连接。");
    } finally {
      setBusy(button, false);
    }
  };

  document.getElementById("sendCode").onclick = async () => {
    const form = document.getElementById("registerForm");
    const email = form.email.value.trim();
    showFormError(form);
    if (!email) return showFormError(form, "请先填写邮箱。");
    const button = document.getElementById("sendCode");
    setBusy(button, true);
    try {
      const result = await api.requestEmailVerification({ email });
      showFormError(form, result.message || "验证码已发送。");
    } catch (error) {
      showFormError(form, error.message || "验证码发送失败。");
    } finally {
      setBusy(button, false);
    }
  };
}
