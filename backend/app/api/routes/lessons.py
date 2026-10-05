import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ClassProfile, LessonPlan, Song, Teacher
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
