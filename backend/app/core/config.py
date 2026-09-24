from functools import lru_cache
import os
from pathlib import Path
import tempfile

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "乡音智谱 · 乡村音乐教室 AI 教学助手"
    app_env: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'zhiban.db'}"
    upload_dir: str = str(BACKEND_DIR / "data" / "uploads")
    frontend_dir: str = str(BACKEND_DIR.parent / "frontend")
    ai_api_key: str = ""
    ai_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    ai_model: str = "glm-5.3-flash"
    ai_fast_model: str = "doubao-seed-2-0-mini-260428"
    ai_fast_base_url: str = ""
    ai_fast_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        # Vercel 的部署目录是只读的；未接入生产数据库前，允许它以临时
        # SQLite 演示模式启动，而不是在建表时直接失败。数据不会跨实例保存。
        if os.getenv("VERCEL") and self.database_url.startswith("sqlite"):
            runtime_dir = Path(tempfile.gettempdir()) / "xiangyin"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            self.database_url = f"sqlite:///{runtime_dir / 'zhiban.db'}"
            self.upload_dir = str(runtime_dir / "uploads")
        # .env 中的相对路径统一相对 backend/ 解析，避免从不同工作目录启动时路径漂移。
        prefix = "sqlite:///./"
        if self.database_url.startswith(prefix):
            relative = self.database_url[len(prefix) :]
            self.database_url = f"sqlite:///{(BACKEND_DIR / relative).resolve()}"
        upload = Path(self.upload_dir)
        if not upload.is_absolute():
            self.upload_dir = str((BACKEND_DIR / upload).resolve())
        frontend = Path(self.frontend_dir)
        if not frontend.is_absolute():
            self.frontend_dir = str((BACKEND_DIR / frontend).resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()
