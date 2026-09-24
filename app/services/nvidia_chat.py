"""NVIDIA chat-completions tool planner; no provider text becomes an inventory fact."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import Settings
from app.services.embedding_service import EmbeddingService, SharedRateLimiter


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


class ChatModelError(RuntimeError):
    pass


class NvidiaChatClient:
    def __init__(self, settings: Settings, rate_path: Path | None = None):
        if not settings.nvidia_llm_key:
            raise ValueError("nvidia_LLM_model_key is required for chat")
        self.settings = settings
        self.limiter = SharedRateLimiter(
            rate_path
            or Path(__file__).resolve().parents[2] / "data" / ".nvidia_rate_limit.json",
            settings.nvidia_requests_per_minute,
        )
        self.client = httpx.Client(timeout=120)
        self.request_count = 0

    def close(self) -> None:
        self.client.close()

    def plan(self, messages: list[dict], tools: list[dict]) -> list[ToolCall]:
        body = {
            "model": self.settings.nvidia_llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": 1024,
            "stream": False,
        }
        for attempt in range(4):
            self.limiter.acquire()
            self.request_count += 1
            try:
                response = self.client.post(
                    self.settings.nvidia_llm_url,
                    headers={"Authorization": f"Bearer {self.settings.nvidia_llm_key}"},
                    json=body,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 3:
                    raise ChatModelError(
                        "NVIDIA chat transport failed after retries"
                    ) from exc
                time.sleep(EmbeddingService._retry_delay(None, attempt))
                continue
            if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                if attempt == 3:
                    raise ChatModelError(
                        f"NVIDIA chat returned HTTP {response.status_code} "
                        "after retries"
                    )
                time.sleep(EmbeddingService._retry_delay(response, attempt))
                continue
            if response.status_code >= 400:
                raise ChatModelError(
                    f"NVIDIA chat returned HTTP {response.status_code}"
                )
            try:
                calls = response.json()["choices"][0]["message"].get("tool_calls") or []
                result = []
                for call in calls[:5]:
                    function = call["function"]
                    arguments = function.get("arguments") or "{}"
                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)
                    if not isinstance(arguments, dict):
                        raise TypeError("Tool arguments must be an object")
                    result.append(ToolCall(name=function["name"], arguments=arguments))
                return result
            except (
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise ChatModelError("Unexpected NVIDIA tool-call response") from exc
        raise AssertionError("Unreachable retry state")
