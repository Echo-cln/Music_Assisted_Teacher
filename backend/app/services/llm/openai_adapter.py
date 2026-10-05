"""兼容智谱与火山方舟 Chat Completions 的严格正文读取器。

这里刻意不做“空返回自动降级”。模型没有实际正文就是一次失败；错误会带上
非敏感的响应结构，方便直接定位模型名、接口权限或字段格式问题。
"""
from __future__ import annotations

import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OpenAICompatibleAdapter:
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None, generation_strategy: str = "deep"):
        settings = get_settings()
        self.settings = settings
        fast = generation_strategy == "fast"
        self.model = model or (settings.ai_fast_model if fast else settings.ai_model)
        self.base_url = (base_url or (settings.ai_fast_base_url if fast and settings.ai_fast_base_url else settings.ai_base_url)).rstrip("/")
        self.api_key = api_key or (settings.ai_fast_api_key if fast and settings.ai_fast_api_key else settings.ai_api_key)

    @staticmethod
    def _to_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(str(part.get("text") or part.get("content") or "") for part in value if isinstance(part, dict))
        return ""

    @classmethod
    def _read_text(cls, choice: dict) -> str:
        """读取两家服务常见的流式/非流式正文位置，绝不把推理内容当作答案。"""
        for container in (choice.get("delta"), choice.get("message"), choice):
            if not isinstance(container, dict):
                continue
            for key in ("content", "text", "output_text"):
                text = cls._to_text(container.get(key))
                if text.strip():
                    return text
        return ""

    def stream(self, messages: list[dict], generation_strategy: str = "deep"):
        if not self.api_key:
            name = "AI_FAST_API_KEY / AI_API_KEY" if generation_strategy == "fast" else "AI_API_KEY"
            raise ValueError(f"未配置{name}，无法请求 model={self.model}")

        payload: dict = {
            "model": self.model, "messages": messages, "stream": True,
            "temperature": 0.35 if generation_strategy == "fast" else 0.45,
            "max_tokens": (
                getattr(self.settings, "ai_fast_max_tokens", 8192)
                if generation_strategy == "fast"
                else getattr(self.settings, "ai_max_tokens", 12288)
            ),
        }
        # GLM-5.3 的 thinking 不能关闭，且未指定 effort 时会默认 max。此前
        # 3200 个 token 会被 reasoning_content 耗尽，从而发生“有数千 SSE 事件、
        # 但 content 为空且 finish_reason=length”。这不是密钥问题。
        # 仅向 GLM-5.3 发送其专用参数，以免豆包等 OpenAI-compatible 服务拒绝它。
        if "glm-5.3" in self.model.lower():
            effort = (
                getattr(self.settings, "ai_fast_reasoning_effort", "low")
                if generation_strategy == "fast"
                else getattr(self.settings, "ai_reasoning_effort", "high")
            )
            payload["reasoning_effort"] = effort if effort in {"low", "high", "max"} else ("low" if generation_strategy == "fast" else "high")
            payload["thinking"] = {"type": "enabled", "clear_thinking": True}
        # 不传 response_format：GLM-5.3-Flash 的兼容接口会因该参数出现不一致行为。
        # JSON 约束由提示词和后端解析承担，避免把参数不兼容伪装为空内容。
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        event_count, text_count, text_chars, finish_reason, observed = 0, 0, 0, "", set()
        try:
            with httpx.Client(timeout=httpx.Timeout(180, connect=20)) as client:
                with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    logger.info("llm_response model=%s strategy=%s status=%s content_type=%s request_id=%s", self.model, generation_strategy, response.status_code, response.headers.get("content-type", ""), response.headers.get("x-request-id") or response.headers.get("request-id") or "-")
                    if response.status_code >= 400:
                        detail = response.read().decode("utf-8", "replace")[:1200].replace("\n", " ")
                        raise RuntimeError(f"模型 HTTP {response.status_code}（model={self.model}，base_url={self.base_url}）：{detail}")
                    content_type = response.headers.get("content-type", "")
                    # 有些兼容网关会忽略 stream=true，直接返回一个完整 JSON。它仍是
                    # 有效模型正文，必须解析而不是误报“空内容”。
                    if "text/event-stream" not in content_type.lower():
                        raw = response.read().decode("utf-8", "replace")
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError(
                                f"模型返回了非 SSE 且非 JSON 的内容（model={self.model}，content-type={content_type or '未提供'}）：{raw[:600]}"
                            ) from exc
                        choices = event.get("choices") if isinstance(event, dict) else None
                        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                        text = self._read_text(choice)
                        if text:
                            yield text
                            return
                        keys = ", ".join(sorted(event.keys())) if isinstance(event, dict) else type(event).__name__
                        raise RuntimeError(
                            f"模型返回 JSON 但没有正文（model={self.model}，base_url={self.base_url}，顶层字段={keys}，"
                            f"choice字段={', '.join(sorted(choice.keys())) or '无'}）。请检查模型名、权限和接口地址。"
                        )
                    for raw_line in response.iter_lines():
                        line = raw_line.lstrip("\ufeff \t")
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            observed.add("non_json_data")
                            continue
                        event_count += 1
                        choices = event.get("choices") if isinstance(event, dict) else None
                        if not isinstance(choices, list) or not choices:
                            observed.add("no_choices")
                            continue
                        choice = choices[0] if isinstance(choices[0], dict) else {}
                        finish_reason = choice.get("finish_reason") or finish_reason
                        for part_name in ("delta", "message"):
                            part = choice.get(part_name)
                            if isinstance(part, dict):
                                observed.update(f"{part_name}.{key}" for key in part.keys())
                        text = self._read_text(choice)
                        if text:
                            text_count += 1
                            text_chars += len(text)
                            yield text
        except httpx.HTTPError as exc:
            raise RuntimeError(f"模型连接失败（model={self.model}，base_url={self.base_url}）：{exc}") from exc

        if text_count == 0:
            fields = ", ".join(sorted(observed)) or "无 choices/delta/message 字段"
            raise RuntimeError(
                f"模型响应中没有正文（model={self.model}，base_url={self.base_url}，"
                f"SSE事件={event_count}，结束原因={finish_reason or '未提供'}，字段={fields}）。"
                "这不是已成功生成；请据此核对模型权限、模型名和接口供应商。"
            )
        if finish_reason == "length":
            raise RuntimeError(
                f"模型正文在完成前被长度限制截断（model={self.model}，正文分片={text_count}，正文字符={text_chars}）；本次结果未保存。"
            )
