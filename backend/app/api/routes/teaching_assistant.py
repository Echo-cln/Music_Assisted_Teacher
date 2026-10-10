from __future__ import annotations

import json
import logging
import re
import ast
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import (
    ArrangementProject, AssistantConversation, AudioAnalysis, AudioAsset, ClassProfile,
    ClassroomRecord, Feedback, InstrumentSoundfont, LessonPlan, LessonPlanRevision,
    MusicTheory, Song, Teacher, TeachingGame, TeachingMistake,
)
from app.services.ai_provider import _naturalize_dialogue_answer, reply_to_lesson_dialogue
from app.services.recommendation_service import recommend_songs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teaching-assistant", tags=["教学助手"])

STOP_WORDS = {
    "帮我", "请问", "想要", "一下", "看看", "查看", "找到", "之前", "历史",
    "教案", "课堂", "记录", "这个", "那个", "我们", "有没有", "怎么", "如何",
    "根据", "内容", "相关", "所有", "一个", "一下", "进行", "修改", "调整",
    "班级", "老师", "学生", "想", "要", "找", "查", "说", "本课", "本节",
}
DOMAIN_TERMS = (
    "音准", "节奏", "合作", "课堂反馈", "班级画像", "教案", "歌曲", "民歌", "古筝",
    "小提琴", "二胡", "吉他", "非洲鼓", "音频分析", "编曲工程", "音乐游戏", "乐理",
    "易错纠正", "课堂参与", "设备不足", "无投影", "音域", "节拍", "模唱", "节奏接龙",
)


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=100)
    context: dict[str, Any] = Field(default_factory=dict)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    context: dict[str, Any] | None = None


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _owned_conversation(db: Session, conversation_id: int, teacher_id: int) -> AssistantConversation:
    row = db.scalar(select(AssistantConversation).where(
        AssistantConversation.id == conversation_id,
        AssistantConversation.teacher_id == teacher_id,
    ))
    if not row:
        raise HTTPException(status_code=404, detail="这段对话不存在或已删除")
    return row


