import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import hash_password  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.session import Session, SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    ClassProfile,
    ClassroomRecord,
    Feedback,
    LessonPlan,
    Song,
    Teacher,
)

CLASS_SPECS = [
    {
        "name": "三年级 1 班", "grade": 3, "student_count": 32, "province": "广东",
        "learning_level": "中等", "activity_level": "较高", "cooperation": "喜欢分组合作",
        "pitch_level": "音准不稳定", "rhythm_level": "节奏偏弱", "theory_level": "乐理理解较弱",
        "preferred_method": "互动与分组合作", "common_problems": "后半节容易走神", "teacher_notes": "适合少讲多练。",
    },
    {
        "name": "三年级 2 班", "grade": 3, "student_count": 29, "province": "广东",
        "learning_level": "基础较弱", "activity_level": "中等", "cooperation": "需要教师带动",
        "pitch_level": "音准基础一般", "rhythm_level": "恒拍感不足", "theory_level": "乐理理解较弱",
        "preferred_method": "唱游与律动", "common_problems": "不太敢开口", "teacher_notes": "需要更多示范和正向鼓励。",
    },
    {
        "name": "四年级 1 班", "grade": 4, "student_count": 35, "province": "广西",
        "learning_level": "中等偏上", "activity_level": "较高", "cooperation": "合作意识较强",
        "pitch_level": "音准较稳定", "rhythm_level": "节奏基础较好", "theory_level": "能理解基础术语",
        "preferred_method": "合作创编", "common_problems": "学生差异较大", "teacher_notes": "适合分层任务与小组展示。",
    },
]

TREND_SERIES = {
    "三年级1班": {
        "pitch_stability": [58, 63, 69, 74],
        "rhythm_regularness": [46, 52, 61, 68],
        "participation": ["参与一般", "参与一般", "参与积极", "参与积极"],
        "cooperation": ["合作一般", "合作一般", "主动合作", "主动合作"],
    },
    "三年级2班": {
        "pitch_stability": [45, 50, 56, 62],
        "rhythm_regularness": [39, 47, 53, 60],
        "participation": ["需要带动", "参与一般", "参与一般", "参与积极"],
        "cooperation": ["需要教师带动", "合作一般", "合作一般", "主动合作"],
    },
    "四年级1班": {
        "pitch_stability": [72, 76, 80, 83],
        "rhythm_regularness": [68, 73, 78, 82],
        "participation": ["参与积极", "参与积极", "参与积极", "参与积极"],
        "cooperation": ["主动合作", "主动合作", "主动合作", "主动合作"],
    },
}


def normalized(value: str) -> str:
    return "".join((value or "").split())


def get_or_create_demo_song(db: Session, teacher: Teacher) -> Song:
    song = db.scalar(select(Song).where(Song.name == "茉莉花"))
    if song:
        return song
    song = db.scalar(select(Song).order_by(Song.id).limit(1))
    if song:
        return song
    song = Song(
        owner_teacher_id=teacher.id,
        name="趋势演示歌曲",
        region="华南地区",
        province="广东",
        mood="舒缓、抒情",
        mode="五声音阶",
        grade="三至四年级",
        source="系统演示样例",
        song_type="演示歌曲",
        range_note="中音区",
        range_score=55,
        rhythm_score=55,
        dialect_score=50,
        difficulty="简单",
    )
    db.add(song)
    db.flush()
    return song


def seed() -> tuple[int, int]:
    init_db()
    created_classes = 0
    created_feedback = 0
    with SessionLocal() as db:
        teacher = db.scalar(select(Teacher).where(Teacher.username == "demo"))
        if not teacher:
            password_hash, salt = hash_password("demo123456")
            teacher = Teacher(
                username="demo",
                display_name="林老师",
                school="乡音智谱演示学校",
                password_hash=password_hash,
                password_salt=salt,
            )
            db.add(teacher)
            db.flush()

        existing_classes = db.scalars(
            select(ClassProfile).where(ClassProfile.teacher_id == teacher.id)
        ).all()
        class_by_name = {normalized(item.name): item for item in existing_classes}
        for spec in CLASS_SPECS:
            key = normalized(spec["name"])
            if key not in class_by_name:
                profile = ClassProfile(teacher_id=teacher.id, **spec)
                db.add(profile)
                db.flush()
                class_by_name[key] = profile
                created_classes += 1

        song = get_or_create_demo_song(db, teacher)
        seeded_keys: set[tuple[int, int]] = set()
        existing_feedback = db.scalars(
            select(Feedback).where(Feedback.teacher_id == teacher.id)
        ).all()
        for feedback in existing_feedback:
            try:
                analysis = json.loads(feedback.analysis_json or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if not analysis.get("demo_trend_sample"):
                continue
            record = db.get(ClassroomRecord, feedback.classroom_record_id)
            sample_index = analysis.get("demo_trend_sample_index")
            if record and isinstance(sample_index, int):
                seeded_keys.add((record.class_id, sample_index))

        for spec in CLASS_SPECS:
            profile = class_by_name[normalized(spec["name"])]
            series = TREND_SERIES[normalized(spec["name"])]
            for index in range(4):
                sample_number = index + 1
                if (profile.id, sample_number) in seeded_keys:
                    continue
                taught_at = datetime(2026, 9, 9, 10, 0) + timedelta(days=index * 7)
                title = f"【演示记录】《{song.name}》歌唱与节奏练习 · 第 {sample_number} 次"
                lesson = LessonPlan(
                    teacher_id=teacher.id,
                    title=title,
                    class_id=profile.id,
                    song_id=song.id,
                    duration_minutes=40,
                    teacher_requirements="数据库中的趋势演示记录；非真实课堂观察。",
                    content_json=json.dumps({
                        "title": title,
                        "summary": "用于展示班级学情趋势图的数据样例，不代表真实课堂结果。",
                        "objectives": ["练习稳定音高与恒拍", "参与小组演唱与合作"],
                        "timeline": [],
                        "teacher_requirements": "演示数据，非真实课堂观察。",
                    }, ensure_ascii=False),
                    generation_mode="demo",
                    created_at=taught_at,
                )
                db.add(lesson)
                db.flush()
                record = ClassroomRecord(
                    teacher_id=teacher.id,
                    class_id=profile.id,
                    lesson_plan_id=lesson.id,
                    taught_at=taught_at,
                    status="feedback_completed",
                    created_at=taught_at,
                )
                db.add(record)
                db.flush()
                class_observations = {
                    key: values[index] for key, values in series.items()
                }
                analysis = {
                    "demo_trend_sample": True,
                    "demo_trend_sample_index": sample_number,
                    "demo_notice": "数据库演示记录，不代表真实课堂观察。",
                    "class_observations": class_observations,
                }
                db.add(Feedback(
                    teacher_id=teacher.id,
                    classroom_record_id=record.id,
                    overall_effect="演示样例",
                    highlights="演示记录：跟唱练习与节奏活动。",
                    problems="演示记录：用于展示趋势变化，不代表真实班级情况。",
                    improvement="请用本班真实课堂观察替换演示信息。",
                    audio_summary="未关联真实录音；音准与节奏分值为演示观察值。",
                    analysis_json=json.dumps(analysis, ensure_ascii=False),
                    created_at=taught_at,
                ))
                created_feedback += 1

        db.commit()
    return created_classes, created_feedback


if __name__ == "__main__":
    classes_added, records_added = seed()
    print(
        "演示数据已写入数据库："
        f"新增班级 {classes_added} 个，新增趋势反馈 {records_added} 条；"
        "重复运行不会重复添加。"
    )
    print("演示账号：demo / demo123456")
