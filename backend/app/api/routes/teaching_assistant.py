from __future__ import annotations

import json
import logging
import re
import ast
from datetime import datetime
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
                                "route": source.get("route") if source.get("route") in {"lessons", "feedback", "audio", "resources", "classes", "workbench"} else None,
                            })
                        if safe_sources:
                            item["sources"] = safe_sources
                    actions = raw.get("actions")
                    if isinstance(actions, list):
                        item["actions"] = [{
                            "type": "open_lesson_planner",
                            "label": _plain(action.get("label"), 60) or "带入教案助手",
                            "song_id": action.get("song_id") if isinstance(action.get("song_id"), int) else None,
                            "song_name": _plain(action.get("song_name"), 80),
                        } for action in actions[:3] if isinstance(action, dict)
                          and action.get("type") == "open_lesson_planner"]
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


def _retrieve(db: Session, teacher_id: int, message: str, context: dict) -> list[dict]:
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
    def relevance(item):
        text = (item.get("label", "") + " " + item.get("detail", "")).lower()
        return sum(2 if term in item.get("label", "").lower() else 1 for term in terms_lower if term in text)
    if terms_lower:
        records.sort(key=relevance, reverse=True)
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
    return any(word in message for word in ("找", "查", "检索", "以前", "之前", "历史", "回看", "有没有", "搜一下", "找出来"))


def _is_song_recommendation(message: str) -> bool:
    return any(word in message for word in ("推荐歌曲", "推荐几首歌", "推荐一首歌", "适合的歌曲", "选什么歌", "选一首歌"))


def _should_retrieve(message: str, context: dict) -> bool:
    if any(context.get(key) for key in ("class_id", "lesson_id", "feedback_id", "audio_analysis_id", "teacher_observations")):
        return True
    return any(word in message for word in (
        "教案", "课堂反馈", "班级", "歌曲", "资源库", "音频", "录音", "编曲", "乐器", "音色",
        "以前", "之前", "历史", "上次", "记录", "游戏", "乐理", "易错", "反馈",
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
    action = any(word in message for word in ("生成教案", "备一份教案", "新建教案", "修改教案", "调整教案", "根据反馈改", "按反馈调整"))
    contextual_edit = bool((context or {}).get("lesson_id") or (context or {}).get("type") in {"feedback", "feedback_draft"}) and any(
        word in message for word in ("改成", "调整", "修改", "删掉", "增加", "补充", "保留")
    )
    return action or contextual_edit


def _lookup_reply(records: list[dict]) -> str:
    if not records:
        return "我暂时没有找到匹配的记录。你可以告诉我班级、歌曲或大概时间，我再帮你缩小范围。"
    lines = ["我找到了几条相关记录，先把最接近的列给你："]
    for item in records[:4]:
        detail = _plain(item.get("detail", ""), 110)
        lines.append(f"• {item['label']}（{item['kind']}）" + (f"：{detail}" if detail else ""))
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
    try:
        sources = _retrieve(db, teacher.id, message, context) if _should_retrieve(message, context) else []
        if _is_song_recommendation(message):
            reply, sources, actions = _recommendation_response(db, teacher.id, message, context)
        elif _is_lookup(message):
            reply = _lookup_reply(sources)
            actions = []
        elif _is_lesson_action(message, context):
            source_text = _compact_sources(sources)
            reply = (
                (f"我找到了可参考的资料：{source_text}。" if source_text else "我记下了这次备课方向，目前没有找到可直接引用的历史记录。")
                + "点下面的按钮后，我们会在教案生成页继续核对班级、歌曲和课时，再由你决定是否生成或调整。"
            )
            actions = [{"type": "open_lesson_planner", "label": "带入教案助手"}]
        else:
            retrieval_context = {
                "entry_context": context,
                "retrieved_records": sources,
                "response_style": "温暖自然，先回应本轮问题；不套固定格式，不重复用户原话；只引用检索到的事实。",
            }
            reply = reply_to_lesson_dialogue(
                message,
                [{"role": item.get("role"), "content": (
                    _naturalize_dialogue_answer(str(item.get("content", "")))[:1200]
                    if item.get("role") == "assistant" else str(item.get("content", ""))[:1200]
                )} for item in history[-10:] if isinstance(item, dict) and item.get("role") in {"user", "assistant"}],
                retrieval_context,
            )
            actions = []
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("teaching_assistant_message_failed teacher_id=%s conversation_id=%s", teacher.id, row.id)
        raise HTTPException(status_code=502, detail="这条消息暂时没有处理好，原有对话和资料都已保留；可以稍后重试。") from exc

    user_item = {"role": "user", "content": message, "created_at": datetime.utcnow().isoformat(timespec="seconds")}
    assistant_item = {
        "role": "assistant", "content": reply,
        "sources": sources, "actions": actions,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    history.extend([user_item, assistant_item])
    row.messages_json = json.dumps(history[-200:], ensure_ascii=False)
    if row.title == "新对话":
        row.title = message[:24] + ("…" if len(message) > 24 else "")
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"conversation": _present(row, True), "reply": assistant_item}

