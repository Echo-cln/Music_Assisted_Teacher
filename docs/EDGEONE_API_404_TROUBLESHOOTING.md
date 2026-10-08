# EdgeOne API 部署与验收

## 当前构建入口

| 项目 | 配置 |
| --- | --- |
| Git 仓库 | `Echo-cln/Music_Assisted_Teacher` |
| 分支 | `pilot/rural-classroom-readiness` |
| 项目根目录 | 仓库根目录 |
| 静态输出目录 | `frontend` |
| Python 函数入口 | `cloud-functions/api/[[default]].py` |
| Python 依赖 | 根目录 `requirements.txt` 与 `cloud-functions/requirements.txt` 均为独立清单 |

EdgeOne 会把 Python 函数放入单独的构建目录。依赖文件不能通过 `-r backend/requirements.txt` 引用仓库其他目录，否则构建目录里没有该相对路径，会出现 `Error parsing included file`。本地开发仍由 `setup.bat` 安装 `backend/requirements.txt`。

`edgeone.json` 使用 `cloudFunctions.maxDuration`。旧写法 `cloudFunctions.python.maxDuration` 虽被 CLI 兼容映射，但会产生弃用警告。

## 部署后分层验收

1. 打开 `GET /api/health`。预期 HTTP 200，响应为 `{"status":"ok"}`。
2. 向 `POST /api/auth/login` 发送格式正确但不存在的账号。预期 HTTP 401；收到 401 说明请求已经到达登录路由。
3. 使用有效账号登录。预期 HTTP 200，并收到会话 Cookie。
4. 登录后访问 `GET /api/auth/me`。预期 HTTP 200 并返回当前教师资料。

PowerShell 健康检查：

```powershell
Invoke-WebRequest -Uri "https://你的本次预览域名/api/health" -Method GET
```

使用浏览器开发者工具 Network 面板检查登录请求。不要把密码、Cookie 或 API Key 发到聊天或提交进 GitHub。

## 如何区分错误

| 响应 | 含义与下一步 |
| --- | --- |
| EdgeOne 页面提示 `404_NOT_FOUND — The site does not exist` | 请求没有进入项目；从当前部署详情重新打开 EdgeOne 生成的预览地址。 |
| `/api/health` 返回 FastAPI JSON 404 | Python 函数已响应，但路由未匹配；检查函数入口和路径前缀。 |
| `/api/health` 返回 500/502/503 | 函数已被调用；看同一次部署的函数日志，排查依赖导入、环境变量与数据库启动。 |
| 健康检查成功，登录返回 401 | 登录路由正常，检查账号、密码或数据库用户记录。 |

## 环境变量

EdgeOne 函数运行环境需要可连接的 `DATABASE_URL`。将 `APP_ENV` 设为 `production`，使会话 Cookie 使用 HTTPS 安全属性。模型、邮件和 Supabase Storage 凭据只在对应功能启用时设置，并保存在 EdgeOne 环境变量中。

数据库或密钥错误发生在函数启动/请求阶段，通常表现为 5xx；它们不是依赖安装阶段 `requirements.txt` 相对路径错误的原因。

## 平台限制

EdgeOne Cloud Functions 单次执行上限为 120 秒，请求/响应体上限为 6 MB，单函数包上限为 128 MB。短请求和登录可先按上面流程验收；超过时限的长时模型生成、音频处理和大文件上传需要单独评估运行方式。
