import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAnalysis, ClassroomRecord, ClassProfile, LessonPlan, LessonPlanRevision, LessonRun, Song, Teacher
from app.repositories.song_repository import SongRepository
from app.schemas.lesson import (
    LessonAdjustRequest,
    LessonGenerateRequest,
    LessonPlanRead,
    LessonPreviewAdjustRequest,
    LessonPreviewRead,
    LessonSaveRequest,
    LessonRunStart,
    LessonRunEvent,
    LessonRunRevisionRequest,
)
from app.services.lesson_run_service import apply_lesson_run_event, build_run_stages, interrupt_stale_lesson_run, serialize_lesson_run
from app.services.lesson_service import (
    save_preview,
    serialize_plan,
    serialize_preview,
    stream_preview,
    stream_preview_adjustment,
)

router = APIRouter(prefix="/lessons", tags=["教案"])
logger = logging.getLogger(__name__)




def _run_snapshot(plan: LessonPlan) -> dict:
    content = json.loads(plan.content_json or "{}")
    return {
        "id": plan.id,
        "title": plan.title,
        "class_id": plan.class_id,
        "class_name": plan.class_profile.name if plan.class_profile else "通用班级",
        "song_id": plan.song_id,
        "song_name": plan.song.name if plan.song else "",
        "duration_minutes": plan.duration_minutes,
        "generation_mode": plan.generation_mode,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "content": content,
    }


def _get_owned_run(db: Session, teacher_id: int, run_id: int) -> LessonRun:
    run = db.scalar(select(LessonRun).where(LessonRun.id == run_id, LessonRun.teacher_id == teacher_id))
    if not run:
        raise HTTPException(status_code=404, detail="授课记录不存在")
    if interrupt_stale_lesson_run(run, datetime.utcnow()):
        db.commit()
        db.refresh(run)
    return run


