import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.db.session import Base
from app.models.entities import ArrangementProject, ClassProfile, ClassroomRecord, Feedback, LessonPlan, Song
from fastapi import HTTPException

from app.api.routes.feedback import _audio_link_mismatch, _validate_audio_link
from app.api.routes.teaching_assistant import _analysis_detail, _is_lesson_action, _is_lookup, _plain, _present, _retrieve, _terms
from app.services.ai_provider import _naturalize_dialogue_answer


def test_intent_guards_keep_lookup_separate_from_lesson_actions():
    assert _is_lookup("帮我找一下四年级1班之前的教案")
    assert not _is_lesson_action("先解释为什么安排节奏接龙，不要改教案")
    assert _is_lesson_action("根据这条课堂反馈调整教案", {"type": "feedback"})
    assert "茉莉花" in _terms("请找《茉莉花》节奏练习的历史教案")
    assert "古筝" in _terms("四年级1班想找古筝编曲")
    assert "class_name" not in _plain("{'class_name': '三年级1班', 'duration': 40}")


def test_assistant_formats_structured_model_output_as_readable_chinese():
    raw = "目前能参考：{'class_name': '三年级1班', 'duration_minutes': 40, 'teacher_requirements': '多互动'}"
    formatted = _naturalize_dialogue_answer(raw)
    assert "{'class_name'" not in formatted
    assert "班级：三年级1班" in formatted
    assert "课时：40" in formatted
    assert "备课要求：多互动" in formatted
    detail = _analysis_detail('{"analysis_mode_label":"课堂录音","scores":{"pitch_stability":82}}')
    assert "课堂录音" in detail and "音高稳定 82分" in detail
    assert "scores" not in detail


def test_existing_conversation_history_is_cleaned_before_display():
    row = SimpleNamespace(
        id=1, title="旧对话", context_json="{}", messages_json=json.dumps([{
            "role": "assistant", "content": "班级资料：{'class_name': '三年级1班', 'duration_minutes': 40}",
            "sources": [{"kind": "班级画像", "label": "三年级1班", "detail": "{'class_name': '三年级1班'}"}],
        }], ensure_ascii=False), created_at=None, updated_at=None,
    )
    message = _present(row, True)["messages"][0]
    assert "{'class_name'" not in message["content"]
    assert message["sources"][0]["label"] == "三年级1班"
    assert len(message["sources"]) <= 8


def test_audio_feedback_link_requires_same_song_lesson_class_and_recording():
    plan = SimpleNamespace(id=21, song_id=31, class_id=41)
    record = SimpleNamespace(id=51, class_id=41)
    analysis = SimpleNamespace(song_id=31, lesson_plan_id=None, classroom_record_id=None)
    recording = SimpleNamespace(song_id=31, classroom_record_id=None)
    assert not _audio_link_mismatch(analysis, plan, record, recording)
    _validate_audio_link(analysis, plan, record, recording)

    wrong_song = SimpleNamespace(song_id=32, lesson_plan_id=None, classroom_record_id=None)
    assert _audio_link_mismatch(wrong_song, plan, record, recording)
    try:
        _validate_audio_link(wrong_song, plan, record, recording)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("an analysis for another song must not be linked")

    wrong_class_recording = SimpleNamespace(song_id=31, classroom_record_id=99)
    assert _audio_link_mismatch(analysis, plan, record, wrong_class_recording)

    wrong_class = SimpleNamespace(id=52, class_id=42)
    assert _audio_link_mismatch(analysis, plan, wrong_class, recording)


def test_retrieval_returns_class_feedback_and_arrangement_for_the_owner_only():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        profile = ClassProfile(
            id=11, teacher_id=7, name="四年级1班", grade=4, student_count=30,
            province="广东", learning_level="中等", activity_level="积极",
            cooperation="愿意合作", pitch_level="音准稳定", rhythm_level="节奏容易加快",
            theory_level="基础", preferred_method="律动实践", common_problems="节奏容易加快",
            teacher_notes="",
        )
        song = Song(
            id=12, name="茉莉花", region="华南地区", province="广东", mood="舒展",
            mode="五声调式", grade="四年级", source="民歌", song_type="民歌",
            range_note="C4-C5", range_score=3, rhythm_score=3, dialect_score=2,
            difficulty="基础",
        )
        plan = LessonPlan(
            id=13, teacher_id=7, title="茉莉花节奏练习", class_id=11, song_id=12,
            duration_minutes=40, teacher_requirements="节奏接龙", content_json='{"summary":"练习节奏接龙"}',
        )
        record = ClassroomRecord(id=14, teacher_id=7, class_id=11, lesson_plan_id=13, status="feedback_completed")
        feedback = Feedback(
            id=15, teacher_id=7, classroom_record_id=14, overall_effect="一般",
            highlights="模唱完成", problems="节奏越唱越快", improvement="下次先练恒拍",
            audio_summary="", analysis_json="{}",
        )
        project = ArrangementProject(
            id=16, teacher_id=7, title="茉莉花古筝编曲", source_kind="manual", tempo=92,
            style="乡土抒情", melody_json="[]", arrangement_json='{"instruments":["古筝"]}',
        )
        db.add_all([profile, song, plan, record, feedback, project])
        db.commit()

        found = _retrieve(db, 7, "四年级1班茉莉花节奏反馈和古筝编曲", {"class_id": 11})
        kinds = {item["kind"] for item in found}
        assert "课堂反馈" in kinds
        assert "编曲工程" in kinds
        assert any("节奏越唱越快" in item["detail"] for item in found)
        try:
            _retrieve(db, 99, "四年级1班茉莉花", {"class_id": 11})
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("another teacher must not retrieve this class")