def _json(raw: str | None, fallback):
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _mapping(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(raw)
            if isinstance(value, dict):
                return value
        except (ValueError, SyntaxError, json.JSONDecodeError):
            pass
    return {}


def _plain(value: Any, limit: int = 260) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text in {"{}", "[]", "None", "null", "未填写", "—"}:
        return ""
    if text.startswith(("{", "[")) and text.endswith(("}", "]")):
        parsed = _mapping(text)
        if not parsed:
            return ""
        useful = []
        for key in ("summary", "teacher_requirements", "requirements", "activity_preference", "equipment_constraints", "class_name", "song_name"):
            item = parsed.get(key)
            if isinstance(item, list):
                item = "、".join(str(part) for part in item if not isinstance(part, (dict, list)))
            clean = re.sub(r"\s+", " ", str(item or "")).strip()
            if clean:
                useful.append(clean)
        text = "；".join(useful)
        if not text:
            return ""
    return text[:limit]


def _lesson_preview(plan: LessonPlan, song: Song, profile: ClassProfile | None) -> str:
    content = _mapping(plan.content_json)
    requirements = _mapping(plan.teacher_requirements)
    summary = _plain(content.get("summary") or content.get("overview"))
    if not summary and requirements:
        parts = []
        for key, label in (("difficulty", "难度"), ("range_note", "音域"), ("teacher_requirements", "教学要求"), ("requirements", "教学要求")):
            value = _plain(requirements.get(key), 100)
            if value:
                parts.append(f"{label}{value}")
        summary = "；".join(parts)
    if not summary:
        summary = _plain(plan.teacher_requirements)
    details = [f"歌曲：《{song.name}》", f"班级：{profile.name if profile else '未指定'}", f"课时：{plan.duration_minutes}分钟"]
    if summary:
        details.append(f"备课要点：{summary}")
    return "；".join(details)


def _goal_observations(raw: Any) -> str:
    payload = _mapping(raw)
    goals = payload.get("goal_observations") or payload.get("objectives") or []
    readable = []
    if isinstance(goals, list):
        for goal in goals[:6]:
            if isinstance(goal, dict):
                objective = _plain(goal.get("objective") or goal.get("goal") or goal.get("name"), 100)
                status = _plain(goal.get("status") or goal.get("observation"), 60)
                if objective or status:
                    readable.append(f"{objective or '课堂目标'}：{status or '已记录'}")
            else:
                value = _plain(goal, 120)
                if value:
                    readable.append(value)
    return "；".join(readable)


def _instrument_names(raw: Any) -> str:
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
    if isinstance(value, dict):
        value = value.get("instruments") or value.get("presets") or value.get("names") or []
    if isinstance(value, list):
        names = []
        for item in value:
            raw_name = (item.get("name") or item.get("instrument") or item.get("preset")) if isinstance(item, dict) else item
            name = _plain(raw_name, 60)
            if name and name not in names:
                names.append(name)
        return "、".join(names[:8])
    return _plain(value, 150)


def _feedback_detail(feedback: Feedback, record: ClassroomRecord, audio_link_valid: bool = True, audio_song_name: str | None = None) -> str:
    parts = [f"日期：{str(record.taught_at or feedback.created_at)[:19]}"]
    fields = [("课堂亮点", feedback.highlights), ("存在问题", feedback.problems), ("下次改进", feedback.improvement)]
    if audio_link_valid:
        fields.append(("音频分析摘要", feedback.audio_summary))
    elif feedback.audio_analysis_id:
        parts.append(f"音频关联异常：关联分析（《{audio_song_name or '未知歌曲'}》）与本课的歌曲、教案或课堂记录不匹配，未将其作为本课证据")
    for label, value in fields:
        text = _plain(value, 220)
        if text:
            parts.append(f"{label}：{text}")
    goals = _goal_observations(feedback.analysis_json)
    if goals:
        parts.append(f"目标观察：{goals}")
    return "；".join(parts)


def _analysis_detail(raw_result: Any, method_version: str = "") -> str:
    """Turn stored analysis JSON into a short, readable note; never expose raw payloads."""
    result = _mapping(raw_result)
    acoustic = result.get("acoustic") if isinstance(result.get("acoustic"), dict) else result
    if not isinstance(acoustic, dict):
        acoustic = {}
    scores = acoustic.get("scores") if isinstance(acoustic.get("scores"), dict) else {}
    labels = {
        "pitch_stability": "音高稳定", "rhythm_regularness": "节拍稳定",
        "dynamics": "力度层次", "clarity": "录音清晰度",
        "voice_usable_ratio": "人声可用度",
    }
    parts = []
    mode = _plain(result.get("analysis_mode_label") or result.get("analysis_mode") or method_version, 80)
    if mode:
        parts.append(f"分析方式：{mode}")
    visible = [f"{labels.get(key, key)} {_plain(value, 24)}分" for key, value in scores.items() if _plain(value, 24)]
    if visible:
        parts.append("指标：" + "、".join(visible[:4]))
    suggestions = result.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = result.get("model_insight", {}).get("suggestions", []) if isinstance(result.get("model_insight"), dict) else []
    advice = [_plain(item, 100) for item in suggestions[:2] if _plain(item, 100)] if isinstance(suggestions, list) else []
    if advice:
        parts.append("建议：" + "；".join(advice))
    return "；".join(parts) or "已保存分析记录；请打开音频分析页面查看完整结果。"


def _resource_detail(label: str, row: Any) -> str:
    if label == "歌曲资源":
        fields = (("地区", row.region), ("适用年级", row.grade), ("情绪", row.mood),
                  ("类型", row.song_type), ("难度", row.difficulty), ("音域", row.range_note))
    elif label == "音乐游戏":
        fields = (("适用年级", row.grade), ("活动特点", row.personality), ("适用情境", row.match_condition), ("玩法", row.instructions))
    elif label == "乐理资源":
        fields = (("分类", row.category), ("内容", row.lower_grade_script), ("进阶说明", row.upper_grade_script))
    else:
        fields = (("问题类型", row.category), ("常见问题", row.problem), ("纠正建议", row.correction))
    return "；".join(f"{key}：{text}" for key, value in fields if (text := _plain(value, 220)))


def _present(row: AssistantConversation, include_messages: bool = False) -> dict:
    result = {
        "id": row.id,
        "title": row.title,
        "context": _json(row.context_json, {}),
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else None,
    }
    if include_messages:
        messages = _json(row.messages_json, [])
        clean_messages = []
        if isinstance(messages, list):
            for raw in messages[-200:]:
                if not isinstance(raw, dict) or raw.get("role") not in {"user", "assistant"}:
                    continue
                item = {key: raw.get(key) for key in ("role", "created_at") if raw.get(key) is not None}
                item["content"] = str(raw.get("content") or "")
                if item["role"] == "assistant":
                    item["content"] = _naturalize_dialogue_answer(item["content"])
                    suggestions = raw.get("suggestions")
                    if isinstance(suggestions, list):
                        safe_suggestions = []
                        for suggestion in suggestions[:6]:
                            if isinstance(suggestion, str):
                                label = _plain(suggestion, 70)
                                if label:
                                    safe_suggestions.append({"label": label, "message": label})
                            elif isinstance(suggestion, dict):
                                label = _plain(suggestion.get("label"), 70)
                                message = _plain(suggestion.get("message"), 180)
                                class_id = suggestion.get("class_id")
                                if label and message:
                                    item_suggestion = {"label": label, "message": message}
                                    if isinstance(class_id, int) and class_id > 0:
                                        item_suggestion["class_id"] = class_id
                                    conversation_id = suggestion.get("conversation_id")
                                    if isinstance(conversation_id, int) and conversation_id > 0:
                                        item_suggestion["conversation_id"] = conversation_id
                                    action = suggestion.get("action")
                                    if action in {"open_conversation", "confirm_class_change", "cancel_class_change"}:
                                        item_suggestion["action"] = action
                                    safe_suggestions.append(item_suggestion)
                        if safe_suggestions:
                            item["suggestions"] = safe_suggestions
                    sources = raw.get("sources")
                    if isinstance(sources, list):
                        safe_sources = []
                        for source in sources[:8]:
                            if not isinstance(source, dict):
                                continue
                            label = _plain(source.get("label"), 100)
                            kind = _plain(source.get("kind"), 40)
                            if not label or not kind:
                                continue
                            safe_sources.append({
                                "kind": kind, "label": label,
                                "detail": _plain(source.get("detail"), 260),
                                "updated_at": _plain(source.get("updated_at"), 40),
                                "route": source.get("route") if source.get("route") in {"lessons", "feedback", "audio", "resources", "classes", "workbench", "teachingAssistant"} else None,
                                "id": source.get("id") if kind in {"历史对话", "已引用的历史对话"} and isinstance(source.get("id"), int) else None,
                            })
                        if safe_sources:
                            item["sources"] = safe_sources
                    actions = raw.get("actions")
                    if isinstance(actions, list):
                        safe_actions = []
                        for action in actions[:3]:
                            if not isinstance(action, dict):
                                continue
                            action_type = action.get("type")
                            if action_type == "open_lesson_planner":
                                safe_actions.append({
                                    "type": action_type,
                                    "label": _plain(action.get("label"), 60) or "带入教案助手",
                                    "song_id": action.get("song_id") if isinstance(action.get("song_id"), int) else None,
                                    "song_name": _plain(action.get("song_name"), 80),
                                })
                            elif action_type in {"open_feedback_form", "open_feedback_archive"}:
                                safe_actions.append({
                                    "type": action_type,
                                    "label": _plain(action.get("label"), 60) or ("打开课堂反馈页" if action_type == "open_feedback_form" else "查看已有反馈"),
                                    "class_id": action.get("class_id") if isinstance(action.get("class_id"), int) else None,
                                    "lesson_id": action.get("lesson_id") if isinstance(action.get("lesson_id"), int) else None,
                                })
                        if safe_actions:
                            item["actions"] = safe_actions
                clean_messages.append(item)
        result["messages"] = clean_messages
    return result


def _terms(query: str) -> list[str]:
    text = query or ""
    tokens: list[str] = [match.strip() for match in re.findall(r"《([^》]{1,40})》", text)]
    tokens.extend(term for term in DOMAIN_TERMS if term in text)
    tokens.extend(re.findall(r"[A-Za-z0-9]{2,}", text))
    cleaned = text
    for phrase in sorted(STOP_WORDS, key=len, reverse=True):
        cleaned = cleaned.replace(phrase, " ")
    chunks = re.findall(r"[\u4e00-\u9fff]{2,}", cleaned)
    for chunk in chunks:
        if len(chunk) <= 10 and chunk not in STOP_WORDS:
            tokens.append(chunk)
        # Chinese often arrives without spaces; overlapping 2–5 character
        # fragments let a natural sentence still find an exact song/resource name.
        for width in range(min(5, len(chunk)), 1, -1):
            tokens.extend(chunk[index:index + width] for index in range(len(chunk) - width + 1))
    seen: list[str] = []
    for value in tokens:
        if value not in STOP_WORDS and len(value) >= 2 and value not in seen:
            seen.append(value)
    # Keep SQL predicates bounded; specific titles and known domain terms come first.
    return seen[:24]


def _matches(columns: list, terms: list[str]):
    if not terms:
        return None
    return or_(*(column.ilike(f"%{term}%") for column in columns for term in terms))


def _citation(kind: str, label: str, detail: str, record_id: int, route: str, updated_at=None) -> dict:
    return {
        "kind": kind, "label": label, "detail": detail[:700], "id": record_id,
        "route": route,
        "updated_at": updated_at.isoformat(timespec="seconds") if updated_at else None,
    }


def _conversation_excerpt(raw_messages: Any, terms: list[str]) -> str:
    messages = raw_messages if isinstance(raw_messages, list) else []
    safe = [item for item in messages if isinstance(item, dict) and item.get("role") in {"user", "assistant"}]
    if not safe:
        return ""
    needle = [term.lower() for term in terms if len(term) >= 2]
    for index in range(len(safe) - 1, -1, -1):
        item = safe[index]
        content = _plain(item.get("content"), 500)
        if not content:
            continue
        if not needle or any(term in content.lower() for term in needle):
            # Include the adjacent answer when possible so a cited conversation has context.
            pair = [item]
            if index + 1 < len(safe) and safe[index + 1].get("role") == "assistant":
                pair.append(safe[index + 1])
            return "；".join(
                f"{'教师' if part.get('role') == 'user' else '助手'}：{_plain(part.get('content'), 220)}"
                for part in pair
            )[:520]
    return ""


def _retrieve(db: Session, teacher_id: int, message: str, context: dict, conversation_id: int | None = None) -> list[dict]:
    terms = _terms(message)
    class_id = context.get("class_id")
    owned_profiles = db.scalars(select(ClassProfile).where(ClassProfile.teacher_id == teacher_id)).all()
    if class_id:
        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="班级信息无效，请重新选择班级")
        profile = next((item for item in owned_profiles if item.id == class_id), None)
        if not profile:
            raise HTTPException(status_code=404, detail="当前班级不存在或无权访问")
    else:
        # If the teacher names one of their classes, scope this turn to that class.
        named_profiles = [item for item in owned_profiles if item.name and item.name in message]
        if len(named_profiles) == 1:
            class_id = named_profiles[0].id
    context_song_id = None
    if context.get("song_id"):
        context_song = db.scalar(select(Song).where(
            Song.id == int(context["song_id"]),
            or_(Song.owner_teacher_id.is_(None), Song.owner_teacher_id == teacher_id),
        ))
        context_song_id = context_song.id if context_song else None
    # A named song or an entry from a lesson/feedback page scopes audio evidence
    # to that song; otherwise broad Chinese substring matches can mix recordings.
    if not context_song_id:
        visible_songs = db.scalars(select(Song).where(
            or_(Song.owner_teacher_id.is_(None), Song.owner_teacher_id == teacher_id)
        ).limit(500)).all()
        named_songs = [song for song in visible_songs if song.name and song.name in message]
        if len(named_songs) == 1:
            context_song_id = named_songs[0].id
    records: list[dict] = []

    # Keep the last cited set attached to the thread so a follow-up like “带着这些资料备课”
    # can act on the same records instead of running a fresh, unrelated search.
    refers_to_recent_sources = any(word in message for word in ("刚才", "这些资料", "这条资料", "上面找到", "带着资料", "结合这些"))
    if refers_to_recent_sources and isinstance(context.get("recent_sources"), list):
        carried_class_id = context.get("recent_sources_class_id")
        if class_id and carried_class_id not in (None, int(class_id)):
            carried_sources = []
        else:
            carried_sources = context["recent_sources"]
        for source in carried_sources[:5]:
            if not isinstance(source, dict) or not source.get("kind") or not source.get("label"):
                continue
            route = source.get("route")
            if route not in {"lessons", "feedback", "audio", "resources", "classes", "workbench", "teachingAssistant"}:
                continue
            records.append({
                "kind": _plain(source.get("kind"), 40), "label": _plain(source.get("label"), 100),
                "detail": _plain(source.get("detail"), 520), "id": source.get("id") if isinstance(source.get("id"), int) else 0,
                "route": route, "updated_at": _plain(source.get("updated_at"), 40),
            })

    # A manually quoted conversation follows the active thread as explicit context.
    referenced_id = context.get("referenced_conversation_id")
    if referenced_id:
        try:
            referenced_id = int(referenced_id)
        except (TypeError, ValueError):
            referenced_id = None
        if referenced_id and referenced_id != conversation_id:
            referenced = db.scalar(select(AssistantConversation).where(
                AssistantConversation.id == referenced_id,
                AssistantConversation.teacher_id == teacher_id,
            ))
            if referenced:
                excerpt = _plain(context.get("referenced_conversation_excerpt"), 520) or _conversation_excerpt(
                    _json(referenced.messages_json, []), terms
                )
                records.append(_citation(
                    "已引用的历史对话", referenced.title, excerpt or "已引用这段对话；请结合标题和后续问题继续讨论。",
                    referenced.id, "teachingAssistant", referenced.updated_at,
                ))

    wants_conversation_history = any(phrase in message for phrase in (
        "之前的对话", "之前对话", "历史对话", "上次对话", "之前聊过", "之前说过", "我们之前聊",
        "以前的聊天", "聊天记录", "对话记录", "引用之前", "引用对话",
    ))
    if wants_conversation_history:
        previous_rows = db.scalars(select(AssistantConversation).where(
            AssistantConversation.teacher_id == teacher_id,
            AssistantConversation.id != (conversation_id or -1),
        ).order_by(AssistantConversation.updated_at.desc()).limit(40)).all()
        candidates = []
        for previous in previous_rows:
            messages = _json(previous.messages_json, [])
            joined = (previous.title or "") + " " + " ".join(
                str(item.get("content") or "") for item in messages if isinstance(item, dict)
            )
            matching = sum(1 for term in terms if term.lower() in joined.lower())
            if matching or not terms:
                excerpt = _conversation_excerpt(messages, terms)
                candidates.append((matching, previous, excerpt))
        candidates.sort(key=lambda item: (item[0], item[1].updated_at or datetime.min), reverse=True)
        for _, previous, excerpt in candidates[:3]:
            records.append(_citation(
                "历史对话", previous.title or "未命名对话",
                excerpt or "这段对话没有可展示的文字内容。", previous.id, "teachingAssistant", previous.updated_at,
            ))

    # Contextual entry points must retrieve their exact parent record even when the
    # teacher's first message uses pronouns such as “这份” or “这条反馈”.
    lesson_id = context.get("lesson_id")
    if lesson_id:
        row = db.execute(select(LessonPlan, Song, ClassProfile).join(Song, Song.id == LessonPlan.song_id).outerjoin(
            ClassProfile, ClassProfile.id == LessonPlan.class_id
        ).where(LessonPlan.id == int(lesson_id), LessonPlan.teacher_id == teacher_id)).first()
        if row:
            plan, song, profile = row
            context_song_id = plan.song_id
            records.append(_citation(
                "当前教案", plan.title,
                _lesson_preview(plan, song, profile),
                plan.id, "lessons", plan.created_at,
            ))
    feedback_id = context.get("feedback_id")
    if feedback_id:
        row = db.execute(select(Feedback, ClassroomRecord, LessonPlan, ClassProfile, Song).join(
            ClassroomRecord, ClassroomRecord.id == Feedback.classroom_record_id
        ).join(LessonPlan, LessonPlan.id == ClassroomRecord.lesson_plan_id).join(
            ClassProfile, ClassProfile.id == ClassroomRecord.class_id
        ).join(Song, Song.id == LessonPlan.song_id).where(
            Feedback.id == int(feedback_id), Feedback.teacher_id == teacher_id
        )).first()
        if row:
            feedback, record, plan, profile, song = row
            context_song_id = plan.song_id
            linked_audio = db.scalar(select(AudioAnalysis).where(
                AudioAnalysis.id == feedback.audio_analysis_id,
                AudioAnalysis.teacher_id == teacher_id,
            )) if feedback.audio_analysis_id else None
            linked_audio_song = db.get(Song, linked_audio.song_id) if linked_audio else None
            linked_recording = db.scalar(select(AudioAsset).where(
                AudioAsset.id == linked_audio.recording_asset_id,
                AudioAsset.teacher_id == teacher_id,
            )) if linked_audio else None
            audio_link_valid = bool(linked_audio and linked_audio.song_id == plan.song_id
                                     and profile.id == record.class_id
                                     and linked_audio.lesson_plan_id in (None, plan.id)
                                     and linked_audio.classroom_record_id in (None, record.id)
                                     and linked_recording and linked_recording.song_id == plan.song_id
                                     and linked_recording.classroom_record_id in (None, record.id)) if feedback.audio_analysis_id else True
            records.append(_citation(
                "当前课堂反馈", f"{profile.name} · 《{song.name}》",
                _feedback_detail(feedback, record, audio_link_valid, linked_audio_song.name if linked_audio_song else None),
                feedback.id, "feedback", feedback.created_at,
            ))
    audio_id = context.get("audio_analysis_id")
    if audio_id:
        row = db.execute(select(AudioAnalysis, Song).join(Song, Song.id == AudioAnalysis.song_id).where(
            AudioAnalysis.id == int(audio_id), AudioAnalysis.teacher_id == teacher_id
        )).first()
        if row and (context_song_id is None or row[0].song_id == context_song_id):
            analysis, song = row
            recording = db.scalar(select(AudioAsset).where(
                AudioAsset.id == analysis.recording_asset_id,
                AudioAsset.teacher_id == teacher_id,
            ))
            associated_record = db.get(ClassroomRecord, analysis.classroom_record_id) if analysis.classroom_record_id else None
            recording_record = db.get(ClassroomRecord, recording.classroom_record_id) if recording and recording.classroom_record_id else None
            if recording and recording.song_id == analysis.song_id and (
                not class_id or (
                    (not associated_record or associated_record.class_id == int(class_id))
                    and (not recording_record or recording_record.class_id == int(class_id))
                )
            ):
                records.append(_citation(
                    "当前音频分析", f"《{song.name}》音频分析",
                    _analysis_detail(analysis.result_json, analysis.method_version), analysis.id, "audio", analysis.created_at,
                ))

    wants_class_context = bool(class_id) or any(word in message for word in ("班级", "画像", "学生", "课堂反馈", "这个班"))
    wants_audio_context = bool(context.get("audio_analysis_id")) or any(
        word in message for word in ("音频", "录音", "音准", "人声", "练唱", "波形", "音频分析")
    )
    classes = [item for item in owned_profiles if item.id == int(class_id)] if class_id else (
        [item for item in owned_profiles if not terms or any(term in (item.name + item.province + item.common_problems + item.teacher_notes) for term in terms)]
        if wants_class_context else []
    )
    classes = sorted(classes, key=lambda item: item.updated_at or item.created_at, reverse=True)[:3]
    for row in classes:
        records.append(_citation(
            "班级画像", row.name,
            f"{row.grade}年级；地区：{row.province}；节奏：{row.rhythm_level}；音准：{row.pitch_level}；"
            f"合作：{row.cooperation}；课堂偏好：{row.preferred_method}；常见问题：{row.common_problems}",
            row.id, "classes", row.updated_at,
        ))

    lesson_stmt = select(LessonPlan, Song, ClassProfile).join(Song, Song.id == LessonPlan.song_id).outerjoin(
        ClassProfile, ClassProfile.id == LessonPlan.class_id
    ).where(LessonPlan.teacher_id == teacher_id)
    if class_id:
        lesson_stmt = lesson_stmt.where(LessonPlan.class_id == int(class_id))
    if context_song_id:
        lesson_stmt = lesson_stmt.where(LessonPlan.song_id == context_song_id)
    if terms:
        condition = _matches([LessonPlan.title, LessonPlan.teacher_requirements, LessonPlan.content_json, Song.name], terms)
        if condition is not None:
            lesson_stmt = lesson_stmt.where(condition)
    lesson_rows = db.execute(lesson_stmt.order_by(LessonPlan.created_at.desc()).limit(5)).all()
    for plan, song, profile in lesson_rows:
        records.append(_citation(
            "历史教案", plan.title,
            _lesson_preview(plan, song, profile),
            plan.id, "lessons", plan.created_at,
        ))

    feedback_stmt = select(Feedback, ClassroomRecord, LessonPlan, ClassProfile, Song).join(
        ClassroomRecord, ClassroomRecord.id == Feedback.classroom_record_id
    ).join(LessonPlan, LessonPlan.id == ClassroomRecord.lesson_plan_id).join(
        ClassProfile, ClassProfile.id == ClassroomRecord.class_id
    ).join(Song, Song.id == LessonPlan.song_id).where(Feedback.teacher_id == teacher_id)
    if class_id:
        feedback_stmt = feedback_stmt.where(ClassroomRecord.class_id == int(class_id))
    if context_song_id:
        feedback_stmt = feedback_stmt.where(LessonPlan.song_id == context_song_id)
    if terms:
        condition = _matches(
            [Feedback.highlights, Feedback.problems, Feedback.improvement, Feedback.audio_summary,
             Feedback.analysis_json, LessonPlan.title, ClassProfile.name, Song.name], terms,
        )
        if condition is not None:
            feedback_stmt = feedback_stmt.where(condition)
    for feedback, record, plan, profile, song in db.execute(
        feedback_stmt.order_by(Feedback.created_at.desc()).limit(5)
    ).all():
        linked_audio = db.scalar(select(AudioAnalysis).where(
            AudioAnalysis.id == feedback.audio_analysis_id,
            AudioAnalysis.teacher_id == teacher_id,
        )) if feedback.audio_analysis_id else None
        linked_audio_song = db.get(Song, linked_audio.song_id) if linked_audio else None
        linked_recording = db.scalar(select(AudioAsset).where(
            AudioAsset.id == linked_audio.recording_asset_id,
            AudioAsset.teacher_id == teacher_id,
        )) if linked_audio else None
        audio_link_valid = bool(linked_audio and linked_audio.song_id == plan.song_id
                                 and plan.class_id == record.class_id
                                 and linked_audio.lesson_plan_id in (None, plan.id)
                                 and linked_audio.classroom_record_id in (None, record.id)
                                 and linked_recording and linked_recording.song_id == plan.song_id
                                 and linked_recording.classroom_record_id in (None, record.id)) if feedback.audio_analysis_id else True
        records.append(_citation(
            "课堂反馈", f"{profile.name} · 《{song.name}》",
            _feedback_detail(feedback, record, audio_link_valid, linked_audio_song.name if linked_audio_song else None),
            feedback.id, "feedback", feedback.created_at,
        ))

    revision_stmt = select(LessonPlanRevision, LessonPlan, Song, ClassProfile).join(
        LessonPlan, LessonPlan.id == LessonPlanRevision.lesson_plan_id
    ).join(Song, Song.id == LessonPlan.song_id).outerjoin(ClassProfile, ClassProfile.id == LessonPlan.class_id).where(
        LessonPlanRevision.teacher_id == teacher_id
    )
    if class_id:
        revision_stmt = revision_stmt.where(LessonPlan.class_id == int(class_id))
    if terms:
        condition = _matches([LessonPlanRevision.content_json, LessonPlan.title, Song.name], terms)
        if condition is not None:
            revision_stmt = revision_stmt.where(condition)
    for revision, plan, song, profile in db.execute(
        revision_stmt.order_by(LessonPlanRevision.created_at.desc()).limit(3)
    ).all():
        revision_content = _mapping(revision.content_json)
        revision_summary = _plain(revision_content.get("summary") or revision_content.get("overview"))
        if not revision_summary and isinstance(revision_content.get("objectives"), list):
            objectives = [_plain(value, 70) for value in revision_content["objectives"][:3]]
            revision_summary = "教学目标：" + "；".join(value for value in objectives if value)
        records.append(_citation(
            "教案历史版本", f"{plan.title} · 第{revision.revision_number}版",
            f"歌曲：《{song.name}》；班级：{profile.name if profile else '未指定'}；课时：{plan.duration_minutes}分钟。"
            + (f"版本要点：{revision_summary}" if revision_summary else "可打开教案查看完整版本。"),
            revision.id, "lessons", revision.created_at,
        ))

    resource_models = [
        ("歌曲资源", Song, ["name", "source", "mood", "song_type", "grade"], "resources"),
        ("音乐游戏", TeachingGame, ["name", "personality", "grade", "match_condition", "instructions"], "resources"),
        ("乐理资源", MusicTheory, ["term", "category", "lower_grade_script", "upper_grade_script"], "resources"),
        ("易错纠正", TeachingMistake, ["category", "problem", "correction"], "resources"),
    ]
    for label, model, field_names, route_name in resource_models:
        stmt = select(model).where(or_(model.owner_teacher_id.is_(None), model.owner_teacher_id == teacher_id))
        if terms:
            condition = _matches([getattr(model, name) for name in field_names], terms)
            if condition is not None:
                stmt = stmt.where(condition)
        for row in db.scalars(stmt.limit(4)).all():
            name = getattr(row, "name", None) or getattr(row, "term", None) or _plain(getattr(row, "problem", ""), 80) or label
            detail = _resource_detail(label, row)
            if detail:
                records.append(_citation(label, name, detail, row.id, route_name))

    # Never surface an arbitrary recent recording for an unscoped prompt.
    allow_audio_search = bool(context_song_id or class_id or context.get("audio_analysis_id"))
    audio_stmt = None
    if wants_audio_context and allow_audio_search:
        audio_stmt = select(AudioAnalysis, Song).join(Song, Song.id == AudioAnalysis.song_id).where(
            AudioAnalysis.teacher_id == teacher_id
        )
        if class_id:
            audio_stmt = audio_stmt.outerjoin(
                ClassroomRecord, ClassroomRecord.id == AudioAnalysis.classroom_record_id
            ).where(ClassroomRecord.class_id == int(class_id))
        if context_song_id:
            audio_stmt = audio_stmt.where(AudioAnalysis.song_id == context_song_id)
        if terms:
            condition = _matches([Song.name, AudioAnalysis.result_json, AudioAnalysis.method_version], terms)
            if condition is not None:
                audio_stmt = audio_stmt.where(condition)
    for row, song in (db.execute(audio_stmt.order_by(AudioAnalysis.created_at.desc()).limit(4)).all() if audio_stmt is not None else []):
        result = _json(row.result_json, {})
        if not isinstance(result, dict):
            continue
        detail = _analysis_detail(result, row.method_version)
        if detail == "已保存分析记录；请打开音频分析页面查看完整结果。":
            continue
        records.append(_citation(
            "音频分析", f"《{song.name}》音频分析",
            detail,
            row.id, "audio", row.created_at,
        ))

    asset_stmt = None
    if wants_audio_context and allow_audio_search:
        asset_stmt = select(AudioAsset, Song, ClassroomRecord).join(Song, Song.id == AudioAsset.song_id).outerjoin(
            ClassroomRecord, ClassroomRecord.id == AudioAsset.classroom_record_id
        ).where(AudioAsset.teacher_id == teacher_id)
        if class_id:
            asset_stmt = asset_stmt.where(ClassroomRecord.class_id == int(class_id))
        if context_song_id:
            asset_stmt = asset_stmt.where(AudioAsset.song_id == context_song_id)
        if terms:
            condition = _matches([AudioAsset.original_filename, AudioAsset.asset_type, Song.name], terms)
            if condition is not None:
                asset_stmt = asset_stmt.where(condition)
    for asset, song, record in (db.execute(asset_stmt.order_by(AudioAsset.created_at.desc()).limit(4)).all() if asset_stmt is not None else []):
        profile_name = db.get(ClassProfile, record.class_id).name if record and db.get(ClassProfile, record.class_id) else "未关联班级"
        records.append(_citation(
            "音频文件", asset.original_filename or f"《{song.name}》录音",
            f"歌曲：《{song.name}》；类型：{asset.asset_type}；班级：{profile_name}；时长：{asset.duration_seconds or '未知'}秒；"
            f"是否参考音源：{'是' if asset.is_reference else '否'}。文件本体需通过音频页面播放，助手不会伪称已听过未分析的音频。",
            asset.id, "audio", asset.created_at,
        ))

    soundfont_stmt = select(InstrumentSoundfont).where(InstrumentSoundfont.teacher_id == teacher_id)
    if terms:
        condition = _matches([InstrumentSoundfont.display_name, InstrumentSoundfont.original_filename,
                              InstrumentSoundfont.preset_name, InstrumentSoundfont.instruments_json], terms)
        if condition is not None:
            soundfont_stmt = soundfont_stmt.where(condition)
    for item in db.scalars(soundfont_stmt.order_by(InstrumentSoundfont.updated_at.desc()).limit(4)).all():
        instruments = _instrument_names(item.instruments_json)
        detail = f"文件：{item.original_filename}；预设：{_plain(item.preset_name, 100) or '未标注'}"
        if instruments:
            detail += f"；包含乐器：{instruments}"
        detail += f"；大小：{item.file_size}字节。"
        records.append(_citation(
            "乐器音色包", item.display_name,
            detail,
            item.id, "workbench", item.updated_at,
        ))

    arrangement_stmt = select(ArrangementProject).where(ArrangementProject.teacher_id == teacher_id)
    if terms:
        condition = _matches([ArrangementProject.title, ArrangementProject.style, ArrangementProject.arrangement_json], terms)
        if condition is not None:
            arrangement_stmt = arrangement_stmt.where(condition)
    for row in db.scalars(arrangement_stmt.order_by(ArrangementProject.updated_at.desc()).limit(4)).all():
        arrangement = _json(row.arrangement_json, {})
        instruments = _instrument_names(arrangement.get("instruments", [])) if isinstance(arrangement, dict) else ""
        melody = _json(row.melody_json, [])
        records.append(_citation(
            "编曲工程", row.title,
            f"速度：{row.tempo} BPM；风格：{_plain(row.style, 60) or '未标注'}；旋律音符：{len(melody) if isinstance(melody, list) else 0}个。"
            + (f"使用乐器：{instruments}。" if instruments else ""),
            row.id, "workbench", row.updated_at,
        ))

    observations = str(context.get("teacher_observations") or "").strip()
    if observations:
        records.insert(0, _citation(
            "本次未保存的课堂观察", context.get("source_label") or "教师本次输入",
            observations, int(context.get("lesson_id") or 0), "feedback",
        ))
    # Prefer records whose titles and evidence actually match this turn, while retaining
    # a bounded, varied set so audio, arrangements, resources, and feedback are not starved.
    terms_lower = [term.lower() for term in terms]
    recent_source_rows = context.get("recent_sources") if isinstance(context.get("recent_sources"), list) else []
    recent_source_ids = {
        (str(item.get("kind") or ""), item.get("id") if isinstance(item.get("id"), int) else 0)
        for item in recent_source_rows if isinstance(item, dict)
    }
    def relevance(item):
        text = (item.get("label", "") + " " + item.get("detail", "")).lower()
        return sum(2 if term in item.get("label", "").lower() else 1 for term in terms_lower if term in text)
    if terms_lower:
        records.sort(key=lambda item: (
            1 if wants_conversation_history and item.get("kind") == "历史对话" else 0,
            1 if refers_to_recent_sources and (str(item.get("kind") or ""), int(item.get("id") or 0)) in recent_source_ids else 0,
            relevance(item),
        ), reverse=True)
    else:
        records.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    counts: dict[str, int] = {}
    seen_records: set[tuple[str, int]] = set()
    diverse = []
    for item in records:
        kind = item["kind"]
        canonical_kind = "教案" if kind in {"当前教案", "历史教案"} else "反馈" if kind in {"当前课堂反馈", "课堂反馈"} else "音频分析" if kind == "当前音频分析" else kind
        identity = (canonical_kind, int(item.get("id") or 0))
        if identity in seen_records or counts.get(canonical_kind, 0) >= 2:
            continue
        seen_records.add(identity)
        counts[canonical_kind] = counts.get(canonical_kind, 0) + 1
        diverse.append(item)
        if len(diverse) >= 8:
            break
    return diverse


