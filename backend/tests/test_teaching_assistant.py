import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.db.session import Base
from app.models.entities import ArrangementProject, AssistantConversation, ClassProfile, ClassroomRecord, Feedback, LessonPlan, Song
from fastapi import HTTPException

from app.api.routes.feedback import _audio_link_mismatch, _validate_audio_link
from app.api.routes.teaching_assistant import (
    _analysis_detail, _class_scope_suggestions, _is_blank_feedback_form_request,
    _is_feedback_creation_request, _is_observation_offer, _is_lesson_action, _is_lookup,
    _is_all_class_request, _is_contextual_short_reply, _is_refine_search_request,
    _plain, _present, _requires_class_scope, _retrieve, _terms, _requested_class_change,
    _today_question_reply, _is_weather_question, _weather_location, _weather_followup_location,
    _class_scope_conflicts, _lookup_reply, _feedback_detail, _is_conversation_delete_request,
)
from app.services.ai_provider import _naturalize_dialogue_answer


def test_intent_guards_keep_lookup_separate_from_lesson_actions():
    assert _is_lookup("帮我找一下四年级1班之前的教案")
    assert not _is_lookup("我找不到合适的答案，你能解释一下吗")
    assert _is_lookup("结合刚才找到的课堂反馈，和我一起准备一份教案")
    assert _is_lesson_action("结合刚才找到的课堂反馈，和我一起准备一份教案")
    assert not _is_lesson_action("先解释为什么安排节奏接龙，不要改教案")
    assert not _is_lesson_action("先分析这份教案有什么问题，暂时不要修改")
    assert _is_lesson_action("根据这条课堂反馈调整教案", {"type": "feedback"})
    assert "茉莉花" in _terms("请找《茉莉花》节奏练习的历史教案")
    assert "古筝" in _terms("四年级1班想找古筝编曲")
    assert "class_name" not in _plain("{'class_name': '三年级1班', 'duration': 40}")


def test_refinement_asks_for_criteria_and_short_answers_use_recent_question():
    assert _is_refine_search_request("换一个年级或课堂目标再帮我找找")
    assert _is_contextual_short_reply("11", [{"role": "assistant", "content": "你想要哪一种？可以选 1 或 2。"}])
    assert not _is_contextual_short_reply("11", [{"role": "assistant", "content": "我找到了几条资源。"}])


def test_assistant_asks_for_class_instead_of_guessing_feedback_scope():
    profiles = [SimpleNamespace(id=11, name="三年级1班"), SimpleNamespace(id=12, name="四年级1班")]
    query = "看看这个班最近的课堂反馈里，节奏方面反复出现什么情况"
    assert _requires_class_scope(query, {}, profiles)
    assert not _requires_class_scope("看看四年级1班最近的课堂反馈", {}, profiles)
    assert not _requires_class_scope("查看所有班级的课堂反馈", {}, profiles)
    assert _is_all_class_request("查看所有班级的课堂反馈")
    assert not _requires_class_scope(query, {"class_id": 11}, profiles)
    options = _class_scope_suggestions(profiles, query)
    assert options[0]["class_id"] == 11
    assert "三年级1班" in options[0]["message"]
    assert options[-1]["label"] == "查看全部班级"


def test_feedback_generation_clarifies_intent_and_blank_form_is_explicit():
    assert _is_feedback_creation_request("为我生成课堂反馈")
    assert _is_feedback_creation_request("帮我整理成课后反馈")
    assert not _is_feedback_creation_request("看看最近的课堂反馈")
    assert _is_observation_offer("我会提供本节课实际观察")
    assert _is_blank_feedback_form_request("打开空白课堂反馈表")
    assert not _is_blank_feedback_form_request("为我生成课堂反馈")


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
        old_conversation = AssistantConversation(
            id=30, teacher_id=7, title="节奏接龙课堂复盘", context_json="{}",
            messages_json=json.dumps([
                {"role": "user", "content": "之前试过节奏接龙，学生后半段会加快。"},
                {"role": "assistant", "content": "可以先用固定拍手脉冲，再逐步加入歌词。"},
            ], ensure_ascii=False),
        )
        private_conversation = AssistantConversation(
            id=31, teacher_id=99, title="节奏接龙私人对话", context_json="{}",
            messages_json='[{"role":"user","content":"节奏接龙"}]',
        )
        db.add_all([profile, song, plan, record, feedback, project, old_conversation, private_conversation])
        db.commit()

        found = _retrieve(db, 7, "四年级1班茉莉花节奏反馈和古筝编曲", {"class_id": 11})
        kinds = {item["kind"] for item in found}
        assert "课堂反馈" in kinds
        assert "编曲工程" in kinds
        assert any("节奏越唱越快" in item["detail"] for item in found)

        past = _retrieve(db, 7, "帮我找之前的对话：节奏接龙", {"class_id": 11}, conversation_id=50)
        historical = [item for item in past if item["kind"] == "历史对话"]
        assert len(historical) == 1
        assert historical[0]["id"] == 30
        assert "固定拍手脉冲" in historical[0]["detail"]
        missing_song = _retrieve(db, 7, "帮我找《不存在的歌曲》的历史教案", {"class_id": 11})
        assert not any(item.get("kind") == "历史教案" for item in missing_song)

        quoted = _retrieve(db, 7, "继续聊这个活动", {
            "referenced_conversation_id": 30,
            "referenced_conversation_title": "节奏接龙课堂复盘",
            "referenced_conversation_excerpt": "教师：之前试过节奏接龙。",
        }, conversation_id=51)
        assert any(item["kind"] == "已引用的历史对话" and item["id"] == 30 for item in quoted)
        try:
            _retrieve(db, 99, "四年级1班茉莉花", {"class_id": 11})
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("another teacher must not retrieve this class")


