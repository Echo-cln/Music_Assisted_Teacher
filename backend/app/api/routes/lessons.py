import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAnalysis, ClassroomRecord, ClassProfile, LessonPlan, Song, Teacher
from app.repositories.song_repository import SongRepository
from app.schemas.lesson import (
    LessonAdjustRequest,
    LessonGenerateRequest,
    LessonPlanRead,
    LessonPreviewAdjustRequest,
    LessonPreviewRead,
    LessonSaveRequest,
)
from app.services.lesson_service import (
    save_preview,
    serialize_plan,
    serialize_preview,
    stream_preview,
    stream_preview_adjustment,
)

router = APIRouter(prefix="/lessons", tags=["教案"])
logger = logging.getLogger(__name__)


def _profile_for_teacher(db: Session, teacher_id: int, class_id: int | None):
    if not class_id:
        return None
    return db.scalar(select(ClassProfile).where(ClassProfile.id == class_id, ClassProfile.teacher_id == teacher_id))


@router.get("", response_model=list[LessonPlanRead])
def list_lessons(
    q: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    statement = (
        select(LessonPlan)
        .options(joinedload(LessonPlan.song), joinedload(LessonPlan.class_profile))
        .where(LessonPlan.teacher_id == teacher.id)
    )
    if q:
        keyword = f"%{q.strip()}%"
        statement = statement.outerjoin(LessonPlan.song).outerjoin(LessonPlan.class_profile).where(or_(
            LessonPlan.title.ilike(keyword),
            Song.name.ilike(keyword),
            ClassProfile.name.ilike(keyword),
        ))
    statement = statement.order_by(LessonPlan.created_at.desc())
    return [serialize_plan(item) for item in db.scalars(statement).unique().all()]


@router.post("/generate", response_model=LessonPreviewRead)
def generate(
    payload: LessonGenerateRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    song = SongRepository(db, teacher.id).get(payload.song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    profile = _profile_for_teacher(db, teacher.id, payload.class_id)
    if payload.class_id and not profile:
        raise HTTPException(status_code=404, detail="班级不存在")
    complete = list(
        stream_preview(
            db,
            song,
            profile,
            payload.duration_minutes,
            payload.activity_preference,
            payload.teacher_requirements,
            teacher.id,
            payload.generation_strategy,
        )
    )[-1][1]
    return serialize_preview(song, profile, payload.duration_minutes, complete["content"], complete["generation_mode"])


@router.post("/generate/stream")
def generate_stream(
    payload: LessonGenerateRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    song = SongRepository(db, teacher.id).get(payload.song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    profile = _profile_for_teacher(db, teacher.id, payload.class_id)
    if payload.class_id and not profile:
        raise HTTPException(status_code=404, detail="班级不存在")

    def events():
        try:
            for kind, value in stream_preview(
                db,
                song,
                profile,
                payload.duration_minutes,
                payload.activity_preference,
                payload.teacher_requirements,
                teacher.id,
                payload.generation_strategy,
            ):
                if kind == "complete":
                    data = {
                        "type": kind,
                        "preview": serialize_preview(
                            song, profile, payload.duration_minutes, value["content"], value["generation_mode"]
                        ),
                    }
                elif kind == "start":
                    data = {"type": kind, "mode": value}
                else:
                    data = {"type": kind, "text": value}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception:
            db.rollback()
            data = {"type": "error", "message": "教案生成失败，请检查模型配置或稍后重试；未保存任何教案。"}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/preview/adjust/stream")
def adjust_preview_stream(
    payload: LessonPreviewAdjustRequest,
    teacher: Teacher = Depends(get_current_teacher),
):
    del teacher

    def events():
        try:
            for kind, value in stream_preview_adjustment(payload.content, payload.instruction):
                if kind == "complete":
                    data = {
                        "type": kind,
                        "preview": {"content": value["content"], "generation_mode": value["generation_mode"]},
                    }
                elif kind == "start":
                    data = {"type": kind, "mode": value}
                else:
                    data = {"type": kind, "text": value}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception:
            data = {"type": "error", "message": "教案调整失败，请稍后重试；原预览内容没有被保存。"}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/save", response_model=LessonPlanRead)
def save(
    payload: LessonSaveRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    song = SongRepository(db, teacher.id).get(payload.song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    profile = _profile_for_teacher(db, teacher.id, payload.class_id)
    if payload.class_id and not profile:
        raise HTTPException(status_code=404, detail="班级不存在")
    try:
        plan = save_preview(
            db,
            song,
            profile,
            payload.duration_minutes,
            payload.teacher_requirements,
            payload.content,
            payload.generation_mode,
            teacher.id,
        )
    except ValueError as exc:
        # 预览在浏览器里停留较久时，内容可能被手工改坏；这属于可修复的
        # 请求问题，应直接告诉前端而不是以“请求失败”掩盖。
        db.rollback()
        raise HTTPException(status_code=422, detail=f"教案内容无法保存：{exc}") from exc
    except Exception as exc:
        db.rollback()
        error_id = uuid.uuid4().hex[:10]
        logger.exception("lesson_save_failed error_id=%s teacher_id=%s song_id=%s", error_id, teacher.id, payload.song_id)
        raise HTTPException(
            status_code=500,
            detail=f"保存教案时数据库写入失败（错误编号 {error_id}）。请保留当前预览后重试；若持续失败，请复制该编号给技术支持。",
        ) from exc
    db.refresh(plan, attribute_names=["song", "class_profile"])
    return serialize_plan(plan)


@router.post("/{lesson_id}/adjust", response_model=LessonPlanRead)
def adjust(
    lesson_id: int,
    payload: LessonAdjustRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    plan = db.scalar(
        select(LessonPlan)
        .options(joinedload(LessonPlan.song), joinedload(LessonPlan.class_profile))
        .where(LessonPlan.id == lesson_id, LessonPlan.teacher_id == teacher.id)
    )
    if not plan:
        raise HTTPException(status_code=404, detail="教案不存在")
    content = json.loads(plan.content_json)
    content["teacher_requirements"] = payload.instruction
    content.setdefault("adjustment_history", []).append(payload.instruction)
    plan.teacher_requirements = payload.instruction
    plan.content_json = json.dumps(content, ensure_ascii=False)
    db.commit()
    db.refresh(plan)
    return serialize_plan(plan)


@router.put("/{lesson_id}", response_model=LessonPlanRead)
def update_lesson(
    lesson_id: int,
    payload: LessonSaveRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    plan = db.scalar(
        select(LessonPlan)
        .options(joinedload(LessonPlan.song), joinedload(LessonPlan.class_profile))
        .where(LessonPlan.id == lesson_id, LessonPlan.teacher_id == teacher.id)
    )
    if not plan:
        raise HTTPException(status_code=404, detail="教案不存在")
    # 编辑时保持归属信息不变，只更新教师确认后的正文与元信息。
    plan.title = str(payload.content.get("title") or plan.title)
    plan.teacher_requirements = payload.teacher_requirements
    plan.content_json = json.dumps(payload.content, ensure_ascii=False)
    plan.generation_mode = payload.generation_mode
    db.commit()
    db.refresh(plan)
    return serialize_plan(plan)


@router.delete("/{lesson_id}")
def delete_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    """删除单条教案档案；保留音频分析，并拒绝删除仍有课堂记录的教案。"""
    plan = db.scalar(select(LessonPlan).where(
        LessonPlan.id == lesson_id,
        LessonPlan.teacher_id == teacher.id,
    ))
    if not plan:
        raise HTTPException(status_code=404, detail="教案不存在")

    has_classroom_record = db.scalar(select(ClassroomRecord.id).where(
        ClassroomRecord.lesson_plan_id == lesson_id,
        ClassroomRecord.teacher_id == teacher.id,
    ).limit(1))
    if has_classroom_record:
        raise HTTPException(
            status_code=409,
            detail="该教案已有课堂记录或反馈。为保留这些记录，请先在教学档案中处理关联课堂记录后再删除。",
        )

    try:
        # 音频分析是独立档案：解除教案关联后保留分析结果和音频文件。
        db.execute(update(AudioAnalysis).where(
            AudioAnalysis.lesson_plan_id == lesson_id,
            AudioAnalysis.teacher_id == teacher.id,
        ).values(lesson_plan_id=None))
        db.delete(plan)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("lesson_delete_failed lesson_id=%s teacher_id=%s", lesson_id, teacher.id)
        raise HTTPException(status_code=500, detail="删除教案档案失败，数据库已回滚。") from exc

    return {"ok": True, "message": "教案档案已删除；关联的音频分析记录与文件已保留。"}
