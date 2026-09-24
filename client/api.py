"""FastAPI transport for the Streamlit UI. No car or booking rules live here."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


class ApiError(RuntimeError):
    """A message safe to show in the UI."""


def backend_url() -> str:
    load_dotenv(override=False)
    return os.getenv("FASTAPI_URL", "http://127.0.0.1:8000").strip().rstrip("/")


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        configured = (
            (base_url if base_url is not None else backend_url()).strip().rstrip("/")
        )
        parsed = urlparse(configured)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError("FASTAPI_URL must be a valid http or https address.")
        self.base_url = configured + "/"
        self.transport = transport

    def _post(self, path: str, payload: dict, *, timeout: float) -> dict:
        try:
            with httpx.Client(
                base_url=self.base_url,
                transport=self.transport,
                timeout=httpx.Timeout(timeout, connect=5.0),
            ) as client:
                response = client.post(path.lstrip("/"), json=payload)
        except httpx.TimeoutException as exc:
            raise ApiError(
                "The car assistant took too long to respond. Please try again."
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(
                "The car service is unavailable. Check that FastAPI is running "
                "and try again."
            ) from exc

        if response.status_code >= 400:
            if response.status_code == 403:
                raise ApiError(
                    "This conversation belongs to another user. Start a new session."
                )
            if response.status_code == 404:
                raise ApiError("This conversation was not found. Start a new session.")
            if response.status_code >= 500:
                raise ApiError(
                    "The car service is temporarily unavailable. Please try again."
                )
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise ApiError(
                str(detail)
                if isinstance(detail, str) and detail
                else "The request could not be completed. Please check your input."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError(
                "The car service returned an unreadable response. Please try again."
            ) from exc
        if not isinstance(data, dict):
            raise ApiError(
                "The car service returned an empty response. Please try again."
            )
        return data

    def create_session(self, user_id: str, display_name: str) -> str:
        data = self._post(
            "sessions", {"user_id": user_id, "display_name": display_name}, timeout=15.0
        )
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ApiError(
                "The car service could not start a conversation. Please try again."
            )
        return session_id

    def start_user(self, display_name: str) -> tuple[str, str]:
        """Resolve a stable backend user, then start a fresh conversation."""
        data = self._post("users", {"display_name": display_name}, timeout=15.0)
        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise ApiError(
                "The car service could not start a profile. Please try again."
            )
        session_id = self.create_session(
            user_id, data.get("display_name") or display_name
        )
        return user_id, session_id

    def chat(self, user_id: str, session_id: str, message: str) -> dict:
        data = self._post(
            "chat",
            {"user_id": user_id, "session_id": session_id, "message": message},
            timeout=180.0,
        )
        if data.get("session_id") != session_id:
            raise ApiError(
                "The car service returned a different conversation. Please "
                "start a new session."
            )
        if not isinstance(data.get("message"), str) or not data["message"].strip():
            raise ApiError(
                "The assistant returned an empty response. Please try again."
            )
        cars = data.get("cars", [])
        if not isinstance(cars, list) or any(not isinstance(car, dict) for car in cars):
            raise ApiError(
                "The car service returned invalid vehicle results. Please try again."
            )
        data["cars"] = cars
        return data
