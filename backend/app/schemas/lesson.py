from typing import Any, Literal

from pydantic import BaseModel, Field


class LessonDialogueMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class LessonDialogueReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    history: list[LessonDialogueMessage] = Field(default_factory=list, max_length=12)
    context: dict[str, Any] = Field(default_factory=dict)


class LessonBriefExtractRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=2000)
    class_id: int | None = None


class LessonGenerateRequest(BaseModel):
    song_id: int
    class_id: int | None = None
    duration_minutes: int = Field(default=40, ge=20, le=90)
    activity_preference: str = "互动与分组合作"
    teacher_requirements: str = ""
    generation_strategy: str = Field(default="deep", pattern="^(fast|deep)$")


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



class LessonRunStart(BaseModel):
    mode: Literal["actual", "simulation"] = "simulation"


class LessonRunEvent(BaseModel):
    action: Literal["pause", "resume", "previous", "next", "finish", "heartbeat", "note", "reflection"]
    stage_index: int | None = Field(default=None, ge=0, le=30)
    note: str | None = Field(default=None, max_length=3000)
    reflection: str | None = Field(default=None, max_length=5000)


class LessonRunRevisionRequest(BaseModel):
    content: dict[str, Any]
