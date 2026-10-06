# EdgeOne 部署

仓库根目录的 [`edgeone.json`](../edgeone.json) 已将 EdgeOne 静态发布目录设为 `frontend`，并关闭前端构建和依赖安装。导入仓库时，项目根目录应为仓库根目录；如果控制台已有旧构建设置，请改为：

| 设置 | 值 |
| --- | --- |
| 根目录 | `/`（仓库根目录） |
| 框架预设 | Other / Static |
| 安装命令 | 留空或使用仓库 `edgeone.json` |
| 构建命令 | 留空或使用仓库 `edgeone.json` |
| 输出目录 | `frontend` |

部署后检查 `https://你的站点/assets/css/main.css?v=20261005-3`：应返回 CSS 文本，响应类型为 `text/css`。若返回 HTML、404 或登录页，说明发布目录没有包含 `frontend/assets/`，页面就会显示浏览器默认样式。再检查 `https://你的站点/assets/js/main.js?v=20261005-3` 是否返回 JavaScript。

静态资源可以放在 EdgeOne Pages，但页面仍需单独运行 FastAPI 后端。EdgeOne 也提供 Python Cloud Functions；本项目当前使用 SQLAlchemy/SQLite、本地上传目录、CPU 密集的音频处理和后台任务线程，不能只靠静态 Pages 完整运行。迁入函数前还需将数据库、上传文件和长任务改接持久化数据库、对象存储与任务服务。当前部署仍使用前端 Pages + 持久化 Python/Docker 后端。

官方说明：[EdgeOne Pages 构建配置](https://pages.edgeone.ai/document/build-guide)、[edgeone.json 配置](https://pages.edgeone.ai/document/edgeone-json)、[Python Cloud Functions](https://pages.edgeone.ai/document/python)。

## 1. 部署 Python 后端

在一台可运行 Docker 的云主机或容器服务中克隆本仓库，在仓库根目录创建 `.env`，填入已有的 AI 与邮件环境变量。使用 Supabase 时，再将 Connect 页面中 **SQLAlchemy → Session pooler** 的 URI 设为 `DATABASE_URL`：

```bash
docker compose -f docker-compose.edgeone.yml up -d --build
```

`DATABASE_URL` 不要提交到仓库。首次连接全新 Supabase 项目时，FastAPI 启动会按现有 SQLAlchemy 模型创建表；这不会把旧 SQLite 用户、教案、分析记录或资源数据复制过去。`runtime/` 仍用于后端本地上传文件，数据库切换不会自动迁移音频文件。

将 HTTPS 域名（例如 `https://api.example.com`）反向代理到服务器的 `8000` 端口。`runtime/` 是数据库和上传音频的持久化目录，不能删除。

在 `docker-compose.edgeone.yml` 中把 `ALLOWED_ORIGINS` 改为 EdgeOne Pages 的真实 HTTPS 域名；跨域 Cookie 登录还必须保持 `SESSION_COOKIE_SECURE=true`。

## 2. 导入 EdgeOne Pages

在 EdgeOne Pages 连接 GitHub 仓库 `Echo-cln/Music_Assisted_Teacher`，把静态发布目录设为 `frontend`，不需要 Node 构建命令。

部署前将 `frontend/config.js` 中的 `apiBaseUrl` 改为后端地址加 `/api`，例如：

```js
window.__APP_CONFIG__ = { apiBaseUrl: "https://api.example.com/api" };
```

提交到 `main` 后，EdgeOne Pages 会从 GitHub 拉取并更新前端；后端则按上述 Docker 服务独立升级。

## 3. 上线检查

1. 打开 `https://api.example.com/api/health`，应返回数据库正常状态。
2. 打开 EdgeOne 站点，注册/登录后刷新页面，登录状态应仍存在。
3. 上传一段课堂录音；任务进度应从“读取音频”依次走到“保存结果”，取消后不应新增分析记录。
4. 分别选择快速与深度教案生成。若模型服务本身拒绝请求，页面会显示模型名、接口地址、HTTP 状态或返回字段，而不会伪造一份 AI 成功结果。
