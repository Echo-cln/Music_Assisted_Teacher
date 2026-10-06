# EdgeOne 前端 + FastAPI 后端部署

当前站点 `https://music-assisted-teacher-qiszkhgt.edgeone.cool` 是静态前端。它不会因为连上 Supabase 就自动拥有 FastAPI API；Supabase 提供数据库和对象存储，本项目的登录、教案、音频分析等 API 仍由 FastAPI 提供。

## EdgeOne Pages 设置

仓库根目录的 [`edgeone.json`](../edgeone.json) 将静态发布目录设为 `frontend`。导入仓库时使用：

| 设置 | 值 |
| --- | --- |
| 根目录 | 仓库根目录 `/` |
| 框架预设 | Other / Static |
| 输出目录 | `frontend` |
| 安装/构建命令 | 使用仓库 `edgeone.json` 中的配置 |

部署后，`/assets/css/main.css` 应返回 CSS，`/assets/js/main.js` 应返回 JavaScript。

## 1. 部署持久运行的 FastAPI

在支持 Docker 的云主机或容器服务上，拉取 `Echo-cln/Music_Assisted_Teacher`。在仓库根目录复制 `.env.edgeone.example` 为 `.env`，填好真实值，然后运行：

```bash
docker compose -f docker-compose.edgeone.yml up -d --build
```

Compose 会在启动前检查 `DATABASE_URL`、`SUPABASE_URL` 和 `SUPABASE_SERVICE_ROLE_KEY`，避免漏配后悄悄退回临时 SQLite。音频、乐谱等文件放在 Supabase Storage；数据库连接使用 Supabase 的 SQLAlchemy Session pooler URI。运行目录 `runtime/` 挂载给后端作临时/本地文件处理目录。

必须为 API 配置一个浏览器可访问的 **HTTPS** 地址，并把请求转发到容器的 `8000` 端口。不要把数据库密码、AI Key 或 Supabase 服务密钥放到前端、EdgeOne 静态文件或 GitHub。独立 API 域名跨站登录需要 HTTPS；后端的 Cookie 已按 `SESSION_COOKIE_SECURE=true` 设置为 `SameSite=None; Secure`。

### EdgeOne Python Cloud Functions 是否可直接替代

EdgeOne Makers 支持 Python/FastAPI 函数，但平台单函数包上限为 128 MB、请求/响应体上限为 6 MB、单次执行上限为 120 秒。当前应用还有音频上传与 CPU 密集分析，以及可能持续超过函数时限的模型任务和进程内后台线程。因此，本项目的完整 API 暂按持久运行的 Docker 服务部署，避免登录能用而音频或长任务中断。若未来改为函数架构，需要另做任务队列/工作进程和大文件直传存储改造。

## 2. 将 EdgeOne API 请求代理到后端

获得后端服务商分配的 HTTPS 地址后，在仓库根目录 `edgeone.json` 的现有配置中加入反向代理规则。将示例主机替换成真实后端地址：

```json
{
  "rewrites": [
    {
      "source": "/api/*",
      "destination": "https://你的后端服务商域名/api/:splat"
    }
  ]
}
```

这会让浏览器继续请求 EdgeOne 预览站点的同源 `/api`，EdgeOne 再把请求转发给 FastAPI。前端 `frontend/config.js` 保持 `apiBaseUrl: "/api"`，Cookie 也由 EdgeOne 同源响应写入，避免前端直连另一个域名造成的跨站 Cookie 问题。EdgeOne 的 `edgeone.json` 支持 rewrite 路由；不要在后端地址确定前提交占位域名。

后端容器的 `8000` 端口必须能被 EdgeOne 源站请求访问；优先使用云服务商分配的 HTTPS 主机名。修改代理规则后，EdgeOne Pages 需要重新部署，才能让 `/api/auth/me` 命中 FastAPI。

后端 `.env` 保持：

```dotenv
ALLOWED_ORIGINS=https://music-assisted-teacher-qiszkhgt.edgeone.cool
SESSION_COOKIE_SECURE=true
```

预览 URL 的查询参数不属于 Origin，不要放进 `ALLOWED_ORIGINS`。若以后改成浏览器直连后端，才需要把 `frontend/config.js` 改为后端 HTTPS 地址并保留 CORS/Cookie 设置。

## 3. 验收顺序

1. 浏览器打开 `https://你的后端HTTPS地址/api/health`，应返回 `{"status":"ok"}`。
2. 将该后端地址写入 `frontend/config.js` 并让 EdgeOne Pages 重新部署。
3. 打开 EdgeOne 站点，在开发者工具 Network 中确认 `/api/auth/me` 请求发往后端 HTTPS 地址，而不是 `music-assisted-teacher-qiszkhgt.edgeone.cool/api`。
4. 登录后刷新页面，确认会话 Cookie 与账号状态保留。
5. 分别验证教案保存、资源读取、音频上传/分析、快速和深度生成。

## 数据说明

Supabase 数据库保存账户、教案、音频分析等结构化数据；Supabase Storage 保存私有媒体文件。SQLite 旧数据需要单独迁移。若旧数据库中的记录仍引用本地路径，必须先迁移对应文件到对象存储并更新引用，否则云端无法读取这些旧文件。

官方文档：[EdgeOne Pages 构建配置](https://pages.edgeone.ai/document/build-guide)、[EdgeOne Python Cloud Functions](https://pages.edgeone.ai/document/python)、[EdgeOne Cloud Functions 限制](https://pages.edgeone.ai/document/cloud-functions)。
