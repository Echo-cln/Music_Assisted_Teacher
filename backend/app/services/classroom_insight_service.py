"""课堂音频的“证据约束模型解读”。

模型不接替音高、起音和响度计算，也不能把声学指标夸大成“学生跑调”这一类
事实判断。它只把已经计算出的时段、证据和本课教学信息改写成教师可执行的
课堂动作；任何时间段必须来自声学分析的输入。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings
from app.services.llm.factory import get_adapter

logger = logging.getLogger(__name__)


def _json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _valid_insights(value: dict[str, Any], known_times: set[str]) -> dict[str, Any] | None:
    summary = str(value.get("summary") or "").strip()
    raw_items = value.get("priorities")
    if not summary or not isinstance(raw_items, list):
        return None
    priorities = []
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            continue
        time = str(item.get("time") or "").strip()
        headline = str(item.get("headline") or "").strip()
        interpretation = str(item.get("interpretation") or "").strip()
        action = str(item.get("action") or "").strip()
        # 模型不得创造不存在的时间段，也不得把空泛建议塞进页面。
        if time not in known_times or not headline or not interpretation or not action:
            continue
        priorities.append({"time": time, "headline": headline[:70], "interpretation": interpretation[:260], "action": action[:300]})
    if not priorities:
        return None
    return {"summary": summary[:360], "priorities": priorities}


def build_classroom_model_insight(*, song: Any, sections: list[dict], scores: dict, classroom_evidence: dict, lesson_content: dict | None = None) -> dict:
    """返回可显示的模型解读状态，失败不阻断音频分析记录保存。"""
    settings = get_settings()
    if not settings.classroom_insight_enabled:
        return {"status": "disabled", "message": "课堂模型解读当前未启用；下方保留声学证据。"}
    if not (settings.ai_fast_api_key or settings.ai_api_key):
        return {"status": "not_configured", "message": "未配置可用模型 API Key；下方仅显示可复核的声学证据。"}

    evidence = [{
        "time": row.get("time"), "focus": row.get("focus"), "evidence": row.get("evidence"),
        "score": row.get("pitch_stability"), "action_seed": row.get("note"),
    } for row in sections]
    lesson = lesson_content or {}
    payload = {
        "song": {"name": getattr(song, "name", ""), "mood": getattr(song, "mood", ""), "type": getattr(song, "song_type", ""), "grade": getattr(song, "grade", "")},
        "lesson_focus": {"key_points": lesson.get("key_points", ""), "difficulties": lesson.get("difficulties", ""), "objectives": lesson.get("objectives", [])},
        "overall_scores": scores,
        "limitations": classroom_evidence.get("limitations", []),
        "segments": evidence,
    }
    prompt = """你是小学音乐教研员。请只依据下方 JSON 的声学证据，写一份短的课堂复盘解读。
不得声称知道歌词、学生身份、具体音高是否唱准，不能添加任何未给出的时间段或数据。
优先选 1–3 个需要本课处理的时间段；每条都要给出教师下一步可直接执行的动作。
只输出 JSON：{\"summary\":\"...\",\"priorities\":[{\"time\":\"必须完全来自segments.time\",\"headline\":\"...\",\"interpretation\":\"解释提供的指标意味着什么，不夸大\",\"action\":\"具体教师组织动作\"}]}。"""
    try:
        # 课堂解读优先调用明确配置的快速模型。若只配置了深度模型，必须走
        # 深度模型对应的 base URL，不能把其 API Key 错发到快速模型端点。
        strategy = "fast" if settings.ai_fast_api_key else "deep"
        parts = list(get_adapter(generation_strategy=strategy).stream(
            [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            generation_strategy=strategy,
            max_tokens=min(2400, max(700, int(settings.classroom_insight_max_tokens))),
        ))
        parsed = _json_object("".join(parts))
        validated = _valid_insights(parsed or {}, {str(row.get("time")) for row in sections})
        if validated:
            return {"status": "ready", "model": settings.ai_fast_model if strategy == "fast" else settings.ai_model, **validated}
        return {"status": "invalid", "message": "模型没有返回可核验的分段解读；下方保留声学证据。"}
    except Exception as exc:  # 音频记录不能因可选的教学解读而整条失败。
        logger.warning("classroom_model_insight_failed: %s", exc)
        return {"status": "unavailable", "message": "本次模型解读未完成；下方仍是可复核的声学证据。"}