@router.post("/{lesson_id}/runs")
def start_lesson_run(
    lesson_id: int,
    payload: LessonRunStart,
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
    now = datetime.utcnow()
    existing_run = db.scalar(
        select(LessonRun)
        .where(
            LessonRun.teacher_id == teacher.id,
            LessonRun.lesson_plan_id == plan.id,
            LessonRun.status.in_(["running", "paused", "interrupted"]),
        )
        .order_by(LessonRun.started_at.desc())
    )
    if existing_run:
        if interrupt_stale_lesson_run(existing_run, now):
            db.commit()
        raise HTTPException(
            status_code=409,
            detail="这份教案已有未结束的授课记录。请先接续、结束或查看原记录，再开始新的授课。",
        )
    content = json.loads(plan.content_json or "{}")
    stages = build_run_stages(content.get("timeline") or [])
    if not stages:
        raise HTTPException(status_code=422, detail="这份教案没有课堂流程，暂时无法开启授课计时。")
    stages[0]["status"] = "running"
    stages[0]["started_at"] = now.isoformat()
    run = LessonRun(
        teacher_id=teacher.id,
        lesson_plan_id=plan.id,
        mode=payload.mode,
        status="running",
        plan_snapshot_json=json.dumps(_run_snapshot(plan), ensure_ascii=False),
        stages_json=json.dumps(stages, ensure_ascii=False),
        current_stage_index=0,
        total_active_seconds=0,
        total_paused_seconds=0,
        reflection="",
        active_since=now,
        paused_since=None,
        last_heartbeat_at=now,
        started_at=now,
        ended_at=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return serialize_lesson_run(run, now)


@router.get("/{lesson_id}/runs")
def list_lesson_runs(
    lesson_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    plan_exists = db.scalar(select(LessonPlan.id).where(
        LessonPlan.id == lesson_id, LessonPlan.teacher_id == teacher.id
    ))
    if not plan_exists:
        raise HTTPException(status_code=404, detail="教案不存在")
    runs = list(db.scalars(
        select(LessonRun)
        .where(LessonRun.lesson_plan_id == lesson_id, LessonRun.teacher_id == teacher.id)
        .order_by(LessonRun.started_at.desc())
    ).all())
    now = datetime.utcnow()
    changed = False
    for run in runs:
        changed = interrupt_stale_lesson_run(run, now) or changed
    if changed:
        db.commit()
    return [serialize_lesson_run(run, now) for run in runs]


@router.get("/runs/{run_id}")
def get_lesson_run(
    run_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    return serialize_lesson_run(_get_owned_run(db, teacher.id, run_id))


@router.post("/runs/{run_id}/events")
def lesson_run_event(
    run_id: int,
    payload: LessonRunEvent,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    run = _get_owned_run(db, teacher.id, run_id)
    try:
        apply_lesson_run_event(
            run,
            payload.action,
            datetime.utcnow(),
            stage_index=payload.stage_index,
            note=payload.note,
            reflection=payload.reflection,
        )
        db.commit()
        db.refresh(run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_lesson_run(run)


@router.post("/runs/{run_id}/revise")
def revise_lesson_from_run(
    run_id: int,
    payload: LessonRunRevisionRequest,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    run = _get_owned_run(db, teacher.id, run_id)
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="请先结束授课并完成计时，再从复盘修订教案。")
    plan = db.scalar(select(LessonPlan).where(
        LessonPlan.id == run.lesson_plan_id, LessonPlan.teacher_id == teacher.id
    ))
    if not plan:
        raise HTTPException(status_code=404, detail="对应教案已不存在")
    content = payload.content
    if not isinstance(content.get("timeline"), list) or not content["timeline"]:
        raise HTTPException(status_code=422, detail="修订内容必须保留课堂流程。")
    snapshot = json.loads(run.plan_snapshot_json or "{}")
    original_timeline = (snapshot.get("content") or {}).get("timeline") or []
    if json.loads(plan.content_json or "{}") != (snapshot.get("content") or {}):
        raise HTTPException(status_code=409, detail="授课后教案主档已发生变化；本次批注仍保留，请先打开当前教案合并后再保存。")
    if len(content["timeline"]) != len(original_timeline):
        raise HTTPException(status_code=422, detail="修订后的课堂环节数量与本次授课记录不一致。")

    latest = db.scalar(select(func.max(LessonPlanRevision.revision_number)).where(
        LessonPlanRevision.lesson_plan_id == plan.id,
        LessonPlanRevision.teacher_id == teacher.id,
    )) or 0
    revision = LessonPlanRevision(
        teacher_id=teacher.id,
        lesson_plan_id=plan.id,
        source_run_id=run.id,
        revision_number=latest + 1,
        content_json=plan.content_json,
    )
    plan.title = str(content.get("title") or plan.title)[:200]
    plan.teacher_requirements = str(content.get("teacher_requirements") or plan.teacher_requirements)
    plan.content_json = json.dumps(content, ensure_ascii=False)
    db.add(revision)
    try:
        db.commit()
        db.refresh(plan)
        db.refresh(revision)
    except Exception as exc:
        db.rollback()
        error_id = uuid.uuid4().hex[:10]
        logger.exception("lesson_run_revision_failed run_id=%s error_id=%s", run.id, error_id)
        raise HTTPException(status_code=500, detail=f"保存教案修订失败（错误编号 {error_id}）。") from exc
    return {"plan": serialize_plan(plan), "revision_number": revision.revision_number, "revision_id": revision.id}


@router.get("/{lesson_id}/revisions")
def list_lesson_revisions(
    lesson_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    plan_exists = db.scalar(select(LessonPlan.id).where(
        LessonPlan.id == lesson_id, LessonPlan.teacher_id == teacher.id
    ))
    if not plan_exists:
        raise HTTPException(status_code=404, detail="教案不存在")
    revisions = db.scalars(
        select(LessonPlanRevision)
        .where(LessonPlanRevision.lesson_plan_id == lesson_id, LessonPlanRevision.teacher_id == teacher.id)
        .order_by(LessonPlanRevision.revision_number.desc())
    ).all()
    return [{
        "id": item.id,
        "revision_number": item.revision_number,
        "source_run_id": item.source_run_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "content": json.loads(item.content_json or "{}"),
    } for item in revisions]


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
    """删除单条教案档案；保留音频分析，并拒绝删除存在课堂/授课历史的教案。"""
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

    has_lesson_run = db.scalar(select(LessonRun.id).where(
        LessonRun.lesson_plan_id == lesson_id,
        LessonRun.teacher_id == teacher.id,
    ).limit(1))
    if has_lesson_run:
        raise HTTPException(
            status_code=409,
            detail="该教案已有授课计时、批注或复盘历史。为保留课堂过程记录，暂不能删除这份教案。",
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