def _is_lookup(message: str) -> bool:
    lookup_language = any(word in message for word in ("找", "查", "检索", "以前", "之前", "历史", "回看", "有没有", "搜一下", "找出来"))
    project_scope = any(word in message for word in (
        "教案", "课堂反馈", "班级", "歌曲", "教学资源", "资源库", "音频", "录音", "编曲", "乐器", "乐理", "易错", "对话", "聊天", "记录",
    ))
    return lookup_language and project_scope


def _is_refine_search_request(message: str) -> bool:
    return any(phrase in message for phrase in (
        "换个条件再找", "换个条件找", "换一个条件", "换个年级", "按别的条件", "换个方向找",
    ))


def _is_contextual_short_reply(message: str, history: list[dict]) -> bool:
    text = message.strip()
    if len(text) > 28 or not history:
        return False
    last_assistant = next((item for item in reversed(history) if isinstance(item, dict) and item.get("role") == "assistant"), None)
    if not last_assistant:
        return False
    prompt = str(last_assistant.get("content") or "")
    asks = ("？" in prompt or "?" in prompt or any(phrase in prompt for phrase in ("你可以选择", "告诉我", "先确认", "哪一种")))
    return asks and bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9、，。！？!?\s]{1,28}", text))


def _is_song_recommendation(message: str) -> bool:
    return any(word in message for word in ("推荐歌曲", "推荐几首歌", "推荐一首歌", "适合的歌曲", "选什么歌", "选一首歌"))


