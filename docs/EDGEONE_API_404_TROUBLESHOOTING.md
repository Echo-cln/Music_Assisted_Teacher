# EdgeOne API 404 部署验收

## 目的

当前登录页已能打开，但登录请求 `POST /api/auth/login` 返回 404。前端与 API 同域，默认请求地址是 `/api`。后端仓库中已定义 `POST /api/auth/login`，因此验收重点是确认 EdgeOne 部署包含并注册 Python 云函数，而不是更改登录表单或账号密码。

## 本次代码修复

- `cloud-functions/api/[[default]].py` 显式声明 `app = FastAPI(...)`，让 EdgeOne 能识别函数入口。
- 外层 FastAPI 挂载现有后端应用，继续使用原有路由和中间件，并显式转发生命周期，使数据库初始化仍会运行。
- 函数入口将 `backend/` 加入 Python 模块搜索路径。
- 前端不再把所有 404 都错误描述成“只部署了静态页面、需要另部署 FastAPI”；现在按响应内容区分站点级 404、FastAPI 路由 404 和普通函数路由 404。

## EdgeOne 项目设置

部署应使用：

| 设置 | 值 |
| --- | --- |
| Git 仓库 | `Echo-cln/Music_Assisted_Teacher` |
| 分支 | `pilot/rural-classroom-readiness` |
| 项目根目录 | 仓库根目录 |
| 静态输出目录 | `frontend` |
| Python 函数入口 | `cloud-functions/api/[[default]].py` |

不要只上传 `frontend/` 的静态文件。构建完成后，在部署详情确认提交号是本次修复后的提交，并确认 Python 函数构建成功。预览 URL 以这次部署详情生成的链接为准。

## 分层验收

按顺序测试，不要直接用登录失败来判断整个服务：

1. 打开 `GET /api/health`。预期 HTTP 200，响应为 `{"status":"ok"}`。
2. 向 `POST /api/auth/login` 发送格式正确但不存在的账号。预期 HTTP 401（账号或密码错误）；收到 401 表示登录路由已经到达后端。
3. 使用有效账号登录。预期 HTTP 200，并收到会话 Cookie。
4. 登录后访问 `GET /api/auth/me`。预期 HTTP 200 并返回当前教师资料。

使用 PowerShell 做第 1 项：

```powershell
Invoke-WebRequest -Uri "https://你的本次预览域名/api/health" -Method GET
```

第 2 项可在浏览器开发者工具的 Network 面板检查真实的 `POST /api/auth/login` 响应。不要把密码、Cookie 或 API Key 发到聊天或提交进 GitHub。

## 如何读错误

| 响应 | 下一步 |
| --- | --- |
| 页面显示 EdgeOne `404_NOT_FOUND — The site does not exist` | EdgeOne 尚未解析到该项目/部署域名；从当前部署详情重新打开它生成的预览链接。请求还没进入应用。 |
| `/api/health` 返回 FastAPI JSON 404 | 函数已响应，但路径未匹配；检查入口文件、EdgeOne 去除的 `/api` 前缀和后端路由前缀。 |
| `/api/health` 返回 500/502/503 | 函数路由已接通；查看同一条预览部署的函数日志，继续检查导入、环境变量和数据库启动。 |
| 健康检查成功，登录请求返回 401 | 登录路由正常；核对账号密码或数据库内用户记录。 |
| 浏览器报告网络/CORS 错误 | 检查请求 API 域名与后端跨域设置；同域部署通常不需要跨域请求。 |

## 后端环境变量

健康检查启动时会执行数据库初始化，所以 EdgeOne 函数环境中必须有可连接的 `DATABASE_URL`。还要将 `APP_ENV` 设置为 `production`，确保会话 Cookie 使用 HTTPS 安全属性。模型、SMTP、Supabase Storage 密钥只在相应功能启用时配置；所有密钥应放在 EdgeOne 环境变量，不应提交到仓库。

数据库或密钥错误不会解释“路由未注册”的 404：它们通常在函数入口已经运行后导致启动错误或 5xx。先通过健康检查，再逐项配置与验证。

## 平台限制

EdgeOne Cloud Functions 文档给出的单次函数执行上限为 120 秒、请求/响应体上限为 6 MB、单函数包上限为 128 MB。短请求和登录可以先按上述流程验收；超过平台限制的长时模型生成、音频处理和大文件上传需要单独评估后端运行方式。
