import json

from app.core.security import get_current_teacher
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import (
    ClassProfile,
    ClassroomRecord,
    LessonPlan,
    MusicTheory,
    Song,
    Teacher,
    TeachingGame,
    TeachingMistake,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_preview_adjust_save_and_personal_resource(monkeypatch):
    from app.services import lesson_service

    monkeypatch.setattr(lesson_service, "get_settings", lambda: type("Settings", (), {"ai_api_key": ""})())
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        teacher = Teacher(
            username="tester",
            display_name="测试老师",
            school="测试学校",
            password_hash="x",
            password_salt="y",
        )
        db.add(teacher)
        db.flush()
        teacher_id = teacher.id
        db.add_all(
            [
                Song(
                    source_row=2,
                    name="测试歌",
                    region="华南地区",
                    province="广东",
                    mood="欢快",
                    mode="五声",
                    grade="3年级",
                    source="测试",
                    song_type="童谣",
                    range_note="适中",
                    range_score=2,
                    rhythm_score=2,
                    dialect_score=1,
                    difficulty="2星",
                ),
                TeachingGame(
                    category="节奏",
                    name="拍手游戏",
                    personality="活跃",
                    grade="1-4年级",
                    match_condition="节奏",
                    instructions="拍手跟唱",
                ),
                MusicTheory(category="节拍", term="节拍", lower_grade_script="像走路", upper_grade_script="强弱交替"),
                TeachingMistake(category="节奏", problem="拍子不稳", correction="跟随拍手"),
                ClassProfile(
                    teacher_id=teacher_id,
                    name="三年级测试班",
                    grade=3,
                    student_count=25,
                    province="广东",
                    learning_level="中等",
                    activity_level="较高",
                    cooperation="喜欢分组合作",
                    pitch_level="音准不稳定",
                    rhythm_level="节奏偏弱",
                    theory_level="乐理理解较弱",
                    preferred_method="互动与分组合作",
                    common_problems="后半节容易走神",
                    teacher_notes="",
                ),
            ]
        )
        db.commit()
        teacher = db.get(Teacher, teacher_id)

    def override_db():
        with Session(engine) as db:
            yield db

    def override_teacher():
        return teacher

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_teacher] = override_teacher
    try:
        with TestClient(app) as client:
            body = {
                "song_id": 1,
                "class_id": 1,
                "duration_minutes": 40,
                "activity_preference": "互动与分组合作",
                "teacher_requirements": "多分组",
            }
            response = client.post("/api/lessons/generate/stream", json=body)
            assert response.status_code == 200
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert events[-1]["type"] == "complete"
            preview = events[-1]["preview"]
            assert preview["is_saved"] is False
            assert "id" not in preview
            assert preview["content"]["generation_context"]["class_profile"]["student_count"] == 25
            assert preview["content"]["generation_context"]["matched_database_resources"]["game"]["name"] == "拍手游戏"

            adjustment = client.post(
                "/api/lessons/preview/adjust/stream",
                json={"content": preview["content"], "instruction": "增加分组展示"},
            )
            assert adjustment.status_code == 200
            assert "增加分组展示" in adjustment.text

            saved = client.post(
                "/api/lessons/save", json={**body, "generation_mode": "rules", "content": preview["content"]}
            )
            assert saved.status_code == 200
            assert saved.json()["is_saved"] is True
            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(LessonPlan)) == 1
                assert db.scalar(select(func.count()).select_from(ClassroomRecord)) == 1

            resources = client.get("/api/resources/games").json()
            assert len(resources) == 1
            assert resources[0]["scope"] == "system"
            assert resources[0]["editable"] is False
            payload = {key: resources[0][key] for key in ("category", "name", "personality", "grade", "match_condition", "instructions")}
            payload["instructions"] = "先拍两下再演唱"
            created = client.post("/api/resources/games", json=payload)
            assert created.status_code == 201
            assert created.json()["scope"] == "mine"
            assert client.put("/api/resources/games/1", json=payload).status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_song_design_basis_changes_with_song_facts():
    from types import SimpleNamespace
    from app.services.lesson_service import _song_design_basis

    rhythmic = SimpleNamespace(rhythm_score=5, range_score=1, range_note="c1-c2", mood="欢快", song_type="劳动号子", mode="五声音阶")
    lyrical = SimpleNamespace(rhythm_score=1, range_score=5, range_note="a-c2", mood="抒情", song_type="山歌", mode="羽调式")
    first, second = _song_design_basis(rhythmic), _song_design_basis(lyrical)
    assert first["primary"] != second["primary"]
    assert "节奏难度指标：5" in first["facts"]
    assert "a-c2" in second["practice"]