def _is_all_class_request(message: str) -> bool:
    return any(word in message for word in ("所有班级", "全部班级", "各个班", "各班", "跨班", "班级整体对比", "整体对比"))


def _requires_class_scope(message: str, context: dict, profiles: list[ClassProfile]) -> bool:
    """Class evidence is never inferred from whichever record happens to be newest."""
    if any(context.get(key) for key in ("class_id", "lesson_id", "feedback_id")) or _is_all_class_request(message):
        return False
    if any(item.name and item.name in message for item in profiles):
        return False
    class_sensitive = (
        "这个班", "这班", "本班", "该班", "这个班级", "这个班最近", "班级最近",
        "班级画像", "班级反馈", "课堂反馈里", "课堂反馈中", "课后反馈里", "课后反馈中",
        "反馈里反复", "反馈中反复", "反复出现", "最近的课堂反馈", "最近课堂反馈", "某个班",
    )
    refers_to_feedback_history = any(word in message for word in ("课堂反馈", "课后反馈", "反馈记录")) and any(
        word in message for word in ("查看", "看看", "最近", "之前", "情况", "总结", "查", "找", "反复")
    )
    return any(phrase in message for phrase in class_sensitive) or (len(profiles) > 1 and refers_to_feedback_history)


def _requested_class_change(message: str, profiles: list[ClassProfile]):
    """Return a class only when the user explicitly phrases a scope switch."""
    text = re.sub(r"\s+", "", message or "")
    for profile in profiles:
        name = re.sub(r"\s+", "", str(profile.name or ""))
        if not name or name not in text:
            continue
        patterns = (
            rf"(?:切换|換|换|改|调整|調整)(?:到|成|为|用)?{re.escape(name)}",
            rf"(?:班级|班級)(?:改为|改成|调整为|調整為|设为|設定為|换成|切换到){re.escape(name)}",
            rf"(?:这次|本次|接下来|以后|之后)(?:先)?(?:用|按|切换到|改成){re.escape(name)}",
        )
        if any(re.search(pattern, text) for pattern in patterns):
            return profile
    return None


