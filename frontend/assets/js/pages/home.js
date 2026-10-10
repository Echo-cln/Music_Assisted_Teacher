import { api } from "../api/client.js";
import { esc, pageHeader } from "../utils/dom.js";

export async function renderHome(container) {
  const [stats, classes, lessons] = await Promise.all([api.stats(), api.classes(), api.lessons()]);
  container.innerHTML = pageHeader("音乐课堂工作台", "管理班级、准备教案、整理课堂记录与编曲作品。") + `
    <div class="grid two">
      <div class="grid">
        <section class="card hero"><span class="eyebrow">数据库驱动备课</span><h2>让地方音乐资源，成为乡村老师拿来就能上的课堂</h2><p>班级画像、歌曲资源、教学游戏、乐理话术和课后反馈形成完整闭环。</p><button class="btn primary" data-route="assistant">开始备课</button></section>
        <div class="metrics"><button class="metric-link" data-route="resources" data-resource-kind="songs"><small>地区歌曲</small><b>${stats.songs}</b></button><button class="metric-link" data-route="resources" data-resource-kind="games"><small>课前游戏</small><b>${stats.games}</b></button><button class="metric-link" data-route="resources" data-resource-kind="theory"><small>乐理讲解</small><b>${stats.theory}</b></button><button class="metric-link" data-route="resources" data-resource-kind="mistakes"><small>易错纠正</small><b>${stats.mistakes}</b></button></div>
        <section class="card"><div class="card-head"><h3>最近教案</h3><button class="link" data-route="lessons">查看全部</button></div><div class="list">${lessons.length ? lessons.slice(0, 4).map(plan => `<button class="list-row list-row-link" data-route="lessons"><span class="iconbox">谱</span><div><b>${esc(plan.title)}</b><small>${esc(plan.class_name)} · ${esc(plan.created_at)}</small></div><span class="status ok">${plan.generation_mode === "ai" ? "已完善" : "初稿"}</span></button>`).join("") : '<div class="empty">还没有教案，可以先生成第一份。</div>'}</div></section>
      </div>
      <section class="card"><div class="card-head"><h3>班级画像</h3><button class="link" data-route="classes">管理班级</button></div><div class="list">${classes.map(item => `<button class="list-row list-row-link home-class-list-row" data-route="classes"><span class="iconbox">${item.grade}</span><div><b>${esc(item.name)}</b><small>${item.student_count} 人 · ${esc(item.province)} · ${esc(item.activity_level)}</small></div><span class="pill">${esc(item.preferred_method)}</span></button>`).join("")}</div></section>
    </div>`;
}
