from typing import Literal

from pydantic import BaseModel, Field


class NoteInput(BaseModel):
    pitch: int = Field(ge=24, le=108)
    start: float = Field(ge=0, le=3600)
    duration: float = Field(gt=0, le=30)
    velocity: int = Field(default=88, ge=1, le=127)


class ProjectCreate(BaseModel):
    title: str = Field(default="未命名编曲", min_length=1, max_length=160)
    tempo: int = Field(default=96, ge=40, le=220)
    style: str = Field(default="乡土抒情", min_length=1, max_length=50)
    melody: list[NoteInput] = Field(default_factory=list)


class ArrangeRequest(BaseModel):
    tempo: int = Field(default=96, ge=40, le=220)
    style: str = Field(default="乡土抒情", min_length=1, max_length=50)
    instruments: list[Literal["piano", "violin", "guzheng", "erhu", "drum"]] = Field(default_factory=lambda: ["piano", "guzheng", "drum"])
    melody: list[NoteInput] = Field(default_factory=list)

