# 乡音智谱

**面向乡村小学音乐课堂的备课、记录与数字编曲工具。**

乡音智谱把班级画像、歌曲与教学资源、教案、课堂反馈、音频分析和简易编曲工作台放在一个可自行运行的 Web 项目中。教师可以从现有歌曲和班级情况准备教案，记录课堂表现，再把音频证据和课后反馈整理到相应档案里。

项目提供的是教学辅助工具。教案内容由教师核对和编辑；音频分析结果受录音条件影响，不用于正式考核或替代教师判断。

> 项目目前以中文界面和本地运行流程为主。生产部署说明见 [`docs/EDGEONE_DEPLOYMENT.md`](docs/EDGEONE_DEPLOYMENT.md)。

## 功能概览

- **班级与教学档案**：建立班级画像，按教师账号保存教案、课堂记录和反馈。
- **歌曲与教学资源**：检索歌曲、游戏、乐理和易错点；系统公共资源可查阅，教师也可以维护自己的资源。
- **教案准备**：根据歌曲、班级画像和教师要求生成可编辑的教案预览，调整后再保存。快速与深度模式都以完整教案为目标，模式差别侧重生成速度；实际等待时间受模型服务和网络状况影响。
- **课堂音频分析**：记录音频、波形与分段声学指标，辅助观察音高稳定度、节拍、力度和清晰度；配置模型后还可以整理与已有证据对应的教学建议。
- **单人练唱评测**：在参考主旋律和练唱录音可用时进行旋律对齐与逐音比较。参考素材为原唱/伴奏混音时，需要额外安装人声分离组件；条件不满足时会说明原因，不输出虚构分数。
- **数字乐器与编曲**：在钢琴键盘或卷帘中输入音符、生成多轨编曲并试听；支持导入 MusicXML、MIDI。教师自己的 SF2 音色包保存在当前浏览器的本地存储中，不会上传到项目服务器。
- **五线谱图片识别**：配置本机 Audiveris 后，可将 PNG、JPG、WEBP、TIFF 或 PDF 五线谱识别为可编辑音符。识别结果需要人工核对。
- **账号与数据隔离**：教师注册、登录和退出；个人班级、教案、反馈、上传音频与资源按教师归属保存。

## 技术组成

| 部分 | 技术 |
| --- | --- |
| 前端 | HTML、CSS、原生 JavaScript ES Modules |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy、Pydantic |
| 默认本地数据库 | SQLite |
| 音频分析 | librosa、NumPy、SciPy、Basic Pitch |
| 乐谱与资源 | MusicXML / MIDI 解析、可选 Audiveris、openpyxl |
| 可选模型服务 | 通过后端配置兼容的模型 API；密钥不写入前端 |
| 可选混音人声分离 | Demucs |

## 环境要求

- Python **3.11 或更新版本**。
- Git，用于克隆仓库。
- Windows 可使用项目根目录的 `setup.bat` 和 `run.bat`；macOS/Linux 可使用 `setup.sh` 和 `run.sh`。
- 推荐使用较新的 Chrome 或 Edge 浏览器。

音色 CDN、模型服务、Audiveris 和 Demucs 属于可选外部依赖，按下文说明单独配置。

## 本地运行

### Windows

在 PowerShell 或命令提示符中执行：

```powershell
git clone https://github.com/Echo-cln/Music_Assisted_Teacher.git
cd Music_Assisted_Teacher
setup.bat
```

首次初始化会创建项目自己的 `.venv`、安装后端依赖、准备环境文件并导入歌曲与演示数据。初始化完成后启动：

```powershell
run.bat
```

浏览器打开 <http://127.0.0.1:8000>。交互式 API 文档在 <http://127.0.0.1:8000/api/docs>。

### macOS / Linux

```bash
git clone https://github.com/Echo-cln/Music_Assisted_Teacher.git
cd Music_Assisted_Teacher
bash setup.sh
bash run.sh
```

浏览器同样访问 <http://127.0.0.1:8000>。如果当前 Shell 不支持执行脚本，可以先运行 `chmod +x setup.sh run.sh`。

### 首次登录

运行初始化脚本会创建本地演示账号：

```text
用户名：demo
密码：demo123456
```

该账号仅供本地体验。部署到可被他人访问的服务器前，请改掉默认凭据或停用演示账号，并通过注册页创建自己的账号。

## 配置模型与邮件服务

初始化后复制得到 `backend/.env`（若文件不存在，可手动复制 `backend/.env.example`）。根据实际服务商、模型名称和账号权限修改配置。模板当前示例为：

```dotenv
AI_API_KEY=填写深度模式服务商的密钥
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_MODEL=glm-5.3-flash

AI_FAST_API_KEY=填写快速模式服务商的密钥
AI_FAST_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
AI_FAST_MODEL=doubao-seed-2-0-mini-260428
```

请确认密钥、接口地址和模型属于同一服务商及同一账户权限。若两个模式使用同一服务商，按该服务商的接口要求填写相同的地址和密钥。模型服务没有配置或不可用时，依赖模型的操作不会得到真实模型结果；其他本地页面和编曲功能仍可使用。

注册邮箱验证码需要 SMTP 服务。将以下字段加入 `backend/.env` 并填入邮件服务商提供的 SMTP 地址、端口、账号、授权码和发件人：

```dotenv
SMTP_HOST=
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
```

不要把 `.env`、API Key、SMTP 密码或生产环境凭据提交到 GitHub。生产环境应使用部署平台的密钥管理功能。

