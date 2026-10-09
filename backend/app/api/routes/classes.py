import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAnalysis, ClassProfile, ClassroomRecord, Feedback, LessonPlan, Teacher
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


@router.get("/{class_id}/trends")
def class_learning_trends(
    class_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """Return only persisted classroom feedback and linked audio evidence for this teacher's class."""
    profile = db.scalar(select(ClassProfile).where(
        ClassProfile.id == class_id,
        ClassProfile.teacher_id == teacher.id,
    ))
    if not profile:
        raise HTTPException(status_code=404, detail="班级不存在")

    rows = db.execute(
        select(Feedback, ClassroomRecord, LessonPlan)
        .join(ClassroomRecord, Feedback.classroom_record_id == ClassroomRecord.id)
        .join(LessonPlan, ClassroomRecord.lesson_plan_id == LessonPlan.id)
        .where(
            Feedback.teacher_id == teacher.id,
            ClassroomRecord.teacher_id == teacher.id,
            ClassroomRecord.class_id == class_id,
            LessonPlan.teacher_id == teacher.id,
        )
        .order_by(Feedback.created_at.desc())
        .limit(12)
    ).all()

    points = []
    for feedback, record, plan in reversed(rows):
        try:
            observation = json.loads(feedback.analysis_json or "{}")
        except (TypeError, json.JSONDecodeError):
            observation = {}
        class_observations = observation.get("class_observations") or {}
        linked_audio = None
        if feedback.audio_analysis_id:
            audio = db.scalar(select(AudioAnalysis).where(
                AudioAnalysis.id == feedback.audio_analysis_id,
                AudioAnalysis.teacher_id == teacher.id,
            ))
            if audio:
                try:
                    result = json.loads(audio.result_json or "{}")
                except (TypeError, json.JSONDecodeError):
                    result = {}
                scores = result.get("scores") or {}
                linked_audio = {
                    "pitch_stability": scores.get("pitch_stability"),
                    "rhythm_regularness": scores.get("rhythm_regularness"),
                    "source": "已关联音频分析记录",
                }
        observed_at = feedback.created_at or record.taught_at or record.created_at
        points.append({
            "date": observed_at.isoformat(timespec="seconds") if observed_at else "",
            "lesson_title": plan.title,
            "overall_effect": feedback.overall_effect,
            "participation": class_observations.get("participation"),
            "cooperation": class_observations.get("cooperation"),
            "pitch_stability": linked_audio["pitch_stability"] if linked_audio else None,
            "rhythm_regularness": linked_audio["rhythm_regularness"] if linked_audio else None,
            "goal_observations": observation.get("goal_observations") or [],
            "source": "教师课后反馈" + (" + 音频分析" if linked_audio else ""),
        })

    return {
        "class_id": profile.id,
        "class_name": profile.name,
        "updated_at": points[-1]["date"] if points else (profile.updated_at.isoformat(timespec="seconds") if profile.updated_at else None),
        "record_count": len(points),
        "points": points,
    }
