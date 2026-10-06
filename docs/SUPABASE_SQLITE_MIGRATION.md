# 将本地 SQLite 数据迁移到 Supabase

本项目的 Supabase 数据库已经建好表结构，但新项目不会自动包含你电脑上的 `backend/data/zhiban.db`。迁移要在保存 SQLite 文件的那台电脑上运行，这样数据库文件和密码不必上传给别人。

## 迁移前

1. 确认旧数据库文件存在，默认位置是 `backend/data/zhiban.db`。如果文件名或目录不同，运行时用 `--source` 指定。
2. 确认 `backend/.env` 里的 `DATABASE_URL` 是 Supabase PostgreSQL 连接串。迁移脚本只把它作为目标，不会把 SQLite 改成目标或删除源文件。
3. 确认当前目标 Supabase 项目正确。脚本会显示脱敏后的目标连接地址和各表记录数，并且目标应用表必须全部为空；发现任何已有数据都会停止，不会覆盖或合并。

## Windows PowerShell 执行

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe backend\scripts\migrate_sqlite_to_supabase.py
```

检查显示的 SQLite 来源、Supabase 目标和记录数，确认无误后输入 `MIGRATE`。脚本会先在 SQLite 文件旁创建带时间戳的 `.bak` 副本，再将所有匹配到的应用表放进同一个 PostgreSQL 事务。导入有错误时，PostgreSQL 事务整体回滚；成功后会逐表核对行数，并重置整数主键序列。

如果旧库路径不同：

```powershell
.\.venv\Scripts\python.exe backend\scripts\migrate_sqlite_to_supabase.py --source "E:\\Programs\\musicTearcher\\backend\\data\\zhiban.db"
```

## 迁移范围与文件说明

迁移范围包含 SQLite 与当前版本应用模型共同拥有的表及字段，例如教师账号（包括密码哈希和盐值）、班级、歌曲、教案、课堂记录、反馈、音频分析、编曲工程和任务记录。旧 SQLite 缺少的新字段由当前模型默认值补齐。源库中的未知表不会写入 Supabase。

音频、乐谱、伴奏和 SoundFont 文件本体不存放在 SQLite 表里；数据库里只有文件路径。因此这一步迁移的是记录和路径，不会自动把本机文件上传到线上存储。迁移后，本地运行的后端仍能读本机原文件；线上后端若要播放这些资源，还需要把文件放入线上可访问的持久化存储，并更新对应路径。

## 迁移后

- 本地 `backend/.env` 和线上后端环境变量都设置为同一个 Supabase `DATABASE_URL`，两边就会读写同一份数据库记录。
- 不要把 `DATABASE_URL`、数据库密码或 SQLite 文件提交到 GitHub。
- 如果目标库已注册账号或写入了其他数据，脚本会停止。先备份目标库并处理重复账号/主键，再做有针对性的合并；不要通过清空目标库来绕过保护。
