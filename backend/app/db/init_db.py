import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, inspect, or_, select, text, update

from app.core.config import get_settings
from app.db.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401
from app.models.entities import AudioAnalysisJob, AuthSession, Teacher, VerificationCode


TENANT_COLUMNS = {
    "songs": ("owner_teacher_id", "INTEGER"),
    "teaching_games": ("owner_teacher_id", "INTEGER"),
    "music_theory": ("owner_teacher_id", "INTEGER"),
    "teaching_mistakes": ("owner_teacher_id", "INTEGER"),
    "class_profiles": ("teacher_id", "INTEGER"),
    "lesson_plans": ("teacher_id", "INTEGER"),
    "classroom_records": ("teacher_id", "INTEGER"),
    "feedback": ("teacher_id", "INTEGER"),
    "audio_assets": ("teacher_id", "INTEGER"),
}

ADDITIVE_COLUMNS = {
    "feedback": {"audio_summary": "TEXT DEFAULT ''", "audio_analysis_id": "INTEGER"},
    "audio_analyses": {"lesson_plan_id": "INTEGER"},
    "teachers": {"role": "TEXT DEFAULT 'teacher'", "verification_status": "TEXT DEFAULT 'unverified'", "phone": "TEXT"},
    "generation_jobs": {"model_used": "TEXT DEFAULT 'default'", "strategy_used": "TEXT DEFAULT 'standard'"},
}


def _ensure_demo_teacher() -> int:
    # 仅用于兼容升级前已有的本地演示数据。新用户仍通过注册获得独立空间。
    from app.core.security import hash_password

    with SessionLocal() as db:
        teacher = db.query(Teacher).filter(Teacher.username == "demo").first()
        if teacher:
            teacher.role = "admin"
            teacher.verification_status = "verified"
            db.commit()
            return teacher.id
        # 旧数据必须归属到一个教师空间，但线上不能再创建固定口令的管理员账号。
        # 新账号始终走注册流程；这个迁移账号只承接历史无归属记录。
        password_hash, salt = hash_password(secrets.token_urlsafe(32))
        teacher = Teacher(
            username="demo",
            display_name="演示老师",
            email=None,
            school="乡音智谱演示学校",
            password_hash=password_hash,
            password_salt=salt,
            role="admin",
            verification_status="verified",
        )
        db.add(teacher)
        db.commit()
        db.refresh(teacher)
        return teacher.id


def _upgrade_legacy_sqlite() -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables:
        return
    # IMPORTANT: upgrade columns before touching ORM models.  SQLAlchemy emits
    # every mapped Teacher column even for a query that filters only by
    # username.  Calling _ensure_demo_teacher first therefore breaks an older
    # database as soon as a newly added column (e.g. teachers.phone) is mapped.
    with engine.begin() as conn:
        for table, columns in ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            current_columns = {item["name"] for item in inspect(engine).get_columns(table)}
            for column, sql_type in columns.items():
                if column not in current_columns:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))

    # It is now safe to query Teacher through the ORM and obtain the owner for
    # legacy records that predate multi-user support.
    default_teacher_id = _ensure_demo_teacher()
    with engine.begin() as conn:
        for table, (column, sql_type) in TENANT_COLUMNS.items():
            if table not in existing_tables:
                continue
            current_columns = {item["name"] for item in inspect(engine).get_columns(table)}
            if column not in current_columns:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
            if column == "teacher_id":
                conn.execute(text(f'UPDATE "{table}" SET "{column}" = :teacher_id WHERE "{column}" IS NULL'), {"teacher_id": default_teacher_id})


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _upgrade_legacy_sqlite()
    _cleanup_expired_auth_data()


def _cleanup_expired_auth_data() -> None:
    """Drop unusable login sessions and one-time codes instead of retaining them indefinitely."""
    now = datetime.utcnow()
    with SessionLocal() as db:
        _clear_audio_job_inputs(db)
        db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
        db.execute(delete(VerificationCode).where(or_(VerificationCode.expires_at <= now, VerificationCode.consumed_at.is_not(None))))
        db.commit()


def _clear_audio_job_inputs(db) -> None:
    """Scrub old path-bearing payloads and clean inputs from long-interrupted tasks."""
    upload_root = Path(get_settings().upload_dir).resolve()
    stale_before = datetime.utcnow() - timedelta(hours=24)
    jobs = db.scalars(select(AudioAnalysisJob).where(
        AudioAnalysisJob.status.in_(("pending", "running")),
        AudioAnalysisJob.updated_at <= stale_before,
    )).all()
    for job in jobs:
        try:
            payload = json.loads(job.request_json or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        for key in ("recording_path", "reference_path"):
            raw_path = payload.get(key)
            if not raw_path:
                continue
            try:
                candidate = Path(raw_path).resolve()
                candidate.relative_to(upload_root)
                candidate.unlink(missing_ok=True)
            except (OSError, ValueError):
                continue
        job.status = "failed"
        job.stage = "任务超时，已清理临时输入"
        job.error_message = "任务超过 24 小时没有更新，未保存本次结果；请重新上传后重试。"
        job.request_json = "{}"
    db.execute(update(AudioAnalysisJob).where(
        AudioAnalysisJob.status.notin_(("pending", "running")),
        AudioAnalysisJob.request_json != "{}",
    ).values(request_json="{}"))
