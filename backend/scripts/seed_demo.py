import sys
from pathlib import Path

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import hash_password  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.entities import ClassProfile, Teacher  # noqa: E402


def seed() -> None:
    init_db()
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
        if db.scalar(select(func.count()).select_from(ClassProfile).where(ClassProfile.teacher_id == teacher.id)):
            db.commit()
            return
        db.add_all(
            [
                ClassProfile(
                    teacher_id=teacher.id,
                    name="三年级 1 班",
                    grade=3,
                    student_count=32,
                    province="广东",
                    learning_level="中等",
                    activity_level="较高",
                    cooperation="喜欢分组合作",
                    pitch_level="音准不稳定",
                    rhythm_level="节奏偏弱",
                    theory_level="乐理理解较弱",
                    preferred_method="互动与分组合作",
                    common_problems="后半节容易走神",
                    teacher_notes="适合少讲多练。",
                ),
                ClassProfile(
                    teacher_id=teacher.id,
                    name="三年级 2 班",
                    grade=3,
                    student_count=29,
                    province="广东",
                    learning_level="基础较弱",
                    activity_level="中等",
                    cooperation="需要教师带动",
                    pitch_level="音准基础一般",
                    rhythm_level="恒拍感不足",
                    theory_level="乐理理解较弱",
                    preferred_method="唱游与律动",
                    common_problems="不太敢开口",
                    teacher_notes="需要更多示范和正向鼓励。",
                ),
                ClassProfile(
                    teacher_id=teacher.id,
                    name="四年级 1 班",
                    grade=4,
                    student_count=35,
                    province="广西",
                    learning_level="中等偏上",
                    activity_level="较高",
                    cooperation="合作意识较强",
                    pitch_level="音准较稳定",
                    rhythm_level="节奏基础较好",
                    theory_level="能理解基础术语",
                    preferred_method="合作创编",
                    common_problems="学生差异较大",
                    teacher_notes="适合分层任务与小组展示。",
                ),
            ]
        )
        db.commit()


if __name__ == "__main__":
    seed()
    print("演示账号与班级已初始化：demo / demo123456")