## 可选功能

### 混音参考的人声分离

单人练唱使用原唱/伴奏混音作为参考时，项目可通过 Demucs 分离主唱。Windows 先运行过一次 `run.bat`、确保项目 `.venv` 已创建后，再执行：

```powershell
setup_audio_pro.bat
```

macOS/Linux 可在仓库根目录执行：

```bash
.venv/bin/python -m pip install -r backend/requirements-audio-pro.txt
```

首次分离会下载模型权重，耗时和网络状况有关。建议先用 20–40 秒、主旋律清楚且与练唱内容一致的参考音频测试。安装失败或没有提取到有效人声时，逐音比较会显示未评分原因。课堂整体音频分析不要求安装 Demucs。

### 图片或 PDF 五线谱识别

MusicXML 和 MIDI 可以直接导入。图片/PDF 识谱需要自行安装 Audiveris，并在 `backend/.env` 配置 `AUDIVERIS_COMMAND`：

```dotenv
AUDIVERIS_COMMAND=C:\Program Files\Audiveris\bin\Audiveris.bat
OMR_TIMEOUT_SECONDS=180
```

如果安装版本提供的是 `Audiveris.exe`，将上例改为对应 `.exe` 路径；也可以配置 `java -jar "C:\path\Audiveris.jar"`。安装和识谱语言包问题见 [工作台验收说明](docs/WORKBENCH_ACCEPTANCE.md)。识谱不能保证完全正确，请在编曲前核对音符、调号、节奏和声部。

### 导入自己的 SF2 音色包

在数字乐器与编曲工作台导入 `.sf2` 后，可以命名、绑定乐器并试听。音色数据保存在**导入时所用浏览器的 IndexedDB** 中，因此清除站点数据、换浏览器或换设备后不会自动同步。请只导入自己有权使用的音源文件；仓库不附带第三方 SF2 音色包。

## 数据位置与备份

默认本地数据位于 `backend/data/`：

- SQLite 数据库：`backend/data/zhiban.db`
- 上传音频与文件：`backend/data/uploads/`

请定期备份这两个位置。不要将真实用户数据库、上传录音或个人密钥加入版本控制。默认 SQLite 适合本地运行和小规模体验；多人生产部署前，应根据并发、可用性和备份要求评估数据库与文件存储方案。

## 测试

在项目根目录创建并激活虚拟环境后安装开发依赖：

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q
```

测试位于 `backend/tests/`，涵盖模型接口适配、教案数据结构、音频分析证据、乐谱导入、编曲和资源推荐等模块。涉及真实模型、外部音源、Demucs 与 Audiveris 的端到端行为，仍需要在相应环境中单独验收。

## EdgeOne 部署

项目不是纯静态站点：前端可以放在 EdgeOne Pages，FastAPI 后端、数据库、上传文件和音频处理需要运行在支持 Python/Docker 的后端服务中。

简要步骤：

1. 在一台支持 Docker 的服务器或容器服务中克隆本仓库。
2. 按部署文档准备根目录环境变量、持久化 `runtime/` 目录和 HTTPS 反向代理，再运行：

   ```bash
   docker compose -f docker-compose.edgeone.yml up -d --build
   ```

3. 将 EdgeOne Pages 连接到本仓库，根目录保持仓库根目录；仓库根目录的 `edgeone.json` 会将静态输出目录设为 `frontend`，无需 Node 构建命令。
4. 将 `frontend/config.js` 的 `apiBaseUrl` 设置为后端 HTTPS 地址加 `/api`，并把后端 `ALLOWED_ORIGINS` 设为真实 Pages 域名。
5. 按部署文档检查 `/api/health`、登录 Cookie、音频上传和任务流程。

完整配置、持久化要求和上线检查见 [`docs/EDGEONE_DEPLOYMENT.md`](docs/EDGEONE_DEPLOYMENT.md)。SQLite 和上传文件必须挂载到持久化存储；临时容器文件系统不能作为长期数据目录。

## 项目结构

```text
.
├── api/                       # 部署适配入口
├── backend/
│   ├── app/api/routes/        # FastAPI 路由
│   ├── app/models/            # 数据模型
│   ├── app/services/          # 教案、音频、编曲与识谱服务
│   ├── data/raw/              # 初始教学资源数据
│   ├── scripts/               # Excel 导入与演示数据初始化
│   └── tests/                 # 后端测试
├── frontend/                  # 静态前端与页面资源
├── docs/                      # 架构、部署、方法与验收说明
├── setup.bat / setup.sh       # 本地初始化
└── run.bat / run.sh           # 本地启动
```

## 相关文档

- [系统架构](docs/architecture.md)
- [项目状态与边界](docs/status.md)
- [EdgeOne 部署](docs/EDGEONE_DEPLOYMENT.md)
- [音频分析方法与限制](docs/AUDIO_ANALYSIS_METHOD.md)
- [数字乐器与编曲工作台验收](docs/WORKBENCH_ACCEPTANCE.md)
- [模型与音频可靠性说明](docs/LLM_AND_AUDIO_RELIABILITY.md)

## 许可证

当前仓库尚未包含 `LICENSE` 文件。仓库公开可见不等于代码已授权给他人使用、修改或再分发；在项目补充许可证前，请先联系仓库维护者确认授权。第三方模型、音源和 Audiveris 等组件分别适用其自身的服务条款或许可证。
