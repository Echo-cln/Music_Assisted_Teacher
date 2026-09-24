# 乡音智谱 · 乡村音乐教室 AI 教学助手

这是一个可独立运行的 Python 全栈项目，面向乡村小学音乐教学场景。当前版本已经从单机演示升级为**多教师账号 + 个人数据隔离 + 页面可编辑知识库 + 后台 AI 生成任务**。

## 本版本新增

- 教师注册 / 登录 / 退出；登录态使用 HttpOnly Cookie。
- 不同教师的班级、教案、课堂记录、反馈和上传内容相互隔离。
- 系统公共音乐知识库共享；教师可在页面直接新增、编辑、删除自己的资源。
- AI 教案生成改为后台任务：离开 AI 页面后仍继续生成，刷新/切换页面不会丢失任务。
- 生成开始后立即展示规则生成的可用教案骨架，AI 在后台继续增强教师话术和课堂活动。
- 右下角提供“生成步骤与依据”面板：读取班级画像 → 检索知识库 → 生成骨架 → AI 优化 → 结构/课时校验。该面板用于可解释状态反馈，不展示模型内部隐藏思维链。
- GLM 调用不再要求模型重复输出数据库 `generation_context`，减少输出 token 和等待时间。

## 技术栈

- 后端：Python 3.11+、FastAPI、SQLAlchemy、SQLite
- 前端：HTML、CSS、原生 ES Modules
- AI：智谱 BigModel（默认 `glm-5.3-flash`）；未配置密钥时自动使用规则版生成，完整流程仍可演示
- 音频：librosa、NumPy、Basic Pitch（单人练唱的参考音频逐音评测）
- 数据导入：openpyxl

## 快速运行（Windows）

第一次运行：

```text
setup.bat
```

之后：

```text
run.bat
```

浏览器打开：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/api/docs
```

### 演示账号

```text
用户名：demo
密码：demo123456
```

也可以在登录页直接注册新教师账号。新账号会拥有独立的班级、教案与个人资源空间。

演示账号首次启动会自动升级为系统管理员。请在交付演示之外及时修改其默认密码。

## 配置智谱 GLM

出于安全原因，交付压缩包中的 `backend/.env` 不包含任何 API Key。请在本地编辑：

```text
backend/.env
```

填入：

```text
AI_API_KEY=你的密钥
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_MODEL=glm-5.3-flash
```

密钥只由后端读取，不会发送到前端代码。

## 邮箱验证码与系统管理

注册必须填写确认密码和邮箱验证码。验证码会使用真实 SMTP 邮件发送；未配置 SMTP 时，注册页会明确提示“服务未配置”，不会生成假验证码。将以下字段加入 `backend/.env`：

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=your-account@example.com
SMTP_PASSWORD=你的SMTP授权码
SMTP_FROM=your-account@example.com
```

若使用 QQ 邮箱，本包已预填 `SMTP_HOST=smtp.qq.com` 和 `SMTP_PORT=465`；只需将 `SMTP_USERNAME`、`SMTP_FROM` 填为你的 QQ 邮箱，将 `SMTP_PASSWORD` 填为 QQ 邮箱“账户 → 开启服务”生成的 SMTP 授权码。不要填写 QQ 登录密码。

系统管理入口仅向 `role=admin` 用户显示，可管理教师/管理员角色和验证状态。邮箱验证码只证明联系方式可用；如需法定意义上的实名核验或手机短信，需要另行接入合规短信/实名服务商及其凭据。

## 数据隔离设计

系统采用**同一数据库 + teacher_id / owner_teacher_id 租户隔离**，而不是给每位教师复制一个 SQLite 文件：

- `Teacher`：教师账号
- `ClassProfile`：教师自己的班级画像
- `LessonPlan`：教师自己的教案
- `ClassroomRecord`：教师自己的课堂记录
- `Feedback`：教师自己的反馈
- `Song / TeachingGame / MusicTheory / TeachingMistake`
  - `owner_teacher_id = NULL`：系统公共资源
  - `owner_teacher_id = 当前教师`：教师个人资源

普通教师不能直接修改系统公共资源，但可以“复制为我的资源”后自行编辑。

## AI 生成任务

创建教案后，后端生成 `GenerationJob`：

```text
pending → running → completed / failed
```

页面会立即显示本地规则骨架，同时后台继续调用 GLM。任务状态持久化到数据库，因此切换页面不会中断。

## 音频分析任务与关联

上传音频后会创建持久化的 `AudioAnalysisJob`。右下角进度来自后端真实阶段（保存文件、提取音高/节拍、计算指标、保存结果），切换页面或刷新页面后任务仍可查询。

音频分析可选择关联某一教案，也可保留为“私人练唱”。课堂反馈仅能选择同一教案下已归档的音频分析；导入的音频摘要仍可编辑。

## 测试

项目根目录执行：

```bash
python -m pytest -q
```

当前测试覆盖 AI Provider、教案预览/调整/保存、个人资源、推荐规则。
