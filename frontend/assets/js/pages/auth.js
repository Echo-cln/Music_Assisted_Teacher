import { api } from "../api/client.js";
import { esc, notify } from "../utils/dom.js";

export function renderAuth(container, onSuccess) {
  document.body.classList.add("auth-mode");
  container.innerHTML = `<div class="auth-shell">
    <section class="auth-brand-panel">
      <span class="eyebrow">乡音智谱</span>
      <h1>让 AI 真正认识老师正在教的这个班</h1>
      <p>教师账号、班级画像、个人教案与自建资源相互隔离；系统公共乡土音乐库仍可共享使用。</p>
      <div class="auth-demo"><b>演示账号</b><span>demo / demo123456</span></div>
    </section>
    <section class="auth-card">
      <div class="tabs"><button class="tab active" data-auth-mode="login">登录</button><button class="tab" data-auth-mode="register">注册</button></div>
      <form id="loginForm" class="form-grid auth-form">
        <label class="full">用户名或邮箱<input name="account" autocomplete="username" required></label>
        <label class="full">密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="btn primary full" type="submit">登录进入工作台</button>
      </form>
      <form id="registerForm" class="form-grid auth-form hidden">
        <label>用户名<input name="username" minlength="3" pattern="[A-Za-z0-9_.-]+" autocomplete="username" required></label>
        <label>教师姓名<input name="display_name" required></label>
        <label>邮箱（用于验证码）<input name="email" type="email" autocomplete="email" required></label>
        <label>学校（可选）<input name="school"></label>
        <label>密码<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>
        <label>确认密码<input name="password_confirm" type="password" minlength="8" autocomplete="new-password" required></label>
        <label class="full">邮箱验证码<div class="input-action"><input name="verification_code" inputmode="numeric" maxlength="6" required><button type="button" class="btn" id="sendCode">发送验证码</button></div><small>真实邮件发送需由部署者配置 SMTP；手机号短信服务可在后续接入服务商。</small></label>
        <button class="btn primary full" type="submit">创建教师账号</button>
      </form>
    </section>
  </div>`;

  container.querySelectorAll("[data-auth-mode]").forEach(button => button.onclick = () => {
    container.querySelectorAll("[data-auth-mode]").forEach(item => item.classList.toggle("active", item === button));
    document.getElementById("loginForm").classList.toggle("hidden", button.dataset.authMode !== "login");
    document.getElementById("registerForm").classList.toggle("hidden", button.dataset.authMode !== "register");
  });

  document.getElementById("loginForm").onsubmit = async event => {
    event.preventDefault();
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(event.target).entries());
      const teacher = await api.login(payload);
      document.body.classList.remove("auth-mode");
      notify(`欢迎回来，${teacher.display_name}`);
      await onSuccess(teacher);
    } catch (error) {
      notify(error.message);
      button.disabled = false;
    }
  };

  document.getElementById("registerForm").onsubmit = async event => {
    event.preventDefault();
    const button = event.target.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(event.target).entries());
      const teacher = await api.register(payload);
      document.body.classList.remove("auth-mode");
      notify(`账号已创建，欢迎 ${teacher.display_name}`);
      await onSuccess(teacher);
    } catch (error) {
      notify(error.message);
      button.disabled = false;
    }
  };

  document.getElementById("sendCode").onclick = async () => {
    const form = document.getElementById("registerForm");
    const email = form.email.value.trim();
    if (!email) return notify("请先填写邮箱");
    const button = document.getElementById("sendCode");
    button.disabled = true;
    try { const result = await api.requestEmailVerification({ email }); notify(result.message); }
    catch (error) { notify(error.message); }
    finally { button.disabled = false; }
  };
}
