from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import ClassProfile, GenerationJob, Song
from app.repositories.song_repository import SongRepository
from app.schemas.lesson import LessonGenerateRequest
from app.services.lesson_service import build_base_preview, serialize_preview, stream_preview

logger = logging.getLogger(__name__)


def _steps(active_index: int, failed: bool = False) -> list[dict]:
    labels = [
        "读取班级画像",
        "检索歌曲与教学知识库",
        "生成可用教案骨架",
        "AI优化教师话术与课堂活动",
        "校验教案结构与课时",
        "生成完成",
    ]
    result = []
    for index, label in enumerate(labels):
        if failed and index == active_index:
            state = "error"
        elif index < active_index:
            state = "done"
        elif index == active_index:
            state = "running"
        else:
            state = "pending"
        result.append({"label": label, "state": state})
    return result


def _set_job(job: GenerationJob, *, status: str, stage: str, progress: int, step_index: int, error: str = "") -> None:
    job.status = status
    job.stage = stage
    job.progress = progress
    job.steps_json = json.dumps(_steps(step_index, failed=status == "failed"), ensure_ascii=False)
    job.error_message = error
    job.updated_at = datetime.utcnow()


def create_generation_job(teacher_id: int, payload: LessonGenerateRequest) -> dict:
    with SessionLocal() as db:
        song = SongRepository(db, teacher_id).get(payload.song_id)
        if not song:
            raise ValueError("歌曲不存在")
        profile = None
        if payload.class_id:
            profile = db.scalar(
                select(ClassProfile).where(
                    ClassProfile.id == payload.class_id,
                    ClassProfile.teacher_id == teacher_id,
                )
            )
            if not profile:
                raise ValueError("班级不存在")
        base = build_base_preview(
            db,
            song,
            profile,
            payload.duration_minutes,
            payload.activity_preference,
            payload.teacher_requirements,
            teacher_id,
        )
        preview = serialize_preview(song, profile, payload.duration_minutes, base, "rules")
        job = GenerationJob(
            id=str(uuid.uuid4()),
            teacher_id=teacher_id,
            status="pending",
            stage="已完成教案骨架，准备连接模型服务",
            progress=35,
            request_json=payload.model_dump_json(),
            preview_json=json.dumps(preview, ensure_ascii=False),
            result_json="{}",
            steps_json=json.dumps(_steps(2), ensure_ascii=False),
            strategy_used=payload.generation_strategy,
            model_used=get_settings().ai_fast_model if payload.generation_strategy == "fast" else get_settings().ai_model,
        )
        db.add(job)
        db.commit()
        job_id = job.id

    thread = threading.Thread(target=_run_generation_job, args=(job_id,), daemon=True)
    thread.start()
    return get_generation_job(teacher_id, job_id)


