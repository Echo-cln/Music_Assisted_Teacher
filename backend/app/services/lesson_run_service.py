"""授课计时、分段批注与恢复逻辑。"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def build_run_stages(timeline: list[dict]) -> list[dict]:
    stages = []
    for index, item in enumerate(timeline):
        try:
            minutes = max(1, min(90, int(item.get("minutes") or 1)))
        except (TypeError, ValueError):
            minutes = 1
        stages.append({
            "index": index,
            "stage": str(item.get("stage") or f"环节 {index + 1}")[:160],
            "planned_seconds": minutes * 60,
            "active_seconds": 0,
            "note": "",
            "status": "pending",
            "started_at": None,
            "ended_at": None,
        })
    return stages


def _stages(run) -> list[dict]:
    try:
        result = json.loads(run.stages_json or "[]")
    except (TypeError, json.JSONDecodeError):
        result = []
    return result if isinstance(result, list) else []


def _save_stages(run, stages: list[dict]) -> None:
    run.stages_json = json.dumps(stages, ensure_ascii=False)


def settle_lesson_run(run, until: datetime) -> None:
    """结算 active_since 到 until 的有效授课时间，不包含暂停区间。"""
    if run.status != "running" or not run.active_since:
        return
    seconds = max(0, int((until - run.active_since).total_seconds()))
    if not seconds:
        return
    stages = _stages(run)
    index = run.current_stage_index
    if 0 <= index < len(stages):
        stages[index]["active_seconds"] = int(stages[index].get("active_seconds") or 0) + seconds
        if not stages[index].get("started_at"):
            stages[index]["started_at"] = run.active_since.isoformat()
        _save_stages(run, stages)
    run.total_active_seconds = int(run.total_active_seconds or 0) + seconds
    run.active_since = until


def apply_lesson_run_event(run, action: str, now: datetime, stage_index: int | None = None,
                           note: str | None = None, reflection: str | None = None) -> None:
    stages = _stages(run)
    if run.status == "completed":
        raise ValueError("本次授课记录已结束")

    if action == "heartbeat":
        if run.status == "running":
            settle_lesson_run(run, now)
            run.last_heartbeat_at = now
        return
    if action == "pause":
        if run.status != "running":
            raise ValueError("只有计时中的授课可以暂停")
        settle_lesson_run(run, now)
        stages = _stages(run)
        run.status = "paused"
        run.paused_since = now
        run.active_since = None
        if 0 <= run.current_stage_index < len(stages):
            stages[run.current_stage_index]["status"] = "paused"
            _save_stages(run, stages)
        return
    if action == "resume":
        if run.status not in {"paused", "interrupted"}:
            raise ValueError("当前授课记录不需要继续计时")
        if run.status == "paused" and run.paused_since:
            run.total_paused_seconds = int(run.total_paused_seconds or 0) + max(0, int((now - run.paused_since).total_seconds()))
        run.paused_since = None
        run.status = "running"
        run.active_since = now
        run.last_heartbeat_at = now
        if 0 <= run.current_stage_index < len(stages):
            stages[run.current_stage_index]["status"] = "running"
            if not stages[run.current_stage_index].get("started_at"):
                stages[run.current_stage_index]["started_at"] = now.isoformat()
            _save_stages(run, stages)
        return
    if action in {"next", "previous"}:
        if run.status != "running":
            raise ValueError("请先继续计时，再切换授课环节")
        if not stages:
            raise ValueError("教案没有可计时的课堂环节")
        settle_lesson_run(run, now)
        stages = _stages(run)
        old_index = run.current_stage_index
        new_index = min(len(stages) - 1, old_index + 1) if action == "next" else max(0, old_index - 1)
        if new_index == old_index and action == "previous":
            run.active_since = now
            run.last_heartbeat_at = now
            return
        if action == "next":
            stages[old_index]["status"] = "completed"
            stages[old_index]["ended_at"] = now.isoformat()
        else:
            stages[old_index]["status"] = "pending"
        if action == "next" and old_index == len(stages) - 1:
            run.status = "completed"
            run.ended_at = now
            run.active_since = None
            _save_stages(run, stages)
            return
        run.current_stage_index = new_index
        stages[new_index]["status"] = "running"
        if not stages[new_index].get("started_at"):
            stages[new_index]["started_at"] = now.isoformat()
        run.active_since = now
        run.last_heartbeat_at = now
        _save_stages(run, stages)
        return
    if action == "finish":
        if run.status == "running":
            settle_lesson_run(run, now)
        elif run.status == "paused" and run.paused_since:
            run.total_paused_seconds = int(run.total_paused_seconds or 0) + max(0, int((now - run.paused_since).total_seconds()))
        stages = _stages(run)
        if 0 <= run.current_stage_index < len(stages):
            stages[run.current_stage_index]["status"] = "completed"
            stages[run.current_stage_index]["ended_at"] = now.isoformat()
        run.status = "completed"
        run.ended_at = now
        run.active_since = None
        run.paused_since = None
        _save_stages(run, stages)
        return
    if action == "note":
        index = run.current_stage_index if stage_index is None else stage_index
        if not 0 <= index < len(stages):
            raise ValueError("批注关联的环节不存在")
        stages[index]["note"] = (note or "").strip()
        stages[index]["note_updated_at"] = now.isoformat()
        _save_stages(run, stages)
        return
    if action == "reflection":
        run.reflection = (reflection or "").strip()
        return
    raise ValueError("不支持的授课记录操作")


def interrupt_stale_lesson_run(run, now: datetime, stale_seconds: int = 120) -> bool:
    if run.status != "running" or not run.last_heartbeat_at:
        return False
    if (now - run.last_heartbeat_at).total_seconds() <= stale_seconds:
        return False
    # 只计算最后一次心跳之前的活动时间，浏览器关闭后的间隔不算授课。
    settle_lesson_run(run, run.last_heartbeat_at)
    run.status = "interrupted"
    run.active_since = None
    stages = _stages(run)
    if 0 <= run.current_stage_index < len(stages):
        stages[run.current_stage_index]["status"] = "interrupted"
        _save_stages(run, stages)
    return True


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_lesson_run(run, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    stages = _stages(run)
    total_active = int(run.total_active_seconds or 0)
    total_paused = int(run.total_paused_seconds or 0)
    current_seconds = 0
    active_since = run.active_since
    if run.status == "running" and active_since:
        elapsed = max(0, int((now - active_since).total_seconds()))
        total_active += elapsed
        if 0 <= run.current_stage_index < len(stages):
            current_seconds = int(stages[run.current_stage_index].get("active_seconds") or 0) + elapsed
    elif 0 <= run.current_stage_index < len(stages):
        current_seconds = int(stages[run.current_stage_index].get("active_seconds") or 0)
    if run.status == "paused" and run.paused_since:
        total_paused += max(0, int((now - run.paused_since).total_seconds()))
    if 0 <= run.current_stage_index < len(stages):
        stages[run.current_stage_index]["active_seconds"] = current_seconds
    return {
        "id": run.id,
        "lesson_plan_id": run.lesson_plan_id,
        "mode": run.mode,
        "status": run.status,
        "snapshot": json.loads(run.plan_snapshot_json or "{}"),
        "stages": stages,
        "current_stage_index": run.current_stage_index,
        "current_stage_seconds": current_seconds,
        "total_active_seconds": total_active,
        "total_paused_seconds": total_paused,
        "reflection": run.reflection or "",
        "started_at": _utc_iso(run.started_at),
        "ended_at": _utc_iso(run.ended_at),
        "active_since": _utc_iso(active_since),
        "paused_since": _utc_iso(run.paused_since),
        "snapshot_at": _utc_iso(now),
    }
