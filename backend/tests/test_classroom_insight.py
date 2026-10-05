from app.services.classroom_insight_service import _valid_insights


def test_model_insight_only_accepts_existing_audio_time_ranges():
    result = _valid_insights(
        {
            "summary": "前半段先处理起音，再保留后半段的稳定进入方式。",
            "priorities": [
                {"time": "00:00—00:06", "headline": "先统一起拍", "interpretation": "起音证据较弱。", "action": "先拍两拍恒拍再唱。"},
                {"time": "00:30—00:40", "headline": "虚构时段", "interpretation": "不应通过。", "action": "不应通过。"},
            ],
        },
        {"00:00—00:06", "00:06—00:12"},
    )
    assert result is not None
    assert len(result["priorities"]) == 1
    assert result["priorities"][0]["time"] == "00:00—00:06"


def test_model_insight_rejects_results_without_a_verifiable_priority():
    assert _valid_insights(
        {"summary": "泛泛的总结", "priorities": [{"time": "不存在", "headline": "x", "interpretation": "x", "action": "x"}]},
        {"00:00—00:06"},
    ) is None
