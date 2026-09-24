from sqlalchemy import inspect, text

from app.db.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401
from app.models.entities import Teacher


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
        password_hash, salt = hash_password("demo123456")
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
