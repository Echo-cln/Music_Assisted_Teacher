from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ClassProfile, Teacher
from app.schemas.class_profile import ClassProfileCreate, ClassProfileRead, ClassProfileUpdate

router = APIRouter(prefix="/classes", tags=["班级画像"])


@router.get("", response_model=list[ClassProfileRead])
def list_classes(
    q: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    statement = select(ClassProfile).where(ClassProfile.teacher_id == teacher.id)
    if q:
        keyword = f"%{q.strip()}%"
        statement = statement.where(or_(
            ClassProfile.name.ilike(keyword),
            ClassProfile.province.ilike(keyword),
            ClassProfile.teacher_notes.ilike(keyword),
            ClassProfile.common_problems.ilike(keyword),
        ))
    return list(
        db.scalars(
            statement.order_by(ClassProfile.grade, ClassProfile.name)
        ).all()
    )


@router.post("", response_model=ClassProfileRead, status_code=status.HTTP_201_CREATED)
def create_class(
    payload: ClassProfileCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    item = ClassProfile(teacher_id=teacher.id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="你的班级中已存在同名班级")
    db.refresh(item)
    return item


@router.put("/{class_id}", response_model=ClassProfileRead)
def update_class(
    class_id: int,
    payload: ClassProfileUpdate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    item = db.scalar(select(ClassProfile).where(ClassProfile.id == class_id, ClassProfile.teacher_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="班级不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="你的班级中已存在同名班级")
    db.refresh(item)
    return item


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    item = db.scalar(select(ClassProfile).where(ClassProfile.id == class_id, ClassProfile.teacher_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="班级不存在")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
