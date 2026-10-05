from app.services import ai_provider


def test_stream_lesson_json_selects_fast_model_and_forwards_strategy(monkeypatch):
    calls = []

    class Adapter:
        def stream(self, messages, generation_strategy):
            calls.append((messages, generation_strategy))
            yield '{"title":"教案"}'

    monkeypatch.setattr(ai_provider, "get_settings", lambda: type("Settings", (), {"ai_model": "deep", "ai_fast_model": "fast"})())
    monkeypatch.setattr(ai_provider, "get_adapter", lambda model, generation_strategy: Adapter())

    assert "".join(ai_provider.stream_lesson_json({"title": "教案"}, generation_strategy="fast")) == '{"title":"教案"}'
    assert calls[0][1] == "fast"
    assert calls[0][0][0]["role"] == "system"
