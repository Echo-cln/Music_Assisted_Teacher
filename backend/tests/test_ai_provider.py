import json
from types import SimpleNamespace

import httpx
from app.services import ai_provider


def test_bigmodel_stream_sends_selected_model_and_yields_text(monkeypatch):
    settings = SimpleNamespace(
        ai_api_key="test-key",
        ai_base_url="https://open.bigmodel.cn/api/paas/v4",
        ai_model="glm-5.3-flash",
    )
    monkeypatch.setattr(ai_provider, "get_settings", lambda: settings)

    def handle(request):
        assert str(request.url) == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "glm-5.3-flash"
        assert payload["stream"] is True
        assert payload["temperature"] == 1
        assert "response_format" not in payload
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"content":"{\\"title\\":"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"\\"教案\\"}"}}]}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        ai_provider.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert "".join(ai_provider.stream_lesson_json({"title": "教案"})) == '{"title":"教案"}'
