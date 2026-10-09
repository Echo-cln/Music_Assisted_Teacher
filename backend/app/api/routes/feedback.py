import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAnalysis, AudioAsset, ClassProfile, ClassroomRecord, Feedback, LessonPlan, Song, Teacher
from app.schemas.feedback import FeedbackCreate

router = APIRouter(prefix="/feedback", tags=["课后反馈"])


def _audio_link_mismatch(
    analysis: AudioAnalysis | None,
    plan: LessonPlan | None,
    record: ClassroomRecord | None,
    recording: AudioAsset | None = None,
) -> bool:
    """Treat a legacy or incomplete association as untrusted until it matches this lesson."""
    return bool(
        not analysis or not plan or not record
        or plan.class_id != record.class_id
        or analysis.song_id != plan.song_id
        or analysis.lesson_plan_id not in (None, plan.id)
        or analysis.classroom_record_id not in (None, record.id)
        or not recording
        or (recording and (
            recording.song_id != plan.song_id
            or recording.classroom_record_id not in (None, record.id)
        ))
    )


def _validate_audio_link(analysis: AudioAnalysis, plan: LessonPlan, record: ClassroomRecord, recording: AudioAsset | None = None) -> None:
    if plan.class_id != record.class_id:
        raise HTTPException(status_code=422, detail="当前教案与课堂记录所属班级不一致，暂不能关联音频")
    if analysis.song_id != plan.song_id:
        raise HTTPException(status_code=422, detail="音频分析对应的歌曲与当前教案不一致，请重新选择同一首歌的分析记录")
    if analysis.lesson_plan_id not in (None, plan.id):
        raise HTTPException(status_code=422, detail="这条音频分析已关联另一份教案，请先解除原关联")
    if analysis.classroom_record_id not in (None, record.id):
        raise HTTPException(status_code=422, detail="这条音频分析属于另一节课堂记录，不能关联到当前反馈")
    if recording:
        if recording.song_id != plan.song_id:
            raise HTTPException(status_code=422, detail="音频文件登记的歌曲与当前教案不一致，不能关联")
        if recording.classroom_record_id not in (None, record.id):
            raise HTTPException(status_code=422, detail="音频文件属于另一节课堂记录，不能关联到当前反馈")


def _recording_for_analysis(db: Session, analysis: AudioAnalysis, teacher_id: int) -> AudioAsset | None:
    return db.scalar(select(AudioAsset).where(
        AudioAsset.id == analysis.recording_asset_id,
        AudioAsset.teacher_id == teacher_id,
    ))


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
        recording = _recording_for_analysis(db, analysis, teacher.id)
        if not recording:
            raise HTTPException(status_code=404, detail="音频分析对应的录音文件不存在")
        _validate_audio_link(analysis, plan, record, recording)
        if analysis.lesson_plan_id is None:
            analysis.lesson_plan_id = plan.id
        if analysis.classroom_record_id is None:
            analysis.classroom_record_id = record.id
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
        linked_analysis = db.scalar(select(AudioAnalysis).where(
            AudioAnalysis.id == item.audio_analysis_id,
            AudioAnalysis.teacher_id == teacher.id,
        )) if item.audio_analysis_id else None
        linked_recording = _recording_for_analysis(db, linked_analysis, teacher.id) if linked_analysis else None
        audio_link_mismatch = bool(item.audio_analysis_id and _audio_link_mismatch(linked_analysis, plan, record, linked_recording))
        try:
            analysis = json.loads(item.analysis_json or "{}")
        except (TypeError, json.JSONDecodeError):
            analysis = {}
        if not isinstance(analysis, dict):
            analysis = {}
        if plan and not analysis.get("goal_observations"):
            try:
                content = json.loads(plan.content_json or "{}")
            except (TypeError, json.JSONDecodeError):
                content = {}
            if not isinstance(content, dict):
                content = {}
            objectives = content.get("objective_evidence") or [
                {"objective": objective, "evidence": ""} for objective in content.get("objectives", [])
            ]
            analysis["goal_observations"] = [
                {"objective": entry.get("objective", ""), "evidence": entry.get("evidence", ""), "status": ""}
                for entry in objectives if entry.get("objective")
            ]
        safe_analysis = {
            "goal_observations": analysis.get("goal_observations", []),
            "class_observations": analysis.get("class_observations", {}),
        }
        if linked_analysis and not audio_link_mismatch:
            try:
                analysis_result = json.loads(linked_analysis.result_json or "{}")
            except (TypeError, json.JSONDecodeError):
                analysis_result = {}
            if isinstance(analysis_result, dict):
                safe_analysis["analysis_mode_label"] = analysis_result.get("analysis_mode_label", "课堂音频分析")
        output.append({
            "id": item.id, "lesson_plan_id": plan.id if plan else None,
            "lesson_title": plan.title if plan else "已删除教案",
            "class_id": record.class_id if record else None,
            "class_name": db.get(ClassProfile, record.class_id).name if record and db.get(ClassProfile, record.class_id) else "—",
            "song_name": song.name if song else "—",
            "overall_effect": item.overall_effect, "highlights": item.highlights,
            "problems": item.problems, "improvement": item.improvement,
            "audio_summary": item.audio_summary, "analysis": safe_analysis,
            "audio_analysis_id": None if audio_link_mismatch else item.audio_analysis_id,
            "audio_link_mismatch": audio_link_mismatch,
            "audio_analysis_song_name": db.get(Song, linked_analysis.song_id).name if linked_analysis and db.get(Song, linked_analysis.song_id) else None,
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
        analysis = db.scalar(select(AudioAnalysis).where(
            AudioAnalysis.id == payload.audio_analysis_id,
            AudioAnalysis.teacher_id == teacher.id,
        ))
        if not analysis:
            raise HTTPException(status_code=404, detail="音频分析记录不存在")
        recording = _recording_for_analysis(db, analysis, teacher.id)
        if not recording:
            raise HTTPException(status_code=404, detail="音频分析对应的录音文件不存在")
        _validate_audio_link(analysis, plan, record, recording)
        if analysis.lesson_plan_id is None:
            analysis.lesson_plan_id = plan.id
        if analysis.classroom_record_id is None:
            analysis.classroom_record_id = record.id
    for key in ("overall_effect", "highlights", "problems", "improvement", "audio_summary", "audio_analysis_id"):
        setattr(item, key, getattr(payload, key))
    item.analysis_json = json.dumps(payload.analysis, ensure_ascii=False)
    db.commit()
    return {"id": item.id, "message": "反馈已更新"}


@router.delete("/{feedback_id}")
def delete_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """仅删除选中的课堂反馈，保留课堂记录、教案和关联的音频分析。"""
    item = db.scalar(select(Feedback).where(
        Feedback.id == feedback_id,
        Feedback.teacher_id == teacher.id,
    ))
    if not item:
        raise HTTPException(status_code=404, detail="课堂反馈记录不存在")
    try:
        db.delete(item)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="删除课堂反馈失败，数据库已回滚。") from exc
    return {"ok": True, "message": "课堂反馈已删除；音频分析与教案记录已保留。"}
