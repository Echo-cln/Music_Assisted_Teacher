import { esc } from "./dom.js";

function plainLesson(plan) {
  const c = plan.content, s = c.summary || {};
  const rows = (c.timeline || []).map(item => `<tr><td>${item.minutes} 分钟<br><b>${esc(item.stage)}</b></td><td>${esc(item.teacher)}</td><td>${esc(item.students)}</td></tr>`).join("");
  return `<article><h1>${esc(c.title)}</h1><p>${esc(s.class_name)} · ${s.duration} 分钟 · ${esc(s.region)}</p><h2>教学目标</h2><ol>${(c.objectives || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol><h2>教学重点与难点</h2><p><b>重点：</b>${esc(c.key_points)}</p><p><b>难点：</b>${esc(c.difficulties)}</p><p><b>准备：</b>${esc(c.preparation)}</p><h2>完整课堂流程</h2><table><thead><tr><th>时间与环节</th><th>教师活动</th><th>学生活动</th></tr></thead><tbody>${rows}</tbody></table><h2>乐理大白话</h2><p>${esc(c.theory_explanation?.script || "")}</p><h2>易错点与纠正</h2><p><b>预判：</b>${esc(c.mistake_practice?.problem || "")}</p><p><b>练习：</b>${esc(c.mistake_practice?.correction || "")}</p><h2>分层教学</h2><ul>${(c.differentiation || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul><h2>课堂评价</h2><p>${esc(c.assessment || "")}</p></article>`;
}

export function exportLessonWord(plan) {
  const source = `<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:'Microsoft YaHei';line-height:1.65;color:#222}article{max-width:900px;margin:auto}h1{text-align:center}h2{margin-top:26px;border-bottom:1px solid #999;padding-bottom:5px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #777;padding:8px;vertical-align:top;text-align:left}</style></head><body>${plainLesson(plan)}</body></html>`;
  const blob = new Blob([source], { type: "application/msword" });
  const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${plan.title}.doc` });
  link.click(); URL.revokeObjectURL(link.href);
}

export function exportLessonPdf(plan) {
  const win = window.open("", "_blank");
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(plan.title)}</title><style>@page{size:A4;margin:17mm}body{font-family:'Microsoft YaHei';line-height:1.62;color:#222;font-size:11pt}article{max-width:100%}h1{text-align:center;font-size:20pt}h2{margin-top:20px;border-bottom:1px solid #777;padding-bottom:4px;font-size:14pt;page-break-after:avoid}table{width:100%;border-collapse:collapse;font-size:9.5pt}th,td{border:1px solid #777;padding:6px;vertical-align:top;text-align:left}tr{break-inside:avoid}</style></head><body>${plainLesson(plan)}<script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}
