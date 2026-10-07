import { esc } from "./dom.js";

function plainLesson(plan) {
  const content = plan.content || {};
  const summary = content.summary || {};
  const objectives = content.objectives || [];
  const strategy = content.generation_strategy === "fast" ? "快速模式" : content.generation_strategy === "deep" ? "深度模式" : "历史教案";
  const evidence = content.objective_evidence || objectives.map(objective => ({ objective, evidence: "" }));
  const source = content.generation_source === "ai" ? "模型生成" : content.generation_source === "rules" ? "基础生成" : "";
  const rows = (content.timeline || []).map(item => `<tr><td>${esc(item.minutes)} 分钟<br><b>${esc(item.stage)}</b></td><td>${esc(item.teacher)}</td><td>${esc(item.students)}</td><td>${esc(item.device_action || "—")}</td><td>${esc(item.look_for || "—")}</td><td>${esc(item.low_device_option || "—")}</td></tr>`).join("");
  const evidenceRows = evidence.map((item, index) =>
    `<li><b>目标 ${index + 1}：</b>${esc(item.objective)}${item.evidence ? `<br><span>观察依据：${esc(item.evidence)}</span>` : ""}</li>`
  ).join("");
  return `<article><h1>${esc(content.title || plan.title || "音乐教案")}</h1>
    <p>${esc(summary.class_name || plan.class_name || "—")} · ${esc(summary.duration || plan.duration_minutes || "—")} 分钟 · ${esc(summary.region || "—")}</p>
    <p><b>课堂设备：</b>${esc(content.classroom_setup || "电脑与音箱")}</p><p><b>生成方式：</b>${esc(strategy)}${source ? ` · ${esc(source)}` : ""}</p>
    <h2>教学目标</h2><ol>${objectives.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    <h3>目标观察依据</h3><ul>${evidenceRows || "<li>—</li>"}</ul>
    <h2>教学重点与难点</h2><p><b>重点：</b>${esc(content.key_points)}</p><p><b>难点：</b>${esc(content.difficulties)}</p><p><b>准备：</b>${esc(content.preparation)}</p>
    <h2>完整课堂流程</h2><table><thead><tr><th>时间与环节</th><th>教师活动</th><th>学生活动</th><th>本设备安排</th><th>本段观察</th><th>无设备替代做法</th></tr></thead><tbody>${rows}</tbody></table>
    <h2>乐理大白话</h2><p>${esc(content.theory_explanation?.script || "")}</p>
    <h2>易错点与纠正</h2><p><b>预判：</b>${esc(content.mistake_practice?.problem || "")}</p><p><b>练习：</b>${esc(content.mistake_practice?.correction || "")}</p>
    <h2>分层教学</h2><ul>${(content.differentiation || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <h2>课堂评价</h2><p>${esc(content.assessment || "")}</p></article>`;
}

export function exportLessonWord(plan) {
  const source = `<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:'Microsoft YaHei';line-height:1.65;color:#222}article{max-width:1000px;margin:auto}h1{text-align:center}h2{margin-top:26px;border-bottom:1px solid #999;padding-bottom:5px}table{width:100%;border-collapse:collapse;font-size:10pt}th,td{border:1px solid #777;padding:8px;vertical-align:top;text-align:left}li{margin:.35em 0}</style></head><body>${plainLesson(plan)}</body></html>`;
  const blob = new Blob([source], { type: "application/msword" });
  const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${plan.title}.doc` });
  link.click(); URL.revokeObjectURL(link.href);
}

export function exportLessonPdf(plan) {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(plan.title)}</title><style>@page{size:A4 landscape;margin:12mm}body{font-family:'Microsoft YaHei';line-height:1.62;color:#222;font-size:10pt}article{max-width:100%}h1{text-align:center;font-size:20pt}h2{margin-top:20px;border-bottom:1px solid #777;padding-bottom:4px;font-size:14pt;page-break-after:avoid}table{width:100%;border-collapse:collapse;font-size:8.5pt}th,td{border:1px solid #777;padding:6px;vertical-align:top;text-align:left}tr{break-inside:avoid}li{margin:.3em 0}</style></head><body>${plainLesson(plan)}<script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}
