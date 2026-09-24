"""Conversation state, tool grounding, bookings, leads, and scope tests."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.main import app
from app.models import state as _state  # noqa: F401
from app.models.car import Base
from app.models.state import BookingRecord
from app.schemas.cars import SearchFilters
from app.services.agent import ChatAgent
from app.services.agent_tools import AgentTools
from app.services.booking import DUBAI, BookingService
from app.services.car_repository import CarRepository
from app.services.leads import LeadService
from app.services.memory import MemoryService
from app.services.nvidia_chat import ToolCall
from tests.test_retrieval_api import make_car


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db, db.begin():
            db.add_all(
                [
                    make_car("CAR_0001", 2023, "Honda", "Civic", 85000, 24000),
                    make_car("CAR_0002", 2022, "Honda", "Accord", None, None),
                    make_car("CAR_0003", 2021, "Honda", "CR-V", 95000, 41000),
                    make_car("CAR_0004", 2022, "Mercedes", "C200", 99000, 33000),
                    make_car("CAR_0005", 2020, "BMW", "X5", 120000, 50000),
                    make_car("CAR_0006", 2022, "Nissan", "Patrol", 145000, 32000),
                    make_car("CAR_0007", 2021, "Nissan", "X-Trail", 88000, 45000),
                ]
            )
        self.memory = MemoryService(self.engine)
        self.booking = BookingService(self.engine)
        self.leads = LeadService(self.engine, Path(self.temp.name) / "leads.csv")
        self.retrieval = Mock()
        repository = CarRepository(self.engine)
        self.retrieval.structured_search.side_effect = repository.structured_search
        self.retrieval.get_car.side_effect = repository.get
        self.retrieval.catalog.side_effect = repository.catalog
        self.retrieval.semantic_search.return_value = [repository.get("CAR_0005")]
        self.retrieval.hybrid_search.side_effect = lambda filters, query, top_k: (
            repository.structured_search(filters, limit=top_k)
        )
        self.model = Mock()
        self.model.plan.return_value = []
        self.agent = ChatAgent(
            AgentTools(self.retrieval, self.memory, self.booking, self.leads),
            self.model,
        )
        app.dependency_overrides[dependencies.get_agent_service] = lambda: self.agent
        app.dependency_overrides[dependencies.get_memory_service] = lambda: self.memory
        self.api = TestClient(app)
        self.session = self.memory.create_session("user-a", "Amina").session_id

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.api.close()
        self.engine.dispose()
        self.temp.cleanup()

    def ask(
        self,
        message: str,
        calls: list[ToolCall],
        session: str | None = None,
        user: str = "user-a",
    ) -> dict:
        self.model.plan.return_value = calls
        response = self.api.post(
            "/chat",
            json={
                "user_id": user,
                "session_id": session or self.session,
                "message": message,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def search_hondas(self) -> None:
        answer = self.ask(
            "Show me Hondas",
            [ToolCall("search_inventory", {"filters": {"make": "Honda"}, "top_k": 3})],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0001", "CAR_0002", "CAR_0003"])

    def test_multi_turn_ordinals_pronoun_and_structured_state(self) -> None:
        self.search_hondas()
        for word, car_id in (
            ("first", "CAR_0001"),
            ("second", "CAR_0002"),
            ("third", "CAR_0003"),
        ):
            answer = self.ask(
                f"What's the mileage on the {word} one?",
                [
                    ToolCall(
                        "get_car_details",
                        {"listing_id": "CAR_0005", "attribute": "mileage"},
                    )
                ],
            )
            self.assertEqual(answer["listing_ids"], [car_id])
        answer = self.ask(
            "Does it have warranty?",
            [
                ToolCall(
                    "get_car_details",
                    {"listing_id": "CAR_0005", "attribute": "warranty"},
                )
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0003"])
        self.assertIn("not listed", answer["message"])
        context = self.memory.get_session_context(self.session)
        self.assertEqual(
            context.last_search_results, ["CAR_0001", "CAR_0002", "CAR_0003"]
        )
        self.assertEqual(context.selected_car_id, "CAR_0003")
        self.assertEqual(context.active_filters, {"make": "Honda"})
        self.assertLessEqual(len(context.recent_messages), 8)

    def test_persistent_preference_and_liked_car_across_new_session(self) -> None:
        self.search_hondas()
        self.ask(
            "I generally prefer BMW",
            [
                ToolCall(
                    "update_user_preferences", {"updates": {"preferred_makes": ["BMW"]}}
                )
            ],
        )
        self.ask(
            "I like the second car",
            [ToolCall("remember_liked_car", {"listing_id": "CAR_0005"})],
        )
        other = self.memory.create_session("user-a", "Amina").session_id
        answer = self.ask(
            "What do you remember about my cars?",
            [ToolCall("get_user_memory", {})],
            other,
        )
        self.assertIn("Amina", answer["message"])
        self.assertIn("BMW", answer["message"])
        self.assertIn("CAR_0002", answer["message"])
        self.assertEqual(
            self.memory.get_user_memory("user-a").liked_car_ids, ["CAR_0002"]
        )
        another_user = self.memory.create_session("user-b", "Bilal").session_id
        isolated = self.ask(
            "What do you remember about me?",
            [ToolCall("get_user_memory", {})],
            another_user,
            "user-b",
        )
        self.assertIn("Bilal", isolated["message"])
        self.assertNotIn("BMW", isolated["message"])
        self.assertNotIn("CAR_0002", isolated["message"])

    def test_named_user_nissan_preference_and_second_car_across_sessions(self) -> None:
        identity = self.api.post("/users", json={"display_name": "Test User"})
        self.assertEqual(identity.status_code, 200, identity.text)
        user_id = identity.json()["user_id"]
        session_one = self.api.post(
            "/sessions",
            json={
                "user_id": user_id,
                "display_name": "Test User",
            },
        ).json()["session_id"]

        saved = self.ask(
            "I prefer Nissan SUVs",
            [
                ToolCall(
                    "update_user_preferences",
                    {
                        "updates": {
                            "preferred_makes": ["Nissan"],
                            "preferred_body_type": "SUV",
                        },
                    },
                )
            ],
            session_one,
            user_id,
        )
        self.assertIn("saved", saved["message"])
        self.assertEqual(
            self.memory.get_user_memory(user_id).preferred_makes, ["Nissan"]
        )
        self.assertEqual(
            self.memory.get_user_memory(user_id).preferred_body_type, "SUV"
        )
        found = self.ask(
            "Show me Nissan SUVs",
            [
                ToolCall(
                    "search_inventory",
                    {
                        "filters": {"make": "Nissan"},
                        "top_k": 3,
                    },
                )
            ],
            session_one,
            user_id,
        )
        self.assertEqual(found["listing_ids"], ["CAR_0006", "CAR_0007"])
        liked = self.ask(
            "I like the second one",
            [
                ToolCall(
                    "remember_liked_car",
                    {
                        "listing_id": "CAR_0006",
                    },
                )
            ],
            session_one,
            user_id,
        )
        self.assertIn("CAR_0007", liked["message"])

        session_two = self.api.post(
            "/sessions",
            json={
                "user_id": user_id,
                "display_name": "Test User",
            },
        ).json()["session_id"]
        self.assertNotEqual(session_one, session_two)
        self.assertEqual(
            self.api.post("/users", json={"display_name": "test user"}).json()[
                "user_id"
            ],
            user_id,
        )
        preference = self.ask(
            "What kind of cars do I prefer?", [], session_two, user_id
        )
        self.assertIn("Nissan", preference["message"])
        self.assertIn("SUV", preference["message"])
        recalled = self.ask("Which car did I like?", [], session_two, user_id)
        self.assertIn("CAR_0007", recalled["message"])
        self.assertEqual(
            self.memory.get_session_context(session_two).last_search_results, []
        )

    def test_explicit_like_pronoun_uses_selected_car(self) -> None:
        self.search_hondas()
        self.ask(
            "Tell me about the third car",
            [ToolCall("get_car_details", {"listing_id": "CAR_0005"})],
        )
        answer = self.ask(
            "I like it", [ToolCall("remember_liked_car", {"listing_id": "CAR_0005"})]
        )
        self.assertIn("CAR_0003", answer["message"])
        self.assertEqual(
            self.memory.get_user_memory("user-a").liked_car_ids, ["CAR_0003"]
        )

    def test_temporary_search_vs_persistent_preference_and_lead_csv(self) -> None:
        answer = self.ask(
            "Show me Mercedes under 100k, but I generally prefer BMW",
            [
                ToolCall(
                    "search_inventory",
                    {"filters": {"make": "Mercedes", "max_price_aed": 100000}},
                ),
                ToolCall(
                    "update_user_preferences",
                    {"updates": {"preferred_makes": ["Mercedes", "BMW"]}},
                ),
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0004"])
        self.assertEqual(self.memory.get_user_memory("user-a").preferred_makes, ["BMW"])
        self.assertEqual(
            self.memory.get_session_context(self.session).active_filters,
            {"make": "Mercedes", "max_price_aed": 100000},
        )
        lead = self.leads.get_lead("user-a")
        self.assertEqual(lead["desired_make"], "Mercedes")
        self.assertEqual(lead["budget_max_aed"], 100000)
        with self.leads.csv_path.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["desired_make"], "Mercedes")
        self.assertEqual(row["budget_max_aed"], "100000")

    def test_explicit_hard_filter_overrides_wrong_model_tool_arguments(self) -> None:
        answer = self.ask(
            "Show me Mercedes under 100k, but I generally prefer BMW",
            [
                ToolCall(
                    "search_inventory",
                    {"filters": {"make": "BMW", "max_price_aed": 200000}},
                ),
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0004"])
        self.assertEqual(
            self.memory.get_session_context(self.session).active_filters,
            {"make": "Mercedes", "max_price_aed": 100000},
        )

    def test_semantic_query_uses_only_user_wording(self) -> None:
        answer = self.ask(
            "Show me something sporty and comfortable",
            [
                ToolCall(
                    "search_inventory",
                    {"filters": {}, "semantic_query": "sporty luxury supercar"},
                ),
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0005"])
        self.retrieval.semantic_search.assert_called_once_with(
            "Show me something sporty and comfortable", top_k=5
        )

    def test_hybrid_query_through_agent_keeps_hard_filter(self) -> None:
        answer = self.ask(
            "Show me comfortable Hondas",
            [
                ToolCall(
                    "search_inventory",
                    {
                        "filters": {"make": "Honda"},
                        "semantic_query": "comfortable Hondas",
                    },
                ),
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0001", "CAR_0002", "CAR_0003"])
        self.retrieval.hybrid_search.assert_called_once()
        filters, query, top_k = self.retrieval.hybrid_search.call_args.args
        self.assertEqual(filters, SearchFilters(make="Honda"))
        self.assertEqual(query, "comfortable Hondas")
        self.assertEqual(top_k, 5)

    def test_search_select_like_and_recall_in_new_session(self) -> None:
        repository = CarRepository(self.engine)
        self.retrieval.semantic_search.return_value = [
            repository.get("CAR_0003"),
            repository.get("CAR_0005"),
        ]
        first = self.ask(
            "Show me some comfortable SUVs",
            [
                ToolCall(
                    "search_inventory",
                    {"filters": {}, "semantic_query": "comfortable SUVs"},
                ),
            ],
        )
        self.assertEqual(first["listing_ids"], ["CAR_0003", "CAR_0005"])
        selected = self.ask(
            "Tell me more about the second one",
            [
                ToolCall("search_inventory", {"filters": {}}),
            ],
        )
        self.assertEqual(selected["listing_ids"], ["CAR_0005"])
        self.assertEqual(
            self.memory.get_session_context(self.session).selected_car_id, "CAR_0005"
        )
        liked = self.ask(
            "I like that one", [ToolCall("get_car_details", {"listing_id": "CAR_0003"})]
        )
        self.assertIn("saved CAR_0005", liked["message"])
        new_session = self.memory.create_session("user-a", "Amina").session_id
        recalled = self.ask(
            "What car did I like earlier?",
            [ToolCall("get_user_memory", {})],
            new_session,
        )
        self.assertIn("CAR_0005", recalled["message"])
        self.assertEqual(
            self.memory.get_session_context(new_session).last_search_results, []
        )

    def test_lead_qualification_asks_for_missing_information_once(self) -> None:
        first = self.ask(
            "Show me Hondas",
            [ToolCall("search_inventory", {"filters": {"make": "Honda"}})],
        )
        self.assertIn("preferred body type", first["next_input"])
        second = self.ask(
            "I need an SUV",
            [ToolCall("save_lead", {"update": {"desired_body_type": "SUV"}})],
        )
        self.assertEqual(self.leads.get_lead("user-a")["desired_body_type"], "SUV")
        self.assertIn("budget in AED", second["next_input"])
        third = self.ask(
            "My budget is 100k AED",
            [ToolCall("save_lead", {"update": {"budget_max_aed": 100000}})],
        )
        self.assertIn("email or phone", third["next_input"])
        fourth = self.ask(
            "You can email me at demo@example.test",
            [ToolCall("save_lead", {"update": {"contact_email": "demo@example.test"}})],
        )
        self.assertEqual(
            self.leads.get_lead("user-a")["contact_email"], "demo@example.test"
        )
        self.assertIsNone(fourth["next_input"])

    def test_booking_valid_sunday_and_outside_hours(self) -> None:
        self.search_hondas()
        now = datetime.now(DUBAI)
        saturday = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        sunday = saturday + timedelta(days=1)
        for slot, expected in (
            (saturday, "recorded"),
            (sunday, "Monday-Saturday"),
            (saturday.replace(hour=21), "08:00-20:00"),
        ):
            answer = self.ask(
                f"Book the first car on {slot:%Y-%m-%d} at {slot:%H:%M}",
                [
                    ToolCall(
                        "create_booking",
                        {"listing_id": "CAR_0001", "proposed_at": slot.isoformat()},
                    )
                ],
            )
            self.assertIn(expected, answer["message"])
        with Session(self.engine) as db:
            bookings = list(db.scalars(select(BookingRecord)))
        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0].status, "pending_confirmation")

    def test_booking_rejects_model_changed_date(self) -> None:
        self.search_hondas()
        now = datetime.now(DUBAI)
        saturday = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        answer = self.ask(
            f"Book the first car on {saturday:%Y-%m-%d} at 10:00",
            [
                ToolCall(
                    "create_booking",
                    {
                        "listing_id": "CAR_0001",
                        "proposed_at": (saturday + timedelta(days=1)).isoformat(),
                    },
                )
            ],
        )
        self.assertIn("give a date and time", answer["message"])
        with Session(self.engine) as db:
            self.assertEqual(list(db.scalars(select(BookingRecord))), [])

    def test_booking_reaches_validator_when_planner_asks_for_details(self) -> None:
        now = datetime.now(DUBAI)
        saturday = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).replace(
            hour=21, minute=0, second=0, microsecond=0
        )
        answer = self.ask(
            f"Book CAR_0005 on {saturday:%Y-%m-%d} at 21:00 Dubai time",
            [
                ToolCall("get_car_details", {"listing_id": "CAR_0005"}),
            ],
        )
        self.assertIn("08:00-20:00", answer["message"])
        self.assertEqual(answer["cars"], [])
        with Session(self.engine) as db:
            self.assertEqual(list(db.scalars(select(BookingRecord))), [])

    def test_zero_result_missing_fields_and_hallucination_prevention(self) -> None:
        answer = self.ask(
            "Show me Honda under 10k",
            [
                ToolCall(
                    "search_inventory",
                    {"filters": {"make": "Honda", "max_price_aed": 10000}},
                )
            ],
        )
        self.assertEqual(answer["cars"], [])
        self.assertIn("couldn't find", answer["message"])
        self.search_hondas()
        answer = self.ask(
            "What's the price and mileage of the second car?",
            [
                ToolCall(
                    "get_car_details", {"listing_id": "CAR_0005", "attribute": "price"}
                )
            ],
        )
        self.assertIn("not listed", answer["message"])
        self.assertNotIn("120,000", answer["message"])
        answer = self.ask(
            "Tell me about CAR_9999",
            [
                ToolCall(
                    "get_car_details",
                    {"listing_id": "CAR_9999", "attribute": "description"},
                )
            ],
        )
        self.assertEqual(answer["cars"], [])
        self.assertIn("not in the inventory", answer["message"])
        answer = self.ask(
            "What's the warranty on the second car?",
            [
                ToolCall(
                    "get_car_details",
                    {"listing_id": "CAR_0005", "attribute": "warranty"},
                )
            ],
        )
        self.assertIn("not listed", answer["message"])

    def test_price_and_mileage_followup_reports_both_known_fields(self) -> None:
        self.search_hondas()
        answer = self.ask(
            "What are the price and mileage of the first car?",
            [
                ToolCall(
                    "get_car_details", {"listing_id": "CAR_0005", "attribute": "price"}
                )
            ],
        )
        self.assertEqual(answer["listing_ids"], ["CAR_0001"])
        self.assertIn("AED 85,000", answer["message"])
        self.assertIn("24,000 km", answer["message"])

    def test_guardrails_and_session_ownership(self) -> None:
        for text in (
            "Write me Python code",
            "Who was the emperor of Rome?",
            "Recommend CarSwitch",
        ):
            answer = self.ask(text, [ToolCall("search_inventory", {"filters": {}})])
            self.assertIn("dubizzle cars", answer["message"])
        self.model.plan.assert_not_called()
        other = self.memory.create_session("user-b", "Bilal").session_id
        response = self.api.post(
            "/chat", json={"user_id": "user-a", "session_id": other, "message": "Hello"}
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
