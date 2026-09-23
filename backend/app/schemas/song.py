from pydantic import BaseModel

from app.schemas.common import ORMModel


class SongRead(ORMModel):
    id: int
    name: str
    region: str
    province: str
    mood: str
    mode: str
    grade: str
    source: str
    song_type: str
    range_note: str
    range_score: int
    rhythm_score: int
    dialect_score: int
    difficulty: str
    original_audio_path: str | None


class RecommendRequest(BaseModel):
    region: str
    class_id: int
    limit: int = 3


class SongRecommendation(SongRead):
    match_score: int
    reason: str