def _today_question_reply(message: str) -> str | None:
    text = re.sub(r"\s+", "", message or "")
    if not re.search(r"今天.*(?:周几|星期几|星期|几号|日期)|今天是(?:几号|星期几|周几)", text):
        return None
    today = datetime.now(ZoneInfo("Asia/Shanghai"))
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    return f"今天是{today.year}年{today.month}月{today.day}日，{weekdays[today.weekday()]}。"


def _class_scope_suggestions(profiles: list[ClassProfile], message: str) -> list[dict]:
    def scoped_query(name: str) -> str:
        query = message
        for phrase in ("这个班级", "这个班", "这班", "本班", "该班", "某个班"):
            query = query.replace(phrase, name)
        return query

    suggestions = [{"label": item.name, "message": scoped_query(item.name), "class_id": int(item.id)}
                   for item in profiles[:5] if item.name]
    if len(profiles) > 1:
        all_query = message
        for phrase in ("这个班级", "这个班", "这班", "本班", "该班", "某个班"):
            all_query = all_query.replace(phrase, "所有班级")
        if not _is_all_class_request(all_query):
            all_query = f"查看所有班级的课堂反馈：{all_query}"
        suggestions.append({"label": "查看全部班级", "message": all_query})
    return suggestions


def _is_feedback_creation_request(message: str) -> bool:
    feedback_words = ("课堂反馈", "课后反馈", "反馈记录")
    creation_words = ("生成", "写一份", "帮我写", "整理成", "新建", "填写", "做一份")
    return any(word in message for word in feedback_words) and any(word in message for word in creation_words)


