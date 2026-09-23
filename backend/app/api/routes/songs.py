from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ClassProfile, Teacher
from app.repositories.song_repository import SongRepository
from app.schemas.song import RecommendRequest, SongRead, SongRecommendation
from app.services.recommendation_service import recommend_songs

router = APIRouter(prefix="/songs", tags=["歌曲"])


@router.get("", response_model=list[SongRead])
def list_songs(
    region: str | None = None,
    province: str | None = None,
    grade: str | None = None,
    q: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    repository = SongRepository(db, teacher.id)
    return repository.search_by_name(q) if q else repository.list_songs(region, province, grade)


@router.post("/recommend", response_model=list[SongRecommendation])
def recommend(
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    profile = db.scalar(select(ClassProfile).where(ClassProfile.id == payload.class_id, ClassProfile.teacher_id == teacher.id))
    if not profile:
        raise HTTPException(status_code=404, detail="班级不存在")
    items = recommend_songs(db, payload.region, profile, payload.limit, teacher.id)
    return [
        SongRecommendation(
            **SongRead.model_validate(item["song"]).model_dump(),
            match_score=item["match_score"],
            reason=item["reason"],
        )
        for item in items
    ]
