from typing import Any

from pydantic import BaseModel, Field


class LessonGenerateRequest(BaseModel):
    song_id: int
    class_id: int | None = None
    duration_minutes: int = Field(default=40, ge=20, le=90)
    activity_preference: str = "互动与分组合作"
    teacher_requirements: str = ""


class LessonPlanRead(BaseModel):
    id: int
    title: str
    class_id: int | None
    class_name: str
    song_id: int
    song_name: str
    duration_minutes: int
    generation_mode: str
    content: dict[str, Any]
    created_at: str
    is_saved: bool = True


class LessonPreviewRead(BaseModel):
    class_id: int | None
    class_name: str
    song_id: int
    song_name: str
    duration_minutes: int
    generation_mode: str
    content: dict[str, Any]
    is_saved: bool = False


class LessonSaveRequest(BaseModel):
    song_id: int
    class_id: int | None = None
    duration_minutes: int = Field(default=40, ge=20, le=90)
    teacher_requirements: str = ""
    generation_mode: str = "ai"
    content: dict[str, Any]


class LessonPreviewAdjustRequest(BaseModel):
    content: dict[str, Any]
    instruction: str = Field(min_length=2, max_length=1000)


class LessonAdjustRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=1000)
