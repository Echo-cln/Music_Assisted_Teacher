from functools import lru_cache
import os
from pathlib import Path
import tempfile

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def normalize_database_url(database_url: str) -> str:
    """Use psycopg 3 for PostgreSQL URLs while leaving SQLite and explicit drivers alone."""
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


class Settings(BaseSettings):
    app_name: str = "乡音智谱 · 乡村音乐教室 AI 教学助手"
    app_env: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'zhiban.db'}"
    upload_dir: str = str(BACKEND_DIR / "data" / "uploads")
    # Private object storage for media shared by local and hosted backends.
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "teacher-media"
    frontend_dir: str = str(BACKEND_DIR.parent / "frontend")
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    session_cookie_secure: bool = False
    ai_api_key: str = ""
    ai_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    ai_model: str = "glm-5.3-flash"
    ai_fast_model: str = "doubao-seed-2-0-mini-260428"
    ai_fast_base_url: str = ""
    ai_fast_api_key: str = ""
    # GLM-5.3 系列始终会先生成推理 token。若不显式设置，供应商默认 max，
    # 很容易在输出教案正文前耗尽 max_tokens。其它兼容服务不会收到该参数。
    ai_reasoning_effort: str = "low"
    ai_fast_reasoning_effort: str = "low"
    ai_max_tokens: int = 32768
    ai_fast_max_tokens: int = 32768
    # 课堂模型只解释已提取的声学证据，不直接替代音频测量。默认使用已配置的快速模型，
    # 失败不会影响音频分析保存。
    classroom_insight_enabled: bool = True
    classroom_insight_max_tokens: int = 1800
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # 官方 Audiveris 可执行文件路径；留空时图片/PDF 导入会给出可操作的配置提示，
    # 不会把图片误报为已经识别的乐谱。
    audiveris_command: str = ""
    omr_timeout_seconds: int = 180

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
        # Supabase and other PostgreSQL providers commonly return postgresql:// or postgres://.
        # Route those URLs through the psycopg 3 driver installed by requirements.txt.
        self.database_url = normalize_database_url(self.database_url)
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

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
