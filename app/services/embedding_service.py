"""NVIDIA passage/query embeddings with shared rate limiting and bounded retries."""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from filelock import FileLock

from app.core.config import Settings


def normalized_text(text: str) -> str:
    # Whitespace normalization keeps Arabic and other Unicode characters intact.
    return " ".join(text.split())


def text_hash(text: str) -> str:
    return hashlib.sha256(normalized_text(text).encode("utf-8")).hexdigest()


class SharedRateLimiter:
    """Rolling 60-second request cap shared by local ingestion/search processes."""

    def __init__(self, path: Path, limit: int):
        if limit < 1 or limit > 40:
            raise ValueError("NVIDIA request limit must be between 1 and 40/minute")
        self.path = path
        self.lock = FileLock(str(path) + ".lock")
        self.limit = limit
        path.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.time()
                try:
                    timestamps = json.loads(self.path.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    timestamps = []
                timestamps = [t for t in timestamps if 0 <= now - t < 60]
                if len(timestamps) < self.limit:
                    timestamps.append(now)
                    temp = self.path.with_suffix(".tmp")
                    temp.write_text(json.dumps(timestamps), encoding="utf-8")
                    os.replace(temp, self.path)
                    return
                delay = max(0.1, 60 - (now - timestamps[0]))
            time.sleep(delay)


class EmbeddingError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class EmbeddingService:
    def __init__(self, settings: Settings, rate_path: Path | None = None):
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

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            value = response.headers.get("Retry-After")
            if value:
                try:
                    return min(120.0, max(0.0, float(value)))
                except ValueError:
                    try:
                        dt = parsedate_to_datetime(value)
                        return min(
                            120.0, max(0.0, (dt - datetime.now(UTC)).total_seconds())
                        )
                    except (TypeError, ValueError):
                        pass
        return min(60.0, 2**attempt + random.uniform(0, 1))

    def _request(self, texts: list[str], input_type: str) -> list[list[float]]:
        if input_type not in ("passage", "query"):
            raise ValueError("input_type must be passage or query")
        if not texts or any(not normalized_text(t) for t in texts):
            raise ValueError("Embedding inputs must be non-empty")
        body = {
            "model": self.settings.nvidia_model,
            "input": [normalized_text(t) for t in texts],
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "NONE",
        }
        for attempt in range(5):
            self.limiter.acquire()
            self.request_count += 1
            try:
                response = self.client.post(
                    self.settings.nvidia_url,
                    headers={"Authorization": f"Bearer {self.settings.nvidia_key}"},
                    json=body,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 4:
                    raise EmbeddingError(
                        "NVIDIA embedding transport failed after retries"
                    ) from exc
                time.sleep(self._retry_delay(None, attempt))
                continue
            if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                if attempt == 4:
                    raise EmbeddingError(
                        "NVIDIA embedding endpoint returned HTTP "
                        f"{response.status_code} after retries"
                    )
                time.sleep(self._retry_delay(response, attempt))
                continue
            if response.status_code >= 400:
                # Never include the provider response body; it may contain request text.
                raise EmbeddingError(
                    f"NVIDIA embedding endpoint returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            try:
                items = response.json()["data"]
                vectors = [
                    item["embedding"]
                    for item in sorted(items, key=lambda x: x["index"])
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise EmbeddingError(
                    "Unexpected NVIDIA embedding response shape"
                ) from exc
            if (
                len(vectors) != len(texts)
                or not vectors
                or any(
                    not isinstance(v, list) or not v or len(v) != len(vectors[0])
                    for v in vectors
                )
            ):
                raise EmbeddingError(
                    "NVIDIA returned missing or inconsistent embeddings"
                )
            return vectors
        raise AssertionError("Unreachable retry state")

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._request(texts, "passage")
        except EmbeddingError as exc:
            # The hosted endpoint does not publish a stable item/payload ceiling.
            # A smaller batch may succeed if the provider rejects a large payload.
            if exc.status_code not in (413, 422) or len(texts) == 1:
                raise
            middle = len(texts) // 2
            return self.embed_passages(texts[:middle]) + self.embed_passages(
                texts[middle:]
            )

    def embed_query(self, query: str) -> list[float]:
        return self._request([query], "query")[0]
