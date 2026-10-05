import json
import re
from copy import deepcopy
from collections.abc import Iterator

from json_repair import repair_json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    ClassProfile,
    ClassroomRecord,
    LessonPlan,
    MusicTheory,
    Song,
    TeachingGame,
    TeachingMistake,
)
from app.services.ai_provider import stream_adjusted_lesson_json, stream_lesson_json


def _visible(model, teacher_id: int):
    return or_(model.owner_teacher_id.is_(None), model.owner_teacher_id == teacher_id)


def _knowledge(db: Session, song: Song, profile: ClassProfile | None, teacher_id: int) -> dict:
    grade = profile.grade if profile else 3
    games = list(db.scalars(select(TeachingGame).where(_visible(TeachingGame, teacher_id))).all())
    theories = list(db.scalars(select(MusicTheory).where(_visible(MusicTheory, teacher_id))).all())
    mistakes = list(db.scalars(select(TeachingMistake).where(_visible(TeachingMistake, teacher_id))).all())
    games.sort(key=lambda item: item.owner_teacher_id == teacher_id, reverse=True)
    theories.sort(key=lambda item: item.owner_teacher_id == teacher_id, reverse=True)
    mistakes.sort(key=lambda item: item.owner_teacher_id == teacher_id, reverse=True)
    if not games or not theories or not mistakes:
        raise ValueError("教学知识库不完整，请先导入音乐游戏、乐理和易错纠正资源")

    traits = " ".join(
        value
        for value in (
            profile.activity_level if profile else "",
            profile.cooperation if profile else "",
            profile.preferred_method if profile else "",
            profile.rhythm_level if profile else "",
        )
    )

    def game_score(game: TeachingGame) -> int:
        score = 0
        grade_numbers = [int(value) for value in re.findall(r"[1-6]", game.grade or "")]
        if grade_numbers and min(grade_numbers) <= grade <= max(grade_numbers):
            score += 8
        condition = (game.match_condition or "") + " " + (game.personality or "")
        for keyword in ("节奏", "合作", "互动", "律动", "演唱"):
            if keyword in condition and keyword in traits:
                score += 3
        if "弱" in (profile.rhythm_level if profile else "") and "节奏" in condition:
            score += 5
        if song.province in condition or song.region in condition:
            score += 4
        if "欢快" in song.mood and any(word in condition for word in ("欢快", "活跃")):
            score += 3
        if "弱" in (profile.pitch_level if profile else "") and "音准" in condition:
            score += 3
        if game.owner_teacher_id == teacher_id:
            score += 1
        return score

    game = max(games, key=game_score)
    focus = "节奏" if profile and any(word in profile.rhythm_level for word in ("弱", "不足")) else "音准"
    theory_keyword = "节拍" if focus == "节奏" else "旋律"
    theory = next((item for item in theories if theory_keyword in (item.category or "")), None)
    theory = theory or next((item for item in theories if "节拍" in (item.category or "")), None) or theories[0]
    mistake = next((item for item in mistakes if focus in (item.category or "")), None) or mistakes[0]
    return {
        "game": {
            "name": game.name,
            "category": game.category,
            "grade": game.grade,
            "match_condition": game.match_condition,
            "instructions": game.instructions,
        },
        "theory": {
            "term": theory.term,
            "script": theory.lower_grade_script if grade <= 3 else theory.upper_grade_script,
        },
        "mistake": {"problem": mistake.problem, "correction": mistake.correction},
    }