def _is_observation_offer(message: str) -> bool:
    return any(phrase in message for phrase in (
        "我会提供本节课实际观察", "我来补充课堂观察", "我提供课堂观察", "我来提供实际观察",
    ))


def _is_blank_feedback_form_request(message: str) -> bool:
    return any(word in message for word in ("空白反馈表", "空白课堂反馈", "打开反馈表", "打开课堂反馈页", "填写课堂反馈表"))


def _follow_up_suggestions(message: str, sources: list[dict], actions: list[dict]) -> list[dict]:
    """Offer a few relevant next moves without turning every reply into a checklist."""
    if actions:
        return []
    history_source = next((item for item in sources if item.get("kind") == "历史对话"), None)
    if history_source:
        return [
            {"label": "引用这段对话继续聊", "message": "请结合我引用的这段旧对话，继续回答我刚才的问题", "conversation_id": history_source.get("id")},
            {"label": "打开原对话", "message": "打开这段历史对话", "conversation_id": history_source.get("id"), "action": "open_conversation"},
        ]
    if any(word in message for word in ("课堂反馈", "课后反馈", "反馈", "课堂表现")):
        return [
            {"label": "按班级继续查看", "message": "我想按班级继续查看课堂反馈"},
            {"label": "根据反馈准备教案", "message": "根据刚才找到的课堂反馈，和我一起准备一份教案"},
            {"label": "打开课堂反馈页", "message": "打开空白课堂反馈表"},
        ]
    if any(item.get("kind") in {"歌曲资源", "音乐游戏", "乐理资源", "易错纠正"} for item in sources):
        return [
            {"label": "围绕这些资源备课", "message": "请结合刚才找到的资源，和我一起准备一节课"},
            {"label": "换个条件再找", "message": "换一个年级或课堂目标再帮我找找"},
        ]
    if sources:
        return [
            {"label": "继续看这条资料", "message": "请把刚才最相关的资料展开说明"},
            {"label": "带着资料准备教案", "message": "结合刚才找到的资料，和我一起准备一份教案"},
        ]
    return []


