from app.services.audio_service import _classroom_findings


def test_classroom_findings_cite_the_weakest_recorded_segment():
    sections = [
        {"time": "00:00—00:08", "voiced_ratio": .84, "pitch_stability": 88, "rhythm_score": 82, "evidence": "可用人声 84%"},
        {"time": "00:08—00:16", "voiced_ratio": .61, "pitch_stability": 43, "rhythm_score": 49, "evidence": "可用人声 61% · 音高离散 210 cents"},
    ]
    findings = _classroom_findings(sections, {"pitch_stability": 52, "rhythm_regularness": 55, "dynamics": 75})
    assert findings
    assert any(item["time"] == "00:08—00:16" for item in findings)
    assert any("43" in item["evidence"] or "49" in item["evidence"] for item in findings)
