import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAnalysis, ClassProfile, ClassroomRecord, Feedback, LessonPlan, Song, Teacher
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
    if payload.audio_analysis_id:
        analysis = db.scalar(select(AudioAnalysis).where(AudioAnalysis.id == payload.audio_analysis_id, AudioAnalysis.teacher_id == teacher.id))
        if not analysis:
            raise HTTPException(status_code=404, detail="音频分析记录不存在")
        if analysis.lesson_plan_id != plan.id:
            raise HTTPException(status_code=422, detail="所选音频分析未绑定当前教案，不能写入本课反馈")
    item = Feedback(
        teacher_id=teacher.id,
        classroom_record_id=record.id,
        overall_effect=payload.overall_effect,
        highlights=payload.highlights,
        problems=payload.problems,
        improvement=payload.improvement,
        audio_summary=payload.audio_summary,
        audio_analysis_id=payload.audio_analysis_id,
        analysis_json=json.dumps(payload.analysis, ensure_ascii=False),
    )
    record.status = "feedback_completed"
    profile = db.scalar(select(ClassProfile).where(ClassProfile.id == record.class_id, ClassProfile.teacher_id == teacher.id))
    if profile and payload.problems:
        profile.teacher_notes = f"{profile.teacher_notes}\n最近反馈：{payload.problems}".strip()
    db.add(item)
    db.commit()
    return {"id": item.id, "message": "反馈已归档并更新班级画像"}


@router.get("")
def list_feedback(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    rows = db.scalars(select(Feedback).where(Feedback.teacher_id == teacher.id).order_by(Feedback.created_at.desc())).all()
    output = []
    for item in rows:
        record = db.get(ClassroomRecord, item.classroom_record_id)
        plan = db.get(LessonPlan, record.lesson_plan_id) if record else None
        song = db.get(Song, plan.song_id) if plan else None
        analysis = json.loads(item.analysis_json or "{}")
        if plan and not analysis.get("goal_observations"):
            content = json.loads(plan.content_json or "{}")
            objectives = content.get("objective_evidence") or [
                {"objective": objective, "evidence": ""} for objective in content.get("objectives", [])
            ]
            analysis["goal_observations"] = [
                {"objective": entry.get("objective", ""), "evidence": entry.get("evidence", ""), "status": ""}
                for entry in objectives if entry.get("objective")
            ]
        output.append({
            "id": item.id, "lesson_plan_id": plan.id if plan else None,
            "lesson_title": plan.title if plan else "已删除教案",
            "song_name": song.name if song else "—",
            "overall_effect": item.overall_effect, "highlights": item.highlights,
            "problems": item.problems, "improvement": item.improvement,
            "audio_summary": item.audio_summary, "analysis": analysis,
            "audio_analysis_id": item.audio_analysis_id,
            "created_at": item.created_at.isoformat(timespec="seconds"),
        })
    return output

@router.put("/{feedback_id}")
def update_feedback(feedback_id: int, payload: FeedbackCreate, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    item = db.scalar(select(Feedback).where(Feedback.id == feedback_id, Feedback.teacher_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="反馈记录不存在")
    record = db.get(ClassroomRecord, item.classroom_record_id)
    plan = db.scalar(select(LessonPlan).where(LessonPlan.id == payload.lesson_plan_id, LessonPlan.teacher_id == teacher.id))
    if not record or not plan or record.lesson_plan_id != plan.id:
        raise HTTPException(status_code=422, detail="反馈所属教案无效")
    if payload.audio_analysis_id:
        analysis = db.scalar(select(AudioAnalysis).where(AudioAnalysis.id == payload.audio_analysis_id, AudioAnalysis.teacher_id == teacher.id, AudioAnalysis.lesson_plan_id == plan.id))
        if not analysis:
            raise HTTPException(status_code=422, detail="音频分析记录未绑定当前教案")
    for key in ("overall_effect", "highlights", "problems", "improvement", "audio_summary", "audio_analysis_id"):
        setattr(item, key, getattr(payload, key))
    item.analysis_json = json.dumps(payload.analysis, ensure_ascii=False)
    db.commit()
    return {"id": item.id, "message": "反馈已更新"}
