import json
from types import SimpleNamespace

import httpx

from app.services.llm.openai_adapter import OpenAICompatibleAdapter


def test_glm_payload_uses_low_reasoning_and_large_output_budget(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="key", ai_base_url="https://example.test/v4", ai_model="glm-5.3-flash",
        ai_fast_api_key="", ai_fast_base_url="", ai_fast_model="fast",
        ai_max_tokens=32768, ai_fast_max_tokens=8192, ai_reasoning_effort="low", ai_fast_reasoning_effort="low",
    )
    monkeypatch.setattr("app.services.llm.openai_adapter.get_settings", lambda: settings)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 32768
        assert payload["reasoning_effort"] == "low"
        assert payload["thinking"]["type"] == "enabled"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text='data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')

    real = httpx.Client
    monkeypatch.setattr("app.services.llm.openai_adapter.httpx.Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    adapter = OpenAICompatibleAdapter(generation_strategy="deep")
    assert "".join(adapter.stream([{"role": "user", "content": "x"}])) == "{}"
