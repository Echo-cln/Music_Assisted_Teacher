import re

from sqlalchemy.orm import Session

from app.models.entities import ClassProfile, Song
from app.repositories.song_repository import SongRepository

CHINESE_GRADE = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def _number(text: str, default: int = 3) -> int:
    match = re.search(r"[一二三四五六1-6]", text or "")
    if not match:
        return default
    return CHINESE_GRADE.get(match.group(), int(match.group()) if match.group().isdigit() else default)


def recommend_songs(
    db: Session, region: str, class_profile: ClassProfile, limit: int = 3, teacher_id: int | None = None
) -> list[dict]:
    songs = SongRepository(db, teacher_id=teacher_id).list_songs(region=region)
    ranked: list[tuple[int, Song, list[str]]] = []
    for song in songs:
        score = 68
        reasons: list[str] = []
        grade_gap = abs(_number(song.grade) - class_profile.grade)
        score += max(0, 16 - grade_gap * 7)
        if grade_gap == 0:
            reasons.append("年级完全匹配")
        if song.province == class_profile.province:
            score += 8
            reasons.append("与班级所在省份一致")
        if any(word in class_profile.rhythm_level for word in ("弱", "不足")) and song.rhythm_score <= 2:
            score += 4
            reasons.append("节奏难度适合基础强化")
        if any(word in class_profile.pitch_level for word in ("弱", "不稳定")) and song.range_score <= 2:
            score += 4
            reasons.append("音域难度适合目前音准基础")
        difficulty = _number(song.difficulty, 3)
        if "弱" in class_profile.learning_level:
            max_difficulty = 2
        elif "中等" in class_profile.learning_level:
            max_difficulty = 3
        else:
            max_difficulty = 5
        if difficulty <= max_difficulty:
            score += 3
            reasons.append("综合难度适中")
        if song.owner_teacher_id == teacher_id and teacher_id is not None:
            score += 2
            reasons.append("来自我的资源库")
        ranked.append((min(score, 98), song, reasons or ["符合地区和年级基本条件"]))
    ranked.sort(key=lambda item: (-item[0], item[1].source_row or 10**9, item[1].id))
    return [
        {"song": song, "match_score": score, "reason": "；".join(reasons)} for score, song, reasons in ranked[:limit]
    ]
