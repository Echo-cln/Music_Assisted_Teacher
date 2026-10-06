import { api } from "../api/client.js";
import { notify } from "../utils/dom.js";

function showFormError(form, message = "") {
  const box = form.querySelector(".auth-message");
  if (!box) return;
  box.textContent = message;
  box.classList.toggle("hidden", !message);
}

function setBusy(button, busy, label) {
  if (!button.dataset.idleLabel) button.dataset.idleLabel = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.idleLabel;
}

export function renderAuth(container, onSuccess) {
  document.body.classList.add("auth-mode");
  container.innerHTML = `<div class="auth-shell">
    <section class="auth-brand-panel">
      <span class="eyebrow">乡音智谱 · 乡村音乐教室</span>
      <h1>让备课、听课与创作<br>更顺手</h1>
      <p>为音乐课堂准备教案、整理记录，也可以在数字工作台里练习和编曲。</p>
      <ul class="auth-features">
        <li>教案与课堂档案</li>
        <li>课堂音频分析</li>
        <li>数字乐器与编曲</li>
      </ul>
    </section>
    <section class="auth-card" aria-label="教师账号">
      <div class="auth-card-heading">
        <span class="brand-mark">乡</span>
        <div><b>教师工作台</b><small>登录或创建教师账号</small></div>
      </div>
      <div class="tabs auth-tabs" role="tablist" aria-label="账号操作">
        <button class="tab active" type="button" data-auth-mode="login" role="tab" aria-selected="true">登录</button>
        <button class="tab" type="button" data-auth-mode="register" role="tab" aria-selected="false">注册</button>
      </div>
      <form id="loginForm" class="form-grid auth-form">
        <label class="full">用户名或邮箱<input name="account" autocomplete="username" required></label>
        <label class="full">密码<input name="password" type="password" autocomplete="current-password" required></label>
        <div class="auth-message full hidden" role="alert" aria-live="polite"></div>
        <button class="btn primary full auth-submit" type="submit">登录进入工作台</button>
      </form>
      <form id="registerForm" class="form-grid auth-form hidden">
        <label>用户名<input name="username" minlength="3" pattern="[A-Za-z0-9_.-]+" autocomplete="username" required></label>
        <label>教师姓名<input name="display_name" autocomplete="name" required></label>
        <label>邮箱<input name="email" type="email" autocomplete="email" required></label>
        <label>学校（可选）<input name="school" autocomplete="organization"></label>
        <label>密码<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>
        <label>确认密码<input name="password_confirm" type="password" minlength="8" autocomplete="new-password" required></label>
        <label class="full">邮箱验证码<div class="input-action"><input name="verification_code" inputmode="numeric" maxlength="6" required><button type="button" class="btn" id="sendCode">发送验证码</button></div><small>验证码发送到填写的邮箱，有效期 10 分钟。</small></label>
        <div class="auth-message full hidden" role="alert" aria-live="polite"></div>
        <button class="btn primary full auth-submit" type="submit">创建教师账号</button>
      </form>
    </section>
  </div>`;

  container.querySelectorAll("[data-auth-mode]").forEach(button => button.onclick = () => {
    const registering = button.dataset.authMode === "register";
    container.querySelectorAll("[data-auth-mode]").forEach(item => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    document.getElementById("loginForm").classList.toggle("hidden", registering);
    document.getElementById("registerForm").classList.toggle("hidden", !registering);
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
    setBusy(button, true, "正在登录…");
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const teacher = await api.login(payload);
      document.body.classList.remove("auth-mode");
      notify(`欢迎回来，${teacher.display_name}`);
      await onSuccess(teacher);
    } catch (error) {
      showFormError(form, error.message || "登录失败，请检查账号信息与后端连接。");
    } finally {
      setBusy(button, false);
    }
  };

  document.getElementById("registerForm").onsubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    showFormError(form);
    setBusy(button, true, "正在创建账号…");
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const teacher = await api.register(payload);
      document.body.classList.remove("auth-mode");
      notify(`账号已创建，欢迎 ${teacher.display_name}`);
      await onSuccess(teacher);
    } catch (error) {
      showFormError(form, error.message || "注册失败，请检查填写内容与后端连接。");
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
    setBusy(button, true, "发送中…");
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