def _should_retrieve(message: str, context: dict) -> bool:
    if any(context.get(key) for key in ("class_id", "lesson_id", "feedback_id", "audio_analysis_id", "teacher_observations", "referenced_conversation_id")):
        return True
    return any(word in message for word in (
        "教案", "课堂反馈", "班级", "歌曲", "资源库", "音频", "录音", "编曲", "乐器", "音色",
        "以前", "之前", "历史", "上次", "对话", "聊天", "引用", "记录", "游戏", "乐理", "易错", "反馈",
    ))


def _recommendation_response(db: Session, teacher_id: int, message: str, context: dict) -> tuple[str, list[dict], list[dict]]:
    profiles = db.scalars(select(ClassProfile).where(ClassProfile.teacher_id == teacher_id)).all()
    class_id = context.get("class_id")
    profile = next((item for item in profiles if class_id and item.id == int(class_id)), None)
    if profile is None:
        named = [item for item in profiles if item.name and item.name in message]
        profile = named[0] if len(named) == 1 else None
    if profile is None:
        return "可以。我先确认一下是给哪个班挑歌？你可以选择班级，或者直接告诉我年级和班名。", [], []

    region_match = re.search(r"(华南地区|华东地区|华北地区|西南地区|西北地区|东北地区|华中地区)", message)
    region = region_match.group(1) if region_match else None
    candidates = recommend_songs(db, region, profile, limit=3, teacher_id=teacher_id)
    if not candidates:
        return f"我还没找到适合{profile.name}的歌曲。可以先到教学资源库补充歌曲，或者告诉我想练的内容，我再帮你换个方向找。", [], []
    sources = []
    actions = []
    descriptions = []
    for candidate in candidates:
        song = candidate["song"]
        detail = (
            f"匹配度参考：{candidate['match_score']}%；推荐依据：{candidate['reason']}；"
            f"地区：{song.region or '未标注'}；适用年级：{song.grade or '未标注'}；"
            f"情绪：{song.mood or '未标注'}；难度：{song.difficulty or '未标注'}。"
        )
        sources.append(_citation("推荐歌曲", song.name, detail, song.id, "resources"))
        descriptions.append(f"《{song.name}》——{candidate['reason']}（匹配参考 {candidate['match_score']}%）")
        actions.append({
            "type": "open_lesson_planner", "label": f"围绕《{song.name}》备课",
            "song_id": song.id, "song_name": song.name,
        })
    reply = f"我结合{profile.name}的年级、地区和课堂特点，先挑了几首供你看看：\n" + "\n".join(
        f"{index + 1}. {item}" for index, item in enumerate(descriptions)
    ) + "\n你可以先选一首，再继续确认课堂目标和活动；我不会因为你问了推荐就直接生成教案。"
    return reply, sources, actions


def _is_lesson_action(message: str, context: dict | None = None) -> bool:
    action = any(word in message for word in (
        "生成教案", "备一份教案", "新建教案", "修改教案", "调整教案", "根据反馈改", "按反馈调整",
        "准备教案", "准备一份教案", "一起备课", "一起准备一节课", "准备新课",
    ))
    contextual_edit = bool((context or {}).get("lesson_id") or (context or {}).get("type") in {"feedback", "feedback_draft"}) and any(
        word in message for word in ("改成", "调整", "修改", "删掉", "增加", "补充", "保留")
    )
    return action or contextual_edit


def _lookup_reply(records: list[dict]) -> str:
    if not records:
        return "我暂时没有找到匹配的记录。你可以告诉我班级、歌曲或大概时间，我再帮你缩小范围。"
    history_records = [item for item in records if item.get("kind") == "历史对话"]
    if history_records:
        return f"找到 {len(history_records)} 段可能相关的旧对话。我把标题和相关问答放在下方资料里，你可以展开查看、引用到当前对话，或直接打开原对话。"
    lines = ["我找到了几条相关记录，先把最接近的列给你："]
    for item in records[:4]:
        detail = _plain(item.get("detail", ""), 70)
        lines.append(f"• {item['label']} · {item['kind']}" + (f"：{detail}" if detail else ""))
    return "\n".join(lines)


def _compact_sources(records: list[dict], limit: int = 3) -> str:
    lines = []
    for item in records[:limit]:
        detail = _plain(item.get("detail", ""), 110)
        line = f"{item['kind']}《{item['label']}》"
        if detail:
            line += f"：{detail}"
        lines.append(line)
    return "；".join(lines)