def _local_content(
    song: Song, profile: ClassProfile | None, duration: int, activity: str, requirements: str, knowledge: dict
) -> dict:
    class_name = profile.name if profile else "通用班级"
    rhythm = profile.rhythm_level if profile else "节奏基础一般"
    pitch = profile.pitch_level if profile else "音准基础一般"
    parts = [max(3, round(duration * x)) for x in (0.1, 0.14, 0.32, 0.26)]
    parts.append(duration - sum(parts))
    return {
        "title": f"《{song.name}》班级适配音乐课",
        "summary": {
            "class_name": class_name,
            "duration": duration,
            "region": f"{song.region} · {song.province}",
            "difficulty": song.difficulty,
            "range_note": song.range_note,
        },
        "objectives": [
            f"能用自然、稳定的声音演唱《{song.name}》主要乐句，表现“{song.mood}”的情绪。",
            f"能在律动、拍手或小组接唱中保持基本节拍，改善“{rhythm}”。",
            f"了解歌曲与{song.province}地方文化的联系，并说出一个听到的音乐特点。",
        ],
        "key_points": f"依据{song.range_note}分句学唱，用模唱和声势活动解决音准、节奏问题。",
        "difficulties": f"针对“{pitch}”情况，避免长时间抽象讲解，先听、先唱、再总结。",
        "preparation": "歌曲音频或教师范唱、黑板/投影、节奏卡片；无乐器时使用拍手、跺脚和桌面敲击。",
        "timeline": [
            {
                "minutes": parts[0],
                "stage": "情境导入",
                "teacher": f"用{song.province}生活场景或地方文化线索引出歌曲。",
                "students": "聆听并用动作或词语表达感受。",
            },
            {
                "minutes": parts[1],
                "stage": knowledge["game"]["name"],
                "teacher": knowledge["game"]["instructions"],
                "students": "以小组形式完成节奏或声音模仿。",
            },
            {
                "minutes": parts[2],
                "stage": "分句学唱",
                "teacher": "先用 lu 模唱旋律，再填歌词；每两句停一次处理音准、咬字和换气。",
                "students": "听、模仿、互听；基础较弱者先唱骨干音。",
            },
            {
                "minutes": parts[3],
                "stage": "难点练习",
                "teacher": knowledge["mistake"]["correction"],
                "students": "轮换练习并记录最容易出错的一句。",
            },
            {
                "minutes": parts[4],
                "stage": "展示评价",
                "teacher": "按节拍稳定、声音自然、合作完成三项标准评价。",
                "students": "小组展示并说出一个优点和一个下次目标。",
            },
        ],
        "theory_explanation": knowledge["theory"],
        "mistake_practice": knowledge["mistake"],
        "differentiation": [
            "基础层：能跟随教师稳定唱完主要乐句。",
            "提高层：加入声势伴奏或担任小组领唱。",
            "支持策略：音准不稳者先轻声模唱，再逐步扩大到全班。",
        ],
        "assessment": "学生完成三颗星自评：节拍稳定、声音自然、合作完成。教师记录最容易出错的乐句。",
        "activity_preference": activity,
        "teacher_requirements": requirements,
        "generation_context": {
            "selected_song_from_database": {
                "name": song.name,
                "region": song.region,
                "province": song.province,
                "grade": song.grade,
                "difficulty": song.difficulty,
                "range_note": song.range_note,
                "source": song.source,
                "song_type": song.song_type,
                "mode": song.mode,
                "rhythm_score": song.rhythm_score,
                "mood": song.mood,
            },
            "class_profile": {
                "name": class_name,
                "grade": profile.grade if profile else None,
                "student_count": profile.student_count if profile else None,
                "province": profile.province if profile else None,
                "learning_level": profile.learning_level if profile else None,
                "activity_level": profile.activity_level if profile else None,
                "cooperation": profile.cooperation if profile else None,
                "pitch_level": pitch,
                "rhythm_level": rhythm,
                "theory_level": profile.theory_level if profile else None,
                "preferred_method": profile.preferred_method if profile else None,
                "common_problems": profile.common_problems if profile else None,
                "teacher_notes": profile.teacher_notes if profile else None,
            },
            "matched_database_resources": knowledge,
        },
    }


def build_base_preview(
    db: Session,
    song: Song,
    profile: ClassProfile | None,
    duration: int,
    activity: str,
    requirements: str,
    teacher_id: int,
) -> dict:
    return _local_content(song, profile, duration, activity, requirements, _knowledge(db, song, profile, teacher_id))


def _chunks(base: dict, generation_strategy: str = "deep") -> tuple[str, Iterator[str]]:
    settings = get_settings()
    configured = bool(settings.ai_fast_api_key or settings.ai_api_key) if generation_strategy == "fast" else bool(settings.ai_api_key)
    if configured:
        return "ai", stream_lesson_json(base, generation_strategy=generation_strategy)
    content = json.dumps(base, ensure_ascii=False)
    return "rules", (content[i : i + 120] for i in range(0, len(content), 120))


def _adjustment_chunks(content: dict, instruction: str) -> tuple[str, Iterator[str]]:
    if get_settings().ai_api_key:
        return "ai", stream_adjusted_lesson_json(content, instruction)
    adjusted = json.loads(json.dumps(content, ensure_ascii=False))
    adjusted["teacher_requirements"] = instruction
    raw = json.dumps(adjusted, ensure_ascii=False)
    return "rules", (raw[i : i + 120] for i in range(0, len(raw), 120))


