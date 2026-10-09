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
        "pitch_stability": [58, 63, 69, 74, 76, 78, 80, 82, 84, 86],
        "rhythm_regularness": [46, 52, 61, 68, 70, 72, 75, 77, 80, 82],
        "participation": ["参与一般", "参与一般", "参与积极", "参与积极", "参与积极", "参与一般", "参与积极", "参与积极", "参与积极", "参与积极"],
        "cooperation": ["合作一般", "合作一般", "主动合作", "主动合作", "主动合作", "合作一般", "主动合作", "主动合作", "主动合作", "主动合作"],
    },
    "三年级2班": {
        "pitch_stability": [45, 50, 56, 62, 63, 66, 68, 71, 69, 74],
        "rhythm_regularness": [39, 47, 53, 60, 61, 64, 67, 66, 71, 73],
        "participation": ["需要带动", "参与一般", "参与一般", "参与积极", "参与一般", "参与积极", "参与积极", "参与一般", "参与积极", "参与积极"],
        "cooperation": ["需要教师带动", "合作一般", "合作一般", "主动合作", "合作一般", "主动合作", "主动合作", "合作一般", "主动合作", "主动合作"],
    },
    "四年级1班": {
        "pitch_stability": [72, 76, 80, 83, 85, 83, 87, 88, 86, 90],
        "rhythm_regularness": [68, 73, 78, 82, 84, 82, 86, 88, 87, 91],
        "participation": ["参与积极", "参与积极", "参与积极", "参与积极", "参与积极", "参与一般", "参与积极", "参与积极", "参与积极", "参与积极"],
        "cooperation": ["主动合作", "主动合作", "主动合作", "主动合作", "主动合作", "合作一般", "主动合作", "主动合作", "主动合作", "主动合作"],
    },
}

# 每条记录是演示课堂表现，不代表真实课堂测量。
EXTRA_DEMO_SESSIONS = {
    "三年级1班": [
        ("分句换气与句尾收音", "乐句间换气较前次整齐。", "高音处音量上冲，句尾拖长。", "轻声模唱高音，用手势统一收音。", ["听辨乐句结束", "稳定气息"]),
        ("强弱拍与节奏接龙", "多数学生能稳拍并跟随手势换组。", "换组时有人抢拍，弱拍偏重。", "先做两拍身体声势，再轮换领拍。", ["保持恒拍", "区分强弱拍"]),
        ("五声音阶听唱", "小组接唱更连贯。", "相邻音高处偶有滑音。", "将易混音程拆成短句，先听后唱。", ["模唱旋律", "听辨相邻音高"]),
        ("歌词节奏与呼吸", "能按乐句分组歌词并标记呼吸点。", "短句中换气会打断歌词。", "先按节奏朗读，再用手势标呼吸。", ["清晰咬字", "按乐句呼吸"]),
        ("领唱齐唱与音量", "领唱后回到齐唱更均衡。", "领唱音量偏大，后排较弱。", "安排轻声领唱和回应唱，练习聆听。", ["控制音量", "衔接领唱与齐唱"]),
        ("完整演唱与自评", "多数学生能完整演唱并指出稳定乐句。", "结尾收音不齐，少数组节拍略快。", "手势控制速度，让学生说出一项改进。", ["完整演唱", "提出一项改进"]),
    ],
    "三年级2班": [
        ("恒拍模仿与节奏接龙", "示范和同伴带领下更多学生完成四拍模仿。", "独立开始易提前进入，少数不愿领拍。", "先全班齐做，再两人互相提示。", ["跟随稳定拍点", "同伴支持下模仿"]),
        ("短句模唱与音高方向", "能用手势表示旋律上行、下行。", "连续跳进处易滑音，起音依赖提示。", "长句拆成短动机，教师示范后全班回应。", ["判断旋律走向", "模唱短句"]),
        ("歌词朗读与节奏", "小组合作拍出歌词节奏，参与提高。", "切分节奏容易平均分拍，速度渐快。", "先走步定速，再拍手读词，安排同伴提醒。", ["稳定速度", "歌词节奏对应"]),
        ("小组轮唱与倾听", "固定分组后大部分学生愿意接唱。", "临时换组影响秩序，聆听同伴不足。", "保持固定分组，用手势提示轮次。", ["按轮次接唱", "听后回应"]),
        ("节奏稳定与音准", "给拍后能完成短句，出错后愿意再试。", "没有拍点时速度波动，弱声音高不稳。", "用拍手提供恒拍，分层安排跟唱领唱。", ["恒拍支持下演唱", "轻声保持音准"]),
        ("歌曲复习与小组展示", "每组完成展示，更多学生参与歌唱或节奏。", "轮候较长，最后乐句仍需提示。", "缩短轮候，安排全班同步准备和互评。", ["参与展示", "掌握最后乐句进入"]),
    ],
    "四年级1班": [
        ("旋律分句与呼吸", "学生能自主划分乐句并解释呼吸位置。", "个别学生压迫高音，音色变紧。", "加入轻声哼鸣，先保证松弛与句法。", ["划分乐句", "自然完成高音"]),
        ("节奏变奏与合作", "小组能在原节奏上创编并保持拍点。", "速度偏快，变奏后回主题不稳。", "每组只变化一个元素，先说规则再回主题。", ["恒拍创编", "衔接主题变奏"]),
        ("二声部倾听与平衡", "分声部问答演唱，互相倾听较好。", "高声部偶尔过强，低声部被遮盖。", "轮换主导和伴随，用手势控制声部比例。", ["保持声部独立", "平衡主旋律与伴随"]),
        ("地方旋律比较", "能比较节奏情绪并尝试说明判断依据。", "讨论停留在好听与否，音乐要素不足。", "从节奏、音高、速度引用听到的证据。", ["比较旋律", "用音乐要素表达"]),
        ("歌曲结构与编配", "小组能辨认重复乐句并设计简单伴奏。", "伴奏偶尔盖过人声，进入不统一。", "限制音量和密度，由手势统一进入。", ["识别重复乐句", "选择伴奏密度"]),
        ("表现与同伴反馈", "能完整演唱，并对音准、节奏或合作反馈。", "建议有时未指出对应乐句。", "用具体乐句、听到的现象、下次尝试组织反馈。", ["完整表现", "依据证据提出建议"]),
    ],
}

