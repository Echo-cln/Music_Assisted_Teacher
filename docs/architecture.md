# 系统架构

## 核心闭环

教师账号 → 班级画像 → 数据库检索 / 推荐 → 教案生成任务 → 课堂记录 → 课后反馈 → 更新班级画像。

## 多教师数据隔离

采用“同一数据库 + 租户字段”而非“每个老师一个 SQLite 文件”。

- Teacher：教师账号
- AuthSession：登录会话
- ClassProfile / LessonPlan / ClassroomRecord / Feedback / AudioAsset：`teacher_id`
- Song / TeachingGame / MusicTheory / TeachingMistake：`owner_teacher_id`
  - NULL：系统公共资源
  - 当前教师 ID：个人资源

API 层对所有个人数据执行教师归属过滤。

## AI 生成架构

1. 根据歌曲 + 班级画像 + 知识库先生成规则版可用教案骨架。
2. 创建 GenerationJob，并立即返回骨架与任务 ID。
3. 后台线程调用 GLM 增强教师话术与活动细节。
4. 前端全局轮询 GenerationJob，即使用户切换页面也不会中断。
5. AI 完成后将增强版教案替换骨架。

页面只展示可验证的“处理步骤与依据”，不展示模型内部隐藏思维链。

## 分层职责

- frontend/：页面、认证交互、知识库 CRUD、全局生成状态、波形可视化。
- backend/app/api/：HTTP 接口、权限与请求校验。
- backend/app/core/：配置与安全工具。
- backend/app/services/：推荐、教案生成、GenerationJob、音频处理。
- backend/app/repositories/：数据查询与资源可见性。
- backend/app/models/：SQLAlchemy 数据模型。
- backend/app/schemas/：Pydantic 输入输出模型。
- backend/scripts/：Excel 导入、演示账号与班级初始化。

## 数据原则

1. 原始 Excel 只读保存，导入后由 SQLite 提供运行时查询。
2. 系统公共资源与个人资源分层，普通教师不能直接污染公共知识库。
3. AI 只使用检索出的歌曲、班级画像和教学资源，不允许虚构关键事实。
4. API Key 只存在后端 `.env`，交付压缩包不携带用户密钥。
5. AI 慢请求采用后台任务，不把生命周期绑定到当前页面 DOM。
6. 没有原唱时音频分析必须明确标注为示意结果。
