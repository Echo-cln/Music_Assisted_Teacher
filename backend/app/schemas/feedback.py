from typing import Any

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    lesson_plan_id: int
    audio_analysis_id: int | None = None
    overall_effect: str
    highlights: str = ""
    problems: str = ""
    improvement: str = ""
    audio_summary: str = ""
    analysis: dict[str, Any] = {}
