import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ClassProfile, ClassroomRecord, Feedback, LessonPlan, Teacher
from app.schemas.feedback import FeedbackCreate

router = APIRouter(prefix="/feedback", tags=["课后反馈"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    plan = db.scalar(select(LessonPlan).where(LessonPlan.id == payload.lesson_plan_id, LessonPlan.teacher_id == teacher.id))
    if not plan:
        raise HTTPException(status_code=404, detail="教案不存在")
    record = db.scalar(
        select(ClassroomRecord).where(
            ClassroomRecord.lesson_plan_id == payload.lesson_plan_id,
            ClassroomRecord.teacher_id == teacher.id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="课堂记录不存在")
    item = Feedback(
        teacher_id=teacher.id,
        classroom_record_id=record.id,
        overall_effect=payload.overall_effect,
        highlights=payload.highlights,
        problems=payload.problems,
        improvement=payload.improvement,
        analysis_json=json.dumps(payload.analysis, ensure_ascii=False),
    )
    record.status = "feedback_completed"
    profile = db.scalar(select(ClassProfile).where(ClassProfile.id == record.class_id, ClassProfile.teacher_id == teacher.id))
    if profile and payload.problems:
        profile.teacher_notes = f"{profile.teacher_notes}\n最近反馈：{payload.problems}".strip()
    db.add(item)
    db.commit()
    return {"id": item.id, "message": "反馈已归档并更新班级画像"}