def _run_generation_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        if not job:
            return
        logger.info("generation_job_started job_id=%s strategy=%s model=%s", job.id, job.strategy_used, job.model_used)
        try:
            payload = LessonGenerateRequest.model_validate_json(job.request_json)
            song = SongRepository(db, job.teacher_id).get(payload.song_id)
            profile = None
            if payload.class_id:
                profile = db.scalar(
                    select(ClassProfile).where(
                        ClassProfile.id == payload.class_id,
                        ClassProfile.teacher_id == job.teacher_id,
                    )
                )
            if not song or (payload.class_id and not profile):
                raise ValueError("生成所需歌曲或班级已不存在")

            _set_job(job, status="running", stage="正在连接模型服务", progress=38, step_index=3)
            db.commit()

            completed = None
            received_chunks = 0
            received_chars = 0
            for kind, value in stream_preview(
                db,
                song,
                profile,
                payload.duration_minutes,
                payload.activity_preference,
                payload.teacher_requirements,
                job.teacher_id,
                payload.generation_strategy,
            ):
                db.refresh(job)
                if job.status == "cancelled":
                    return
                if kind == "start":
                    _set_job(job, status="running", stage="模型已接受请求，等待首段正文", progress=42, step_index=3)
                    db.commit()
                elif kind == "delta":
                    # 每个真正收到的 SSE 正文分片都推进 1%，最多到 88%。
                    # 这不是按时间猜测；无正文时不会假装进度已经完成。
                    received_chunks += 1
                    received_chars += len(str(value))
                    next_progress = min(88, 42 + received_chunks)
                    if next_progress > int(job.progress or 0):
                        _set_job(
                            job,
                            status="running",
                            stage=f"正在接收模型正文（已收到 {received_chars} 字符）",
                            progress=next_progress,
                            step_index=3,
                        )
                        db.commit()
                if kind == "complete":
                    completed = value
            if completed is None:
                raise RuntimeError("AI 未返回完整教案")

            _set_job(job, status="running", stage="模型正文接收完成，正在校验教案结构与课时", progress=92, step_index=4)
            db.commit()
            preview = serialize_preview(
                song,
                profile,
                payload.duration_minutes,
                completed["content"],
                completed["generation_mode"],
            )
            job.result_json = json.dumps(preview, ensure_ascii=False)
            job.status = "completed"
            job.stage = "教案已生成"
            job.progress = 100
            job.steps_json = json.dumps(
                [{"label": item["label"], "state": "done"} for item in _steps(5)], ensure_ascii=False
            )
            job.updated_at = datetime.utcnow()
            db.commit()
            logger.info("generation_job_completed job_id=%s", job.id)
        except Exception as exc:  # noqa: BLE001 - 后台任务必须持久化错误而不是让线程静默退出
            logger.exception("generation_job_failed job_id=%s error=%s", job_id, exc)
            db.rollback()
            job = db.get(GenerationJob, job_id)
            if not job:
                return
            _set_job(
                job,
                status="failed",
                stage="生成失败",
                progress=max(job.progress or 0, 55),
                step_index=3,
                error=str(exc)[:800],
            )
            db.commit()


def serialize_job(job: GenerationJob) -> dict:
    preview = json.loads(job.preview_json or "{}")
    result = json.loads(job.result_json or "{}")
    ended_at = job.updated_at if job.status in {"completed", "failed"} else datetime.utcnow()
    elapsed_seconds = max(0, int((ended_at - job.created_at).total_seconds()))
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "steps": json.loads(job.steps_json or "[]"),
        "preview": preview,
        "result": result or None,
        "error_message": job.error_message,
        "model_used": getattr(job, "model_used", "default"),
        "strategy_used": getattr(job, "strategy_used", "standard"),
        "elapsed_seconds": elapsed_seconds,
        "created_at": job.created_at.isoformat(timespec="seconds"),
        "updated_at": job.updated_at.isoformat(timespec="seconds"),
    }


def get_generation_job(teacher_id: int, job_id: str) -> dict:
    with SessionLocal() as db:
        job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id, GenerationJob.teacher_id == teacher_id))
        if not job:
            raise LookupError("生成任务不存在")
        return serialize_job(job)


def list_generation_jobs(teacher_id: int, limit: int = 10) -> list[dict]:
    with SessionLocal() as db:
        jobs = db.scalars(
            select(GenerationJob)
            .where(GenerationJob.teacher_id == teacher_id)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
        ).all()
        return [serialize_job(job) for job in jobs]


def cancel_generation_job(teacher_id: int, job_id: str) -> None:
    with SessionLocal() as db:
        job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id, GenerationJob.teacher_id == teacher_id))
        if not job:
            raise LookupError("生成任务不存在")
        if job.status not in {"pending", "running"}:
            raise ValueError("该生成任务已经结束，无法取消")
        _set_job(job, status="cancelled", stage="已取消，不会保存生成结果", progress=job.progress or 0, step_index=3)
        job.result_json = "{}"
        db.commit()
