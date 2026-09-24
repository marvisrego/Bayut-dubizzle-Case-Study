"""HTTP contract and session behavior of the thin Streamlit client."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from streamlit.testing.v1 import AppTest

from client.api import ApiClient, ApiError


class ApiClientTests(unittest.TestCase):
    def test_name_only_start_resolves_backend_user_then_creates_session(self) -> None:
        sent = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append((request.url.path, json.loads(request.content)))
            if request.url.path == "/users":
                return httpx.Response(
                    200, json={"user_id": "generated-user", "display_name": "Amina"}
                )
            return httpx.Response(
                201, json={"user_id": "generated-user", "session_id": "session-1"}
            )

        api = ApiClient("http://localhost:8000", transport=httpx.MockTransport(respond))
        self.assertEqual(api.start_user("Amina"), ("generated-user", "session-1"))
        self.assertEqual(
            sent,
            [
                ("/users", {"display_name": "Amina"}),
                ("/sessions", {"user_id": "generated-user", "display_name": "Amina"}),
            ],
        )

    def test_invalid_backend_url_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ApiError, "FASTAPI_URL"):
            ApiClient("not-a-url")

    def test_session_and_chat_use_only_fastapi(self) -> None:
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append((request.url.path, request.content))
            if request.url.path == "/sessions":
                return httpx.Response(201, json={"session_id": "session-1"})
            return httpx.Response(
                200,
                json={"session_id": "session-1", "message": "No matches", "cars": []},
            )

        api = ApiClient("http://localhost:8000", transport=httpx.MockTransport(respond))
        self.assertEqual(api.create_session("demo", "Amina"), "session-1")
        self.assertEqual(
            api.chat("demo", "session-1", "Show me SUVs")["message"], "No matches"
        )
        self.assertEqual([path for path, _ in calls], ["/sessions", "/chat"])
        self.assertIn(b'"user_id":"demo"', calls[1][1])
        self.assertIn(b'"session_id":"session-1"', calls[1][1])

    def test_unavailable_timeout_and_empty_reply_are_friendly(self) -> None:
        def unavailable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private connection detail", request=request)

        def timed_out(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("private timeout detail", request=request)

        for handler, expected in (
            (unavailable, "unavailable"),
            (timed_out, "too long"),
        ):
            with self.subTest(expected=expected):
                api = ApiClient(transport=httpx.MockTransport(handler))
                with self.assertRaises(ApiError) as raised:
                    api.create_session("demo", "Amina")
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("private", str(raised.exception))

        api = ApiClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"session_id": "session-1", "message": "", "cars": []}
                )
            )
        )
        with self.assertRaisesRegex(ApiError, "empty response"):
            api.chat("demo", "session-1", "Hello")


class StreamlitFlowTests(unittest.TestCase):
    def test_welcome_prompt_sends_chat_through_fastapi(self) -> None:
        api = Mock()
        api.start_user.return_value = ("demo-user", "session-1")
        api.chat.return_value = {
            "session_id": "session-1",
            "message": "I found cars.",
            "cars": [],
        }
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        with patch("client.api.ApiClient", return_value=api):
            at = AppTest.from_file(str(app_path)).run()
            at.text_input(key="identity_name").set_value("Amina")
            next(
                button for button in at.button if button.label == "Start / switch user"
            ).click().run()
            next(
                button for button in at.button if button.label == "Family SUVs"
            ).click().run()
            api.chat.assert_called_once_with(
                "demo-user", "session-1", "Show me comfortable family SUVs"
            )
            self.assertEqual(
                at.session_state["messages"][-1]["content"], "I found cars."
            )

    def test_new_session_keeps_identity_and_clears_only_ui_history(self) -> None:
        api = Mock()
        api.start_user.return_value = ("demo-user", "session-1")
        api.create_session.return_value = "session-2"
        api.chat.return_value = {
            "session_id": "session-1",
            "message": "No matching cars.",
            "cars": [],
        }
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        with patch("client.api.ApiClient", return_value=api):
            at = AppTest.from_file(str(app_path)).run()
            at.text_input(key="identity_name").set_value("Amina")
            next(
                button for button in at.button if button.label == "Start / switch user"
            ).click().run()
            self.assertEqual(at.session_state["session_id"], "session-1")
            at.chat_input[0].set_value("Show me SUVs").run()
            api.chat.assert_called_once_with("demo-user", "session-1", "Show me SUVs")
            self.assertEqual(len(at.session_state["messages"]), 2)
            next(
                button for button in at.button if button.label == "New Session"
            ).click().run()
            self.assertEqual(at.session_state["session_id"], "session-2")
            self.assertEqual(at.session_state["active_user_id"], "demo-user")
            self.assertEqual(at.session_state["messages"], [])
            api.start_user.assert_called_once_with("Amina")
            api.create_session.assert_called_once_with("demo-user", "Amina")

    def test_missing_vehicle_fields_and_chat_failure_render_safely(self) -> None:
        api = Mock()
        api.start_user.return_value = ("demo-user", "session-1")
        api.chat.side_effect = [
            {
                "session_id": "session-1",
                "message": "I found a car.",
                "cars": [
                    {
                        "listing_id": "CAR_0001",
                        "year": 2022,
                        "make": "Honda",
                        "model": "Civic",
                        "trim": "Base",
                        "photo_url": None,
                        "price_aed": None,
                        "mileage_km": None,
                    }
                ],
            },
            ApiError(
                "The car service is unavailable. Check that FastAPI is running "
                "and try again."
            ),
        ]
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        with patch("client.api.ApiClient", return_value=api):
            at = AppTest.from_file(str(app_path)).run()
            at.text_input(key="identity_name").set_value("Amina")
            next(
                button for button in at.button if button.label == "Start / switch user"
            ).click().run()
            at.chat_input[0].set_value("Show me a Honda").run()
            self.assertFalse(at.exception)
            self.assertIn(
                "Image not available", [caption.value for caption in at.caption]
            )
            self.assertGreaterEqual(
                [item.value for item in at.markdown].count("Not specified"), 2
            )
            at.chat_input[0].set_value("Tell me more").run()
            self.assertFalse(at.exception)
            self.assertTrue(at.session_state["messages"][-1]["error"])
            self.assertIn("unavailable", at.session_state["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
