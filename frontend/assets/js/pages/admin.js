import { api } from "../api/client.js";
import { esc, notify, pageHeader } from "../utils/dom.js";

export async function renderAdmin(container) {
  const rows = await api.adminUsers();
  container.innerHTML = pageHeader("系统管理", "管理所有注册账号、权限与验证状态。邮箱验证只是联系方式验证；法定实名核验仍需接入合规的第三方服务。") + `<section class="card table-wrap"><table><thead><tr><th>账号</th><th>邮箱</th><th>学校</th><th>角色</th><th>认证状态</th><th>注册时间</th><th>操作</th></tr></thead><tbody>${rows.map(user => `<tr><td><b>${esc(user.display_name)}</b><br><small>@${esc(user.username)}</small></td><td>${esc(user.email || "—")}</td><td>${esc(user.school || "—")}</td><td><select data-role="${user.id}"><option value="teacher" ${user.role === "teacher" ? "selected" : ""}>教师</option><option value="admin" ${user.role === "admin" ? "selected" : ""}>管理员</option></select></td><td><select data-status="${user.id}">${["unverified","email_verified","verified","suspended"].map(item => `<option value="${item}" ${item === user.verification_status ? "selected" : ""}>${item}</option>`).join("")}</select></td><td>${esc(user.created_at)}</td><td><button class="link" data-save="${user.id}">保存</button></td></tr>`).join("")}</tbody></table></section>`;
  container.querySelectorAll("[data-save]").forEach(button => button.onclick = async () => {
    const id = button.dataset.save;
    await api.updateAdminUser(id, { role: container.querySelector(`[data-role="${id}"]`).value, verification_status: container.querySelector(`[data-status="${id}"]`).value });
    notify("用户权限已更新");
  });
}
