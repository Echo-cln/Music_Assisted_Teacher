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
- 音频：librosa、NumPy
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

## 测试

项目根目录执行：

```bash
python -m pytest -q
```

当前测试覆盖 AI Provider、教案预览/调整/保存、个人资源、推荐规则。