@router.post("/conversations", status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    row = AssistantConversation(
        teacher_id=teacher.id, title=payload.title.strip() or "新对话",
        context_json=json.dumps(payload.context, ensure_ascii=False), messages_json="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _present(row, True)


@router.get("/conversations")
def list_conversations(
    class_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    stmt = select(AssistantConversation).where(AssistantConversation.teacher_id == teacher.id)
    rows = db.scalars(stmt.order_by(AssistantConversation.updated_at.desc()).limit(100)).all()
    if class_id is not None:
        rows = [row for row in rows if _json(row.context_json, {}).get("class_id") == class_id]
    return [_present(row) for row in rows]


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    return _present(_owned_conversation(db, conversation_id, teacher.id), True)


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    payload: ConversationPatch,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    row = _owned_conversation(db, conversation_id, teacher.id)
    if payload.title is not None:
        row.title = payload.title.strip()[:100] or "新对话"
    if payload.context is not None:
        row.context_json = json.dumps(payload.context, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _present(row, True)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    row = _owned_conversation(db, conversation_id, teacher.id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    row = _owned_conversation(db, conversation_id, teacher.id)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="请先写下想讨论的内容")
    context = _json(row.context_json, {})
    history = _json(row.messages_json, [])
    suggestions: list[dict] = []
    try:
        profiles = db.scalars(select(ClassProfile).where(ClassProfile.teacher_id == teacher.id)).all()
        class_switch = _requested_class_change(message, profiles)
        requested_today = _today_question_reply(message)
        if requested_today:
            sources, actions = [], []
            reply = requested_today
        elif class_switch and int(context.get("class_id") or 0) != int(class_switch.id):
            sources, actions = [], []
            current_name = _plain(context.get("class_name"), 60) or next(
                (profile.name for profile in profiles if int(profile.id) == int(context.get("class_id") or 0)),
                "尚未指定班级",
            )
            reply = f"我听明白了，你想把这段对话从“{current_name}”切换到“{class_switch.name}”。我先不直接改，确认后再更新班级范围，可以吗？"
            suggestions = [
                {"label": f"确认切换到{class_switch.name}", "message": f"确认切换到{class_switch.name}", "class_id": int(class_switch.id), "action": "confirm_class_change"},
                {"label": "保持当前班级", "message": "保持当前班级", "action": "cancel_class_change"},
            ]
        elif class_switch:
            sources, actions = [], []
            reply = f"这段对话已经在“{class_switch.name}”范围内了。我会继续按这个班级查找和讨论。"
        elif _is_blank_feedback_form_request(message):
            sources = []
            actions = [{
                "type": "open_feedback_form", "label": "打开课堂反馈页",
                "class_id": context.get("class_id") if isinstance(context.get("class_id"), int) else None,
                "lesson_id": context.get("lesson_id") if isinstance(context.get("lesson_id"), int) else None,
            }]
            reply = "好，我带你打开课堂反馈页。那里可以先选择已保存教案，再记录本节课实际观察到的情况；没有提供的课堂表现我不会替你补写。"
        elif _is_feedback_creation_request(message):
            sources, actions = [], []
            if context.get("class_id") or context.get("lesson_id"):
                actions.append({
                    "type": "open_feedback_form", "label": "打开课堂反馈页",
                    "class_id": context.get("class_id") if isinstance(context.get("class_id"), int) else None,
                    "lesson_id": context.get("lesson_id") if isinstance(context.get("lesson_id"), int) else None,
                })
            actions.append({"type": "open_feedback_archive", "label": "查看已有反馈"})
            reply = (
                "可以，我们先把要做的事分清楚：你是想打开一份空白反馈表，查看已有课堂反馈，"
                "还是把你记录的课堂观察整理成反馈？如果是整理内容，请把实际观察告诉我；我不会根据旧教案或别的班级记录编造课堂表现。"
            )
            suggestions = [
                {"label": "打开空白反馈表", "message": "打开空白课堂反馈表"},
                {"label": "查看已有反馈", "message": "查看所有班级的已有课堂反馈记录"},
                {"label": "我来补充课堂观察", "message": "我会提供本节课实际观察"},
            ]
        elif _is_observation_offer(message):
            sources, actions = [], []
            reply = (
                "好，你可以直接把这节课实际看到的情况发给我，比如学生在哪个环节跟上了、哪里遇到困难、你准备怎样调整。"
                "也请告诉我对应的班级或教案。收到后我会先把你的原始观察整理成待核对内容，再由你决定是否带到课堂反馈页保存。"
            )
            suggestions = []
        elif _requires_class_scope(message, context, profiles):
            sources, actions = [], []
            available = "、".join(item.name for item in profiles if item.name) or "目前没有可选班级"
            reply = (
                f"可以帮你梳理这部分记录。为了不把不同班级的情况混在一起，我先确认一下：你想看哪个班？目前可查看：{available}。"
                "选定后我会只根据该班已有记录回答；如果要看整体情况，也可以选择查看全部班级。"
            )
            suggestions = _class_scope_suggestions(profiles, message)
        elif _is_song_recommendation(message):
            sources = _retrieve(db, teacher.id, message, context, row.id) if _should_retrieve(message, context) else []
            reply, sources, actions = _recommendation_response(db, teacher.id, message, context)
            if not actions and "哪个班" in reply:
                suggestions = [{
                    "label": profile.name,
                    "message": f"给{profile.name}推荐几首适合的歌曲",
                    "class_id": int(profile.id),
                } for profile in profiles[:5] if profile.name]
        elif _is_refine_search_request(message):
            sources, actions = [], []
            grades = sorted({f"{profile.grade}年级" for profile in profiles if profile.grade})
            suggestions = [
                {"label": f"{grade} · 节奏练习", "message": f"按{grade}找适合节奏练习的教学资源"}
                for grade in grades[:3]
            ]
            suggestions.extend([
                {"label": "识谱练习", "message": "找适合识谱练习的歌曲或课堂活动"},
                {"label": "无音箱也能上", "message": "找不需要音箱、可以现场带做的音乐活动"},
                {"label": "按歌曲筛选", "message": "按歌曲和适用年级筛选教学资源"},
            ])
            reply = "好呀，我们换个方向慢慢找。你更想按哪个条件筛？可以点下面的选项，也可以直接告诉我年级、课堂目标、歌曲或设备限制。"
        elif _is_lesson_action(message, context):
            sources = _retrieve(db, teacher.id, message, context, row.id) if _should_retrieve(message, context) else []
            source_text = _compact_sources(sources)
            reply = (
                (f"我把这次提到的资料带上了：{source_text}。" if source_text else "我记下了这次备课方向；暂时没有找到能直接引用的旧记录。")
                + "点下面的按钮进入教案助手，我们会接着核对班级、歌曲和课时；你确认后才会生成。"
            )
            actions = [{"type": "open_lesson_planner", "label": "继续准备教案"}]
        elif _is_contextual_short_reply(message, history):
            sources = _retrieve(db, teacher.id, message, context, row.id) if _should_retrieve(message, context) else []
            retrieval_context = {
                "entry_context": context,
                "retrieved_records": sources,
                "response_style": "结合上一轮你提出的问题解释用户的简短回答。若对方只回复数字，要对照你刚才给出的编号选项；没有编号依据时就自然追问，不要自己猜。保持温和、简短、像连续聊天。",
            }
            reply = reply_to_lesson_dialogue(message, history[-16:], retrieval_context)
            actions = []
        elif _is_lookup(message):
            sources = _retrieve(db, teacher.id, message, context, row.id) if _should_retrieve(message, context) else []
            reply = _lookup_reply(sources)
            actions = []
        else:
            sources = _retrieve(db, teacher.id, message, context, row.id) if _should_retrieve(message, context) else []
            retrieval_context = {
                "entry_context": context,
                "retrieved_records": sources,
                "response_style": (
                    "温暖自然，先回应本轮问题；不套固定格式，不重复用户原话。用户聊到项目内的历史记录时，只引用本轮检索到且范围匹配的事实；普通知识、闲聊或偏离项目主题的问题，可以直接用你的通用知识回答，不要硬拉回固定流程。"
                    "不得根据最近记录猜测用户指的是哪个班，不得把教案计划写成已发生的课堂事实，也不得编造日期、学生表现、反馈或音频结论。"
                    "信息不足或指代不清时，先用一句自然的话询问关键条件；不要自行生成教案或课堂反馈，也不要声称已保存或已修改。"
                ),
            }
            reply = reply_to_lesson_dialogue(
                message,
                [{"role": item.get("role"), "content": (
                    _naturalize_dialogue_answer(str(item.get("content", "")))[:1200]
                    if item.get("role") == "assistant" else str(item.get("content", ""))[:1200]
                )} for item in history[-16:] if isinstance(item, dict) and item.get("role") in {"user", "assistant"}],
                retrieval_context,
            )
            actions = []
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("teaching_assistant_message_failed teacher_id=%s conversation_id=%s", teacher.id, row.id)
        raise HTTPException(status_code=502, detail="这条消息暂时没有处理好，原有对话和资料都已保留；可以稍后重试。") from exc

    if "确认切换到" in message and context.get("class_id"):
        for prior in history:
            if isinstance(prior, dict) and prior.get("role") == "assistant" and isinstance(prior.get("suggestions"), list):
                prior["suggestions"] = [
                    item for item in prior["suggestions"]
                    if not isinstance(item, dict) or item.get("action") not in {"confirm_class_change", "cancel_class_change"}
                ]
    if not suggestions:
        suggestions = _follow_up_suggestions(message, sources, actions)

    user_item = {"role": "user", "content": message, "created_at": datetime.utcnow().isoformat(timespec="seconds")}
    assistant_item = {
        "role": "assistant", "content": reply,
        "sources": sources, "actions": actions, "suggestions": suggestions,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    if sources:
        context["recent_sources"] = [{
            "kind": item.get("kind"), "label": item.get("label"), "detail": item.get("detail"),
            "id": item.get("id"), "route": item.get("route"), "updated_at": item.get("updated_at"),
        } for item in sources[:5]]
        context["recent_sources_class_id"] = int(context["class_id"]) if context.get("class_id") else None
        row.context_json = json.dumps(context, ensure_ascii=False)
    history.extend([user_item, assistant_item])
    row.messages_json = json.dumps(history[-200:], ensure_ascii=False)
    if row.title == "新对话":
        row.title = message[:24] + ("…" if len(message) > 24 else "")
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"conversation": _present(row, True), "reply": assistant_item}

