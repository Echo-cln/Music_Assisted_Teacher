from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ClassProfile, MusicTheory, Song, Teacher, TeachingGame, TeachingMistake

router = APIRouter(tags=["系统"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/stats")
def stats(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)) -> dict:
    def visible_count(model):
        return db.scalar(
            select(func.count())
            .select_from(model)
            .where(or_(model.owner_teacher_id.is_(None), model.owner_teacher_id == teacher.id))
        )

    return {
        "songs": visible_count(Song),
        "games": visible_count(TeachingGame),
        "theory": visible_count(MusicTheory),
        "mistakes": visible_count(TeachingMistake),
        "classes": db.scalar(
            select(func.count()).select_from(ClassProfile).where(ClassProfile.teacher_id == teacher.id)
        ),
    }