DEMO_SESSION_DATES = [
    datetime(2026, 10, 2, 10, 0), datetime(2026, 10, 3, 10, 0),
    datetime(2026, 10, 5, 10, 0), datetime(2026, 10, 7, 10, 0),
    datetime(2026, 10, 8, 10, 0), datetime(2026, 10, 9, 10, 0),
]


def normalized(value: str) -> str:
    return "".join((value or "").split())


def get_or_create_demo_song(db: Session, teacher: Teacher) -> Song:
    song = db.scalar(
        select(Song)
        .where(Song.name == "茉莉花", Song.owner_teacher_id == teacher.id)
        .order_by(Song.id)
    )
    if song:
        return song
    song = db.scalar(select(Song).where(Song.name == "茉莉花").order_by(Song.id))
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
            for index in range(10):
                sample_number = index + 1
                if (profile.id, sample_number) in seeded_keys:
                    continue
                if sample_number <= 4:
                    taught_at = datetime(2026, 9, 9, 10, 0) + timedelta(days=index * 7)
                    detail = ("歌唱与节奏练习", "演示记录：跟唱练习与节奏活动。",
                              "演示记录：用于展示趋势变化，不代表真实班级情况。",
                              "请用本班真实课堂观察替换演示信息。",
                              ["练习稳定音高与恒拍", "参与小组演唱与合作"])
                else:
                    detail = EXTRA_DEMO_SESSIONS[normalized(spec["name"])][index - 4]
                    taught_at = DEMO_SESSION_DATES[index - 4]
                focus, highlights, problems, improvement, goals = detail
                title = f"【演示记录】《{song.name}》{focus} · 第 {sample_number} 次"
                lesson = LessonPlan(
                    teacher_id=teacher.id,
                    title=title,
                    class_id=profile.id,
                    song_id=song.id,
                    duration_minutes=40,
                    teacher_requirements="数据库中的趋势演示记录；非真实课堂观察。",
                    content_json=json.dumps({
                        "title": title,
                        "summary": f"演示数据：{focus}。不代表真实课堂观察。",
                        "objectives": goals,
                        "timeline": [],
                        "teacher_requirements": "演示数据，非真实课堂观察。",
                        "demo_sample_index": sample_number,
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
                    "goal_observations": goals,
                }
                db.add(Feedback(
                    teacher_id=teacher.id,
                    classroom_record_id=record.id,
                    overall_effect="演示样例",
                    highlights=highlights,
                    problems=problems,
                    improvement=improvement,
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