def _validated_content(raw: str, base: dict) -> dict:
    # 兼容少数模型仍包裹 Markdown 代码围栏或附带一句前言，提取完整对象后再校验。
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.split("\n", 1)[1] if "\n" in normalized else ""
        normalized = normalized.rsplit("```", 1)[0].strip()
    start, end = normalized.find("{"), normalized.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回完整 JSON 教案，请稍后重试或检查模型服务")
    candidate = normalized[start : end + 1]
    try:
        content = json.loads(candidate)
    except json.JSONDecodeError as exc:
        # 只修复已经完整返回的对象中漏逗号、转义或尾逗号等格式瑕疵；
        # 截断内容仍会被拒绝，不会伪造或补写教学内容。
        try:
            content = repair_json(candidate, return_objects=True)
        except Exception as repair_exc:
            raise ValueError(
                f"模型返回的 JSON 无法解析（第 {exc.lineno} 行、第 {exc.colno} 列）：{exc.msg}。本次结果未保存，请重试。"
            ) from repair_exc
    if not isinstance(content, dict):
        raise ValueError("模型没有返回教案对象")
    generated = content
    # 兼容兼容接口常见的包装。部分网关会把本应是 JSON 对象的 content 再包成
    # JSON 字符串；此前会把它误判为“缺少全部字段”。只解包模型实际返回的 JSON，
    # 不能从规则骨架补字段后伪装为成功。
    for wrapper in ("enhancement", "lesson", "data", "content", "教案", "result"):
        wrapped = content.get(wrapper)
        if isinstance(wrapped, dict):
            generated = wrapped
            break
        if isinstance(wrapped, str) and wrapped.lstrip().startswith("{"):
            try:
                parsed = json.loads(wrapped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                generated = parsed
                break
    required_fields = (
        "title", "objectives", "key_points", "difficulties", "preparation",
        "timeline", "theory_explanation", "mistake_practice", "differentiation", "assessment",
    )
    missing = [field for field in required_fields if not generated.get(field)]
    if missing:
        present = ", ".join(sorted(generated.keys())) or "无"
        raise ValueError(
            f"模型返回的教案缺少必要字段：{', '.join(missing)}（实际字段：{present}）；"
            "本次深度结果未保存，请重试"
        )
    wrong_types = [field for field in required_fields if not isinstance(generated.get(field), type(base.get(field)))]
    if wrong_types:
        raise ValueError(f"模型返回的教案字段类型不正确：{', '.join(wrong_types)}；本次深度结果未保存，请重试")
    base_timeline_for_check = base.get("timeline") or []
    timeline = generated.get("timeline") or []
    if len(timeline) != len(base_timeline_for_check):
        raise ValueError(f"模型返回的 timeline 项数为 {len(timeline)}，应为 {len(base_timeline_for_check)}；本次深度结果未保存，请重试")
    incomplete_timeline = [
        str(index + 1) for index, item in enumerate(timeline)
        if not isinstance(item, dict) or not isinstance(item.get("teacher"), str) or not item.get("teacher").strip()
        or not isinstance(item.get("students"), str) or not item.get("students").strip()
    ]
    if incomplete_timeline:
        raise ValueError(f"模型返回的第 {', '.join(incomplete_timeline)} 个课堂环节缺少教师或学生任务；本次深度结果未保存，请重试")
    content = deepcopy(base)
    for field in (
        "title",
        "objectives",
        "key_points",
        "difficulties",
        "preparation",
        "timeline",
        "theory_explanation",
        "mistake_practice",
        "differentiation",
        "assessment",
    ):
        value = generated.get(field)
        if isinstance(value, type(content.get(field))) and value:
            content[field] = value

    # 课堂流程的阶段、时长由规则层根据课时生成，不能被模型删减或改写。
    # 模型只可增强同一位置的教师、学生活动；若个别项生成不完整，则保留骨架内容。
    base_timeline = base.get("timeline")
    if base_timeline:
        enhanced_timeline = []
        for index, base_item in enumerate(base_timeline):
            raw_timeline = generated.get("timeline", [])
            generated_item = raw_timeline[index] if isinstance(raw_timeline, list) and index < len(raw_timeline) else {}
            if not isinstance(generated_item, dict):
                generated_item = {}
            item = dict(base_item)
            for field in ("teacher", "students"):
                value = generated_item.get(field)
                if isinstance(value, str) and value.strip():
                    item[field] = value.strip()
            enhanced_timeline.append(item)
        content["timeline"] = enhanced_timeline
    content["summary"] = base["summary"]
    if base.get("generation_context"):
        content["generation_context"] = base["generation_context"]
    if base.get("activity_preference") is not None:
        content["activity_preference"] = base.get("activity_preference")
    if base.get("teacher_requirements") is not None:
        content["teacher_requirements"] = base.get("teacher_requirements")
    return content


def stream_preview(
    db: Session,
    song: Song,
    profile: ClassProfile | None,
    duration: int,
    activity: str,
    requirements: str,
    teacher_id: int,
    generation_strategy: str = "deep",
) -> Iterator[tuple[str, object]]:
    base = build_base_preview(db, song, profile, duration, activity, requirements, teacher_id)
    mode, pieces = _chunks(base, generation_strategy)
    yield "start", mode
    collected = []
    for piece in pieces:
        collected.append(piece)
        yield "delta", piece
    raw = "".join(collected).strip()
    if not raw:
        raise ValueError("模型未返回可解析的教案正文，请检查模型服务配置后重试")
    content = _validated_content(raw, base)
    yield "complete", {"content": content, "generation_mode": mode}


def stream_preview_adjustment(content: dict, instruction: str) -> Iterator[tuple[str, object]]:
    mode, pieces = _adjustment_chunks(content, instruction)
    yield "start", mode
    collected = []
    for piece in pieces:
        collected.append(piece)
        yield "delta", piece
    base = deepcopy(content)
    base["teacher_requirements"] = instruction
    adjusted = _validated_content("".join(collected), base)
    adjusted["teacher_requirements"] = instruction
    adjusted.setdefault("adjustment_history", []).append(instruction)
    yield "complete", {"content": adjusted, "generation_mode": mode}


def _save_plan(
    db: Session,
    song: Song,
    profile: ClassProfile | None,
    duration: int,
    requirements: str,
    content: dict,
    mode: str,
    teacher_id: int,
) -> LessonPlan:
    plan = LessonPlan(
        teacher_id=teacher_id,
        title=content.get("title", f"《{song.name}》音乐课"),
        class_id=profile.id if profile else None,
        song_id=song.id,
        duration_minutes=duration,
        teacher_requirements=requirements,
        content_json=json.dumps(content, ensure_ascii=False),
        generation_mode=mode,
    )
    db.add(plan)
    db.flush()
    if profile:
        db.add(
            ClassroomRecord(
                teacher_id=teacher_id,
                class_id=profile.id,
                lesson_plan_id=plan.id,
                status="planned",
            )
        )
    db.commit()
    db.refresh(plan)
    return plan


def save_preview(
    db: Session,
    song: Song,
    profile: ClassProfile | None,
    duration: int,
    requirements: str,
    content: dict,
    mode: str,
    teacher_id: int,
) -> LessonPlan:
    validated = _validated_content(
        json.dumps(content, ensure_ascii=False),
        {
            "summary": content.get("summary", {}),
            "generation_context": content.get("generation_context"),
            "activity_preference": content.get("activity_preference"),
            "teacher_requirements": requirements,
        },
    )
    return _save_plan(db, song, profile, duration, requirements, validated, mode, teacher_id)


def serialize_preview(song: Song, profile: ClassProfile | None, duration: int, content: dict, mode: str) -> dict:
    return {
        "class_id": profile.id if profile else None,
        "class_name": profile.name if profile else "通用模式",
        "song_id": song.id,
        "song_name": song.name,
        "duration_minutes": duration,
        "generation_mode": mode,
        "content": content,
        "is_saved": False,
    }


def serialize_plan(plan: LessonPlan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "class_id": plan.class_id,
        "class_name": plan.class_profile.name if plan.class_profile else "通用模式",
        "song_id": plan.song_id,
        "song_name": plan.song.name,
        "duration_minutes": plan.duration_minutes,
        "generation_mode": plan.generation_mode,
        "content": json.loads(plan.content_json),
        "created_at": plan.created_at.strftime("%Y-%m-%d %H:%M"),
        "is_saved": True,
    }
