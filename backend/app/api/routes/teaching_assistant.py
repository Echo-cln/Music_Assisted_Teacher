from __future__ import annotations

import json
import logging
import re
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
from app.services.ai_provider import reply_to_lesson_dialogue
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


def _present(row: AssistantConversation, include_messages: bool = False) -> dict:
    result = {
        "id": row.id,
        "title": row.title,
        "context": _json(row.context_json, {}),
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else None,
    }
    if include_messages:
        result["messages"] = _json(row.messages_json, [])
    return result


def _terms(query: str) -> list[str]:
    text = query or ""
    values = re.findall(r"《[^》]{1,40}》|[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", text)
    tokens: list[str] = []
    for value in values:
        value = value.strip().strip("《》")
        if not value:
            continue
        tokens.append(value)
        # Long Chinese runs otherwise become one unusable SQL substring. Add
        # known musical terms and overlapping bigrams to make natural queries searchable.
        tokens.extend(term for term in DOMAIN_TERMS if term in value)
        chinese = re.sub(r"[^\u4e00-\u9fff]", "", value)
        if len(chinese) > 5:
            tokens.extend(chinese[index:index + 2] for index in range(len(chinese) - 1))
    seen: list[str] = []
    for value in tokens:
        if value not in STOP_WORDS and len(value) >= 2 and value not in seen:
            seen.append(value)
    # Keep SQL predicates bounded; specific titles and known domain terms come first.
    return seen[:16]


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
            records.append(_citation(
                "当前教案", plan.title,
                f"歌曲：《{song.name}》；班级：{profile.name if profile else '未指定'}；课时：{plan.duration_minutes}分钟；正文：{plan.content_json[:650]}",
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
            records.append(_citation(
                "当前课堂反馈", f"{profile.name} · 《{song.name}》",
                f"课堂亮点：{feedback.highlights}；存在问题：{feedback.problems}；下次改进：{feedback.improvement}；音频摘要：{feedback.audio_summary}；目标观察：{feedback.analysis_json}",
                feedback.id, "feedback", feedback.created_at,
            ))
    audio_id = context.get("audio_analysis_id")
    if audio_id:
        row = db.execute(select(AudioAnalysis, Song).join(Song, Song.id == AudioAnalysis.song_id).where(
            AudioAnalysis.id == int(audio_id), AudioAnalysis.teacher_id == teacher_id
        )).first()
        if row:
            analysis, song = row
            records.append(_citation("当前音频分析", f"《{song.name}》音频分析", analysis.result_json[:700], analysis.id, "audio", analysis.created_at))

    wants_class_context = bool(class_id) or any(word in message for word in ("班级", "画像", "学生", "课堂反馈", "这个班"))
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
    if terms:
        condition = _matches([LessonPlan.title, LessonPlan.teacher_requirements, LessonPlan.content_json, Song.name], terms)
        if condition is not None:
            lesson_stmt = lesson_stmt.where(condition)
    lesson_rows = db.execute(lesson_stmt.order_by(LessonPlan.created_at.desc()).limit(5)).all()
    for plan, song, profile in lesson_rows:
        content = _json(plan.content_json, {})
        summary = content.get("summary", "") if isinstance(content, dict) else ""
        records.append(_citation(
            "历史教案", plan.title,
            f"歌曲：《{song.name}》；班级：{profile.name if profile else '未指定'}；"
            f"课时：{plan.duration_minutes}分钟；摘要：{summary or plan.teacher_requirements}",
            plan.id, "lessons", plan.created_at,
        ))

    feedback_stmt = select(Feedback, ClassroomRecord, LessonPlan, ClassProfile, Song).join(
        ClassroomRecord, ClassroomRecord.id == Feedback.classroom_record_id
    ).join(LessonPlan, LessonPlan.id == ClassroomRecord.lesson_plan_id).join(
        ClassProfile, ClassProfile.id == ClassroomRecord.class_id
    ).join(Song, Song.id == LessonPlan.song_id).where(Feedback.teacher_id == teacher_id)
    if class_id:
        feedback_stmt = feedback_stmt.where(ClassroomRecord.class_id == int(class_id))
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
        records.append(_citation(
            "课堂反馈", f"{profile.name} · 《{song.name}》",
            f"日期：{record.taught_at or feedback.created_at}；课堂亮点：{feedback.highlights}；"
            f"存在问题：{feedback.problems}；下次改进：{feedback.improvement}；"
            f"音频摘要：{feedback.audio_summary}；目标观察：{feedback.analysis_json}",
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
        records.append(_citation(
            "教案历史版本", f"{plan.title} · 第{revision.revision_number}版",
            f"歌曲：《{song.name}》；班级：{profile.name if profile else '未指定'}；版本内容：{revision.content_json[:500]}",
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
            detail = "；".join(f"{name}：{getattr(row, name)}" for name in field_names)
            records.append(_citation(label, getattr(row, "name", getattr(row, "term", getattr(row, "problem", label))), detail, row.id, route_name))

    audio_stmt = select(AudioAnalysis, Song).join(Song, Song.id == AudioAnalysis.song_id).where(
        AudioAnalysis.teacher_id == teacher_id
    )
    if class_id:
        audio_stmt = audio_stmt.outerjoin(
            ClassroomRecord, ClassroomRecord.id == AudioAnalysis.classroom_record_id
        ).where(ClassroomRecord.class_id == int(class_id))
    if terms:
        condition = _matches([Song.name, AudioAnalysis.result_json, AudioAnalysis.method_version], terms)
        if condition is not None:
            audio_stmt = audio_stmt.where(condition)
    for row, song in db.execute(audio_stmt.order_by(AudioAnalysis.created_at.desc()).limit(4)).all():
        result = _json(row.result_json, {})
        scores = result.get("scores", {}) if isinstance(result, dict) else {}
        records.append(_citation(
            "音频分析", f"《{song.name}》音频分析",
            f"分析方式：{row.method_version}；分析指标：{json.dumps(scores, ensure_ascii=False)}；"
            f"建议：{'；'.join(result.get('suggestions', [])[:3]) if isinstance(result, dict) else ''}",
            row.id, "audio", row.created_at,
        ))

    asset_stmt = select(AudioAsset, Song, ClassroomRecord).join(Song, Song.id == AudioAsset.song_id).outerjoin(
        ClassroomRecord, ClassroomRecord.id == AudioAsset.classroom_record_id
    ).where(AudioAsset.teacher_id == teacher_id)
    if class_id:
        asset_stmt = asset_stmt.where(ClassroomRecord.class_id == int(class_id))
    if terms:
        condition = _matches([AudioAsset.original_filename, AudioAsset.asset_type, Song.name], terms)
        if condition is not None:
            asset_stmt = asset_stmt.where(condition)
    for asset, song, record in db.execute(asset_stmt.order_by(AudioAsset.created_at.desc()).limit(4)).all():
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
        records.append(_citation(
            "乐器音色包", item.display_name,
            f"文件：{item.original_filename}；预设：{item.preset_name}；乐器：{item.instruments_json[:300]}；大小：{item.file_size}字节。",
            item.id, "workbench", item.updated_at,
        ))

    arrangement_stmt = select(ArrangementProject).where(ArrangementProject.teacher_id == teacher_id)
    if terms:
        condition = _matches([ArrangementProject.title, ArrangementProject.style, ArrangementProject.arrangement_json], terms)
        if condition is not None:
            arrangement_stmt = arrangement_stmt.where(condition)
    for row in db.scalars(arrangement_stmt.order_by(ArrangementProject.updated_at.desc()).limit(4)).all():
        arrangement = _json(row.arrangement_json, {})
        instruments = arrangement.get("instruments", []) if isinstance(arrangement, dict) else []
        records.append(_citation(
            "编曲工程", row.title,
            f"速度：{row.tempo} BPM；风格：{row.style}；已保存旋律音符：{len(_json(row.melody_json, []))}；"
            f"编曲配置摘要：{json.dumps(instruments, ensure_ascii=False)[:300]}",
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
    diverse = []
    for item in records:
        kind = item["kind"]
        if counts.get(kind, 0) >= 3:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        diverse.append(item)
        if len(diverse) >= 20:
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
    for item in records[:6]:
        lines.append(f"• {item['label']}（{item['kind']}）：{item['detail'][:150]}")
    return "\n".join(lines)


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
            source_text = "\n".join(f"{s['kind']}｜{s['label']}：{s['detail']}" for s in sources[:10])
            reply = (
                "我先把相关资料找出来了。"
                + (f"目前能参考：{source_text[:900]}。" if source_text else "目前没有检索到对应的历史教案或课堂反馈。")
                + "你确认后，我可以把这些信息带到教案助手继续生成或调整；这一步不会直接改动已有教案。"
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
                [{"role": item.get("role"), "content": item.get("content", "")} for item in history[-10:]],
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

