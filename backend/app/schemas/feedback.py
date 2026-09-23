from typing import Any

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    lesson_plan_id: int
    overall_effect: str
    highlights: str = ""
    problems: str = ""
    improvement: str = ""
    analysis: dict[str, Any] = {}
