
export async function renderAIEngine(app) {
 app.innerHTML=`
 <div class="page-header"><h1>AI教学引擎</h1><p>模型可替换，教学结构保持统一。</p></div>
 <div class="card">
 <h2>AI模型</h2>
 <select id="aiModel"><option>自动选择</option><option>GPT-5.6-terra</option><option>GLM-5.3-flash</option><option>DeepSeek</option><option>Qwen</option></select>
 <p class="muted">系统不预设模型优劣，教师可根据需求选择推理引擎。</p>
 </div>
 <div class="card"><h2>生成策略</h2>
 <label><input type="radio" checked name="strategy">标准生成</label>
 <label><input type="radio" name="strategy">深度优化</label>
 <label><input type="radio" name="strategy">快速生成</label>
 </div>
 <div class="card"><h2>生成流程</h2><p>读取班级画像 → 检索音乐知识库 → 生成教学方案 → Schema校验 → 保存教案。</p></div>`;
}