def test_class_scope_change_requires_confirmation_intent_and_today_question_is_answered_locally():
    profiles = [SimpleNamespace(id=11, name="三年级1班"), SimpleNamespace(id=12, name="四年级1班")]
    assert _requested_class_change("把班级切换到四年级1班", profiles).id == 12
    assert _requested_class_change("我想给四年级1班找一首歌", profiles) is None
    answer = _today_question_reply("今天周几了？")
    assert answer and "星期" in answer and "今天是" in answer
    assert _today_question_reply("这周几节音乐课") is None
    assert _today_question_reply("现在几点了") and "北京时间" in _today_question_reply("现在几点了")
    assert _is_weather_question("天气如何")
    assert _weather_location("帮我查一下广州今天的天气") == "广州"
    assert _weather_location("天气如何") is None


def test_weather_city_followup_uses_previous_question_and_does_not_capture_unrelated_short_replies():
    history = [{"role": "assistant", "content": "你想查哪个城市？告诉我地名，我帮你看当前天气和今天的预报。"}]
    assert _weather_followup_location("广州", history) == "广州"
    assert _weather_followup_location("我在厦门", history) == "厦门"
    assert _weather_followup_location("深圳市的天气", history) == "深圳"
    assert _weather_followup_location("不知道", history) is None
    assert _weather_followup_location("广州", [{"role": "assistant", "content": "你想找哪一首歌？"}]) is None


def test_weather_api_failure_is_plain_and_does_not_mention_model_internals(monkeypatch):
    from app.api.routes import teaching_assistant

    def fail_request(*args, **kwargs):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(teaching_assistant, "urlopen", fail_request)
    reply, sources = teaching_assistant._live_weather_reply("查广州天气")
    assert "广州" in reply and "天气数据" in reply
    assert "模型" not in reply and "猜" not in reply
    assert not sources



def test_agent_confirms_class_conflict_before_searching_and_offers_both_scopes():
    profiles = [
        SimpleNamespace(id=11, name="三年级 1 班"),
        SimpleNamespace(id=12, name="五年级 1 班"),
    ]
    conflicts = _class_scope_conflicts(
        "帮我找五年级1班之前的教案",
        {"class_id": 11},
        profiles,
    )
    assert [item.id for item in conflicts] == [12]
    assert not _class_scope_conflicts(
        "给我讲个冷笑话",
        {"class_id": 11},
        profiles,
    )
    assert not _class_scope_conflicts(
        "帮我找五年级1班之前的教案",
        {"class_id": 12},
        profiles,
    )
    assert not _requires_class_scope(
        "看看五年级1班最近的课堂反馈",
        {},
        profiles,
    )


def test_ambiguous_previous_lesson_lookup_asks_instead_of_picking_one():
    records = [
        {"kind": "历史教案", "label": "茉莉花节奏练习", "id": 1, "detail": "班级：三年级1班"},
        {"kind": "历史教案", "label": "茉莉花歌唱活动", "id": 2, "detail": "班级：五年级1班"},
    ]
    reply = _lookup_reply(records, "帮我找上次那份教案")
    assert "暂时不能确定" in reply
    assert "歌曲名、班级或大概时间" in reply


def test_feedback_retrieval_marks_demo_observations_as_demo_data():
    feedback = SimpleNamespace(
        analysis_json=json.dumps({"demo_trend_sample": True, "goal_observations": ["保持恒拍"]}, ensure_ascii=False),
        highlights="能完成节奏模仿",
        problems="弱起容易抢拍",
        improvement="先慢速口读",
        audio_summary="",
        audio_analysis_id=None,
        created_at=None,
    )
    record = SimpleNamespace(taught_at=None)
    detail = _feedback_detail(feedback, record)
    assert "演示样例" in detail
    assert "真实课堂测量" in detail
    assert "保持恒拍" in detail


def test_unreferenced_new_thread_does_not_reuse_prior_thread_context():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        old = AssistantConversation(
            id=201, teacher_id=7, title="旧对话",
            context_json=json.dumps({"class_id": 11, "song_name": "茉莉花"}, ensure_ascii=False),
            messages_json=json.dumps([{"role": "user", "content": "五年级1班茉莉花课堂反馈"}], ensure_ascii=False),
        )
        db.add(old)
        db.commit()
        # Retrieval is only given the current thread's context and does not load another
        # conversation unless the user explicitly asks to search/refer to conversation history.
        found = _retrieve(db, 7, "现在想聊节奏练习", {}, conversation_id=202)
        assert not any(item.get("id") == old.id and item.get("kind") == "已引用的历史对话" for item in found)



def test_delete_conversation_intent_never_matches_lesson_or_feedback_deletion():
    assert _is_conversation_delete_request("删除这段对话")
    assert _is_conversation_delete_request("清除聊天记录")
    assert not _is_conversation_delete_request("删除这份教案")
    assert not _is_conversation_delete_request("删除课堂反馈")
