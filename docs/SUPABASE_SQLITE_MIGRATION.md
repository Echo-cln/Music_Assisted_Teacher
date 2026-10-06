# 将本地 SQLite 数据迁移到 Supabase

本项目的 Supabase 数据库已经建好表结构，但新项目不会自动包含你电脑上的 `backend/data/zhiban.db`。迁移要在保存 SQLite 文件的那台电脑上运行，这样数据库文件和密码不必上传给别人。

## 迁移前

1. 确认旧数据库文件存在，默认位置是 `backend/data/zhiban.db`。如果文件名或目录不同，运行时用 `--source` 指定。
2. 确认 `backend/.env` 里的 `DATABASE_URL` 是 Supabase PostgreSQL 连接串。迁移脚本只把它作为目标，不会把 SQLite 改成目标或删除源文件。
3. 在同一个 Supabase 项目的 **Storage** 中创建私有 Bucket，名称为 `teacher-media`（不要开启 Public）。
4. 在本机 `backend/.env` 和 EdgeOne 后端环境变量中设置以下三项。`SUPABASE_SERVICE_ROLE_KEY` 是服务端密钥，只能留在后端环境变量中，不能放进前端配置、截图或 GitHub。可以填旧版 `service_role` JWT 或新版 `sb_secret_...`；新版 Secret 只通过 `apikey` 请求头发送，后端已针对两种格式分别处理：

   ```dotenv
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=你的服务端SecretKey
   SUPABASE_STORAGE_BUCKET=teacher-media
   ```

   `SUPABASE_URL` 和服务端 Secret Key 可在 Supabase 项目设置的 API Keys 页面查看。这里的 Key 不是数据库密码，也不是前端 publishable/anon key。迁移脚本显示脱敏后的目标地址和逐表记录数；目标应用表必须全部为空，发现已有数据会停止，不会覆盖或合并。

## Windows PowerShell 执行

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe backend\scripts\migrate_sqlite_to_supabase.py
```

检查显示的 SQLite 来源、Supabase 目标和记录数，确认无误后输入 `MIGRATE`。脚本先在 SQLite 文件旁创建带时间戳的 `.bak` 副本，再把旧库中的音频文件、歌曲原唱/伴奏/乐谱文件上传到私有 Bucket，并将数据库里的本机路径替换为云端对象引用；随后将业务表放进同一个 PostgreSQL 事务。遇到引用文件缺失时会在写数据库前停止并列出路径。数据库导入有错误时，PostgreSQL 事务整体回滚；成功后会逐表核对行数并重置整数主键序列。已上传的对象使用内容哈希命名，修复缺失文件后重试不会重复存储相同内容。

如果旧库路径不同：

```powershell
.\.venv\Scripts\python.exe backend\scripts\migrate_sqlite_to_supabase.py --source "E:\Programs\musicTearcher\backend\data\zhiban.db"
```

## 迁移范围与文件说明

迁移范围包含 SQLite 与当前版本应用模型共同拥有的表及字段，例如教师账号（包括密码哈希和盐值）、班级、歌曲、教案、课堂记录、反馈、音频分析、编曲工程和任务记录。旧 SQLite 缺少的新字段由当前模型默认值补齐。音频附件以及 `songs` 中的原唱、伴奏、乐谱路径会同时复制到 `teacher-media`，迁移后本地和 EdgeOne 后端通过同一条数据库记录与私有对象存储访问它们。源库中的未知表不会写入 Supabase。

`.sf2` 乐器包保存在浏览器 IndexedDB，而不是 SQLite，因此本迁移脚本不会自动发现或移动它们。当前版本另提供工作台的云端同步：在原浏览器的音色包卡片点击“同步到云端”，文件会进入私有 `teacher-media` Bucket；使用同一教师账号在另一设备进入工作台，点击“下载到本机”后，文件会先验证并解析，再存入该设备的 IndexedDB。云端记录包含教师归属、显示名称和乐器绑定；同一文件重复上传会按 SHA-256 更新元数据而不重复保存对象。上传上限为 128 MB，Supabase Bucket 的单文件限制也需设置为不小于实际音色包。

## 迁移后

- 本地 `backend/.env` 和线上后端环境变量都设置为同一个 Supabase `DATABASE_URL`，两边就会读写同一份数据库记录。
- 不要把 `DATABASE_URL`、数据库密码或 SQLite 文件提交到 GitHub。
- 如果目标库已注册账号或写入了其他数据，脚本会停止。先备份目标库并处理重复账号/主键，再做有针对性的合并；不要通过清空目标库来绕过保护。
