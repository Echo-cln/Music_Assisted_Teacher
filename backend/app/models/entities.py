from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    school: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(128))
    password_salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (UniqueConstraint("region", "source_row", name="uq_song_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(30), index=True)
    province: Mapped[str] = mapped_column(String(30), index=True)
    mood: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str] = mapped_column(String(30), index=True)
    source: Mapped[str] = mapped_column(String(120))
    song_type: Mapped[str] = mapped_column(String(80))
    range_note: Mapped[str] = mapped_column(String(180))
    range_score: Mapped[int] = mapped_column(Integer)
    rhythm_score: Mapped[int] = mapped_column(Integer)
    dialect_score: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(20))
    original_audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accompaniment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    score_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TeachingGame(Base):
    __tablename__ = "teaching_games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120), index=True)
    personality: Mapped[str] = mapped_column(String(120))
    grade: Mapped[str] = mapped_column(String(50))
    match_condition: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text)


class MusicTheory(Base):
    __tablename__ = "music_theory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80))
    term: Mapped[str] = mapped_column(String(120), index=True)
    lower_grade_script: Mapped[str] = mapped_column(Text)
    upper_grade_script: Mapped[str] = mapped_column(Text)


class TeachingMistake(Base):
    __tablename__ = "teaching_mistakes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    problem: Mapped[str] = mapped_column(Text)
    correction: Mapped[str] = mapped_column(Text)


class ClassProfile(Base):
    __tablename__ = "class_profiles"
    __table_args__ = (UniqueConstraint("teacher_id", "name", name="uq_teacher_class_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    grade: Mapped[int] = mapped_column(Integer)
    student_count: Mapped[int] = mapped_column(Integer)
    province: Mapped[str] = mapped_column(String(30))
    learning_level: Mapped[str] = mapped_column(String(80))
    activity_level: Mapped[str] = mapped_column(String(80))
    cooperation: Mapped[str] = mapped_column(String(100))
    pitch_level: Mapped[str] = mapped_column(String(120))
    rhythm_level: Mapped[str] = mapped_column(String(120))
    theory_level: Mapped[str] = mapped_column(String(120))
    preferred_method: Mapped[str] = mapped_column(String(120))
    common_problems: Mapped[str] = mapped_column(Text, default="")
    teacher_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lesson_plans: Mapped[list["LessonPlan"]] = relationship(back_populates="class_profile")


class LessonPlan(Base):
    __tablename__ = "lesson_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    class_id: Mapped[int | None] = mapped_column(ForeignKey("class_profiles.id"), nullable=True, index=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    teacher_requirements: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[str] = mapped_column(Text)
    generation_mode: Mapped[str] = mapped_column(String(30), default="rules")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    class_profile: Mapped[ClassProfile | None] = relationship(back_populates="lesson_plans")
    song: Mapped[Song] = relationship()


class ClassroomRecord(Base):
    __tablename__ = "classroom_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("class_profiles.id"), index=True)
    lesson_plan_id: Mapped[int] = mapped_column(ForeignKey("lesson_plans.id"), index=True)
    taught_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    classroom_record_id: Mapped[int] = mapped_column(ForeignKey("classroom_records.id"), index=True)
    overall_effect: Mapped[str] = mapped_column(String(30))
    highlights: Mapped[str] = mapped_column(Text, default="")
    problems: Mapped[str] = mapped_column(Text, default="")
    improvement: Mapped[str] = mapped_column(Text, default="")
    analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=True, index=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), index=True)
    classroom_record_id: Mapped[int | None] = mapped_column(ForeignKey("classroom_records.id"), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(30))
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(160), default="等待开始")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    request_json: Mapped[str] = mapped_column(Text)
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    # Phase4: record the actual engine configuration used for reproducibility
    model_used: Mapped[str] = mapped_column(String(120), default="default")
    strategy_used: Mapped[str] = mapped_column(String(50), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIModelConfig(Base):
    __tablename__ = "ai_model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120))
    strategy: Mapped[str] = mapped_column(String(50), default="standard")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
