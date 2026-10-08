# EdgeOne 直接部署试点

此试点把静态前端继续从 frontend/ 发布，并通过 EdgeOne Python Cloud Functions 将同一域名下的 /api/* 请求转发给仓库现有 FastAPI 应用。

## EdgeOne 项目设置

- Git 仓库：Echo-cln/Music_Assisted_Teacher
- 试点分支：pilot/rural-classroom-readiness
- Root Directory：仓库根目录
- Output Directory：frontend
- Build Command：echo 'Static frontend: no build step required'
- Install Command：echo 'Static frontend: no packages to install'
- 环境变量：从项目环境变量面板添加，不要提交密钥到 Git

部署后先测试 GET /api/health 和 GET /api/docs，再测试登录、课程读取、教案保存等数据库接口。

## 必须配置的服务端变量

- APP_ENV=production
- DATABASE_URL：Supabase Postgres 的 SQLAlchemy/psycopg 连接串
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- SUPABASE_STORAGE_BUCKET=teacher-media
- ALLOWED_ORIGINS：EdgeOne 站点源，含协议，不含尾部路径
- AI_API_KEY、AI_FAST_API_KEY：使用对应模型时配置
- SMTP_HOST、SMTP_PORT、SMTP_USERNAME、SMTP_PASSWORD、SMTP_FROM：需要邮件验证码时配置

不要把生产密钥写进 edgeone.json、requirements.txt、代码或 GitHub Actions 日志。

## 本试点能验证的范围

- EdgeOne 能否构建仓库中的 Python Cloud Function。
- 同域 /api/* 是否能进入 FastAPI。
- FastAPI 是否能连接 Supabase，并完成无长耗时的基础 API 请求。

## 当前平台限制与未覆盖功能

EdgeOne Cloud Functions 单次请求体/响应体上限为 6 MB，函数时长默认 30 秒、最高 120 秒。当前应用音频上传配置高于该请求体上限，深度生成及音频分析也可能超过函数时长；当前后台任务还使用进程内线程。因此，本试点不表示大文件上传、长耗时任务已可在线稳定运行。后续需要将音频改为浏览器直传 Supabase Storage，并为长任务接入可靠的队列/独立 worker，或限制为函数时限内可完成的请求。

函数实例文件系统不作为持久化存储；生产媒体仍需使用 Supabase Storage。部署前确认所选区域可访问 Supabase、模型和邮件服务。
