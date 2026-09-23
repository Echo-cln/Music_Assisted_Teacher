import { esc } from "../utils/dom.js";

export function lessonView(plan) {
  const content = plan.content;
  const summary = content.summary;
  return `<article class="lesson" id="lessonDocument">
    <header><span>数据库检索 + 班级画像适配 · ${plan.generation_mode === "ai" ? "AI 生成" : "规则生成"}</span><h2>${esc(content.title)}</h2><p>${esc(summary.class_name)} · ${summary.duration} 分钟 · ${esc(summary.region)}</p></header>
    <div class="lesson-summary"><div><small>建议音域</small><b>${esc(summary.range_note)}</b></div><div><small>歌曲难度</small><b>${esc(summary.difficulty)}</b></div><div><small>教学时长</small><b>${summary.duration} 分钟</b></div><div><small>适用班级</small><b>${esc(summary.class_name)}</b></div></div>
    <section><h3>一、教学目标</h3><ol>${content.objectives.map(item => `<li>${esc(item)}</li>`).join("")}</ol></section>
    <section><h3>二、教学重点与难点</h3><p><b>重点：</b>${esc(content.key_points)}</p><p><b>难点：</b>${esc(content.difficulties)}</p><p><b>准备：</b>${esc(content.preparation)}</p></section>
    <section><h3>三、完整课堂流程</h3><div class="timeline">${content.timeline.map(item => `<div><b>${item.minutes} 分钟</b><strong>${esc(item.stage)}</strong><p><small>教师活动</small><br>${esc(item.teacher)}</p><p><small>学生活动</small><br>${esc(item.students)}</p></div>`).join("")}</div></section>
    <section><h3>四、乐理大白话</h3><p><b>${esc(content.theory_explanation.term)}：</b>${esc(content.theory_explanation.script)}</p></section>
    <section><h3>五、易错点与纠正</h3><p><b>预判：</b>${esc(content.mistake_practice.problem)}</p><p><b>练习：</b>${esc(content.mistake_practice.correction)}</p></section>
    <section><h3>六、分层教学</h3><ul>${content.differentiation.map(item => `<li>${esc(item)}</li>`).join("")}</ul></section>
    <section><h3>七、课堂评价</h3><p>${esc(content.assessment)}</p></section>
  </article>`;
}

