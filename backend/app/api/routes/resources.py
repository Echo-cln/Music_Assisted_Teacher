"""教师可扩展的教学资源库：系统资源只读，个人资源支持增删改查。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import MusicTheory, Song, Teacher, TeachingGame, TeachingMistake

router = APIRouter(prefix="/resources", tags=["教学资源库"])
ResourceKind = Literal["songs", "games", "theory", "mistakes"]
TABLES = {"songs": Song, "games": TeachingGame, "theory": MusicTheory, "mistakes": TeachingMistake}


class SongEdit(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=30)
    province: str = Field(min_length=1, max_length=30)
    mood: str = Field(min_length=1, max_length=80)
    mode: str = Field(min_length=1, max_length=80)
    grade: str = Field(min_length=1, max_length=30)
    source: str = Field(min_length=1, max_length=120)
    song_type: str = Field(min_length=1, max_length=80)
    range_note: str = Field(min_length=1, max_length=180)
    range_score: int = Field(ge=0, le=10)
    rhythm_score: int = Field(ge=0, le=10)
    dialect_score: int = Field(ge=0, le=10)
    difficulty: str = Field(min_length=1, max_length=20)


class GameEdit(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    personality: str = Field(min_length=1, max_length=120)
    grade: str = Field(min_length=1, max_length=50)
    match_condition: str = Field(min_length=1)
    instructions: str = Field(min_length=1)


class TheoryEdit(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    term: str = Field(min_length=1, max_length=120)
    lower_grade_script: str = Field(min_length=1)
    upper_grade_script: str = Field(min_length=1)


class MistakeEdit(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    problem: str = Field(min_length=1)
    correction: str = Field(min_length=1)


FIELDS = {
    "songs": tuple(SongEdit.model_fields),
    "games": tuple(GameEdit.model_fields),
    "theory": tuple(TheoryEdit.model_fields),
    "mistakes": tuple(MistakeEdit.model_fields),
}
SCHEMAS = {"songs": SongEdit, "games": GameEdit, "theory": TheoryEdit, "mistakes": MistakeEdit}


def as_dict(kind: ResourceKind, row: Song | TeachingGame | MusicTheory | TeachingMistake, teacher_id: int) -> dict:
    return {
        "id": row.id,
        **{field: getattr(row, field) for field in FIELDS[kind]},
        "scope": "mine" if row.owner_teacher_id == teacher_id else "system",
        "editable": row.owner_teacher_id == teacher_id,
    }


@router.get("/{kind}")
def list_resources(
    kind: ResourceKind,
    q: str = Query(default="", max_length=80),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    model = TABLES[kind]
    statement = select(model).where(or_(model.owner_teacher_id.is_(None), model.owner_teacher_id == teacher.id)).order_by(
        model.owner_teacher_id.desc().nullslast(), model.id
    )
    if q:
        search_field = {
            "songs": Song.name,
            "games": TeachingGame.name,
            "theory": MusicTheory.term,
            "mistakes": TeachingMistake.problem,
        }[kind]
        statement = statement.where(search_field.contains(q))
    return [as_dict(kind, row, teacher.id) for row in db.scalars(statement.limit(600)).all()]


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_resource(
    kind: ResourceKind,
    payload: dict,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    validated = SCHEMAS[kind].model_validate(payload)
    values = validated.model_dump()
    if kind == "songs":
        current_min = db.scalar(select(func.min(Song.source_row)).where(Song.region == values["region"]))
        values["source_row"] = min(-1, (current_min or 0) - 1)
    row = TABLES[kind](owner_teacher_id=teacher.id, **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_dict(kind, row, teacher.id)


@router.put("/{kind}/{resource_id}")
def update_resource(
    kind: ResourceKind,
    resource_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    model = TABLES[kind]
    row = db.scalar(select(model).where(model.id == resource_id, model.owner_teacher_id == teacher.id))
    if row is None:
        if db.get(model, resource_id):
            raise HTTPException(status_code=403, detail="系统内置资源不可直接修改，请先复制为“我的资源”")
        raise HTTPException(status_code=404, detail="资源不存在")
    validated = SCHEMAS[kind].model_validate(payload)
    for field, value in validated.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return as_dict(kind, row, teacher.id)


@router.delete("/{kind}/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(
    kind: ResourceKind,
    resource_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    model = TABLES[kind]
    row = db.scalar(select(model).where(model.id == resource_id, model.owner_teacher_id == teacher.id))
    if row is None:
        raise HTTPException(status_code=404, detail="只能删除自己的资源")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
