import { api } from "../api/client.js";
import { lessonView } from "../components/lesson.js";
import { showModal } from "../components/modal.js";
import { esc, pageHeader } from "../utils/dom.js";

export async function renderLessons(container) {
  const plans = await api.lessons();
  container.innerHTML = pageHeader("教案与课堂记录", "仅展示教师确认保存的教案；未保存的预览不会出现在这里。", '<button class="btn primary" data-route="assistant">新建教案</button>') + `
    <section class="card table-wrap"><table><thead><tr><th>教案</th><th>班级</th><th>时长</th><th>生成方式</th><th>创建时间</th><th></th></tr></thead><tbody>${plans.length ? plans.map(plan => `<tr><td><b>${esc(plan.title)}</b><br><small>${esc(plan.song_name)}</small></td><td>${esc(plan.class_name)}</td><td>${plan.duration_minutes} 分钟</td><td><span class="status ${plan.generation_mode === "ai" ? "ok" : "info"}">${plan.generation_mode === "ai" ? "AI 接口" : "规则生成"}</span></td><td>${esc(plan.created_at)}</td><td><button class="link" data-plan="${plan.id}">查看完整教案</button></td></tr>`).join("") : '<tr><td colspan="6" class="empty">还没有教案</td></tr>'}</tbody></table></section>`;
  container.querySelectorAll("[data-plan]").forEach(button => {
    button.onclick = () => {
      const plan = plans.find(item => item.id === Number(button.dataset.plan));
      showModal(`<div class="modal-head"><div><h2>完整教案</h2><p>${esc(plan.class_name)} · ${esc(plan.created_at)}</p></div><button class="close" data-close>×</button></div>${lessonView(plan)}`);
    };
  });
}
