"""Offline SQL + Qdrant retrieval and FastAPI contract tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.main import app
from app.models import state as _state  # noqa: F401 - register metadata
from app.models.car import Base, Car
from app.models.state import User
from app.schemas.cars import SearchFilters
from app.services.agent import ChatAgent
from app.services.agent_tools import AgentTools
from app.services.booking import DUBAI, BookingService
from app.services.car_repository import CarRepository
from app.services.leads import LeadService
from app.services.memory import MemoryService
from app.services.nvidia_chat import ToolCall
from app.services.retrieval import RetrievalService
from app.services.vector_store import VectorStore


def make_car(
    listing_id: str,
    year: int,
    make: str,
    model: str,
    price: int | None,
    mileage: int | None,
) -> Car:
    title = f"{year} {make} {model}"
    return Car(
        listing_id=listing_id,
        exact_fingerprint=listing_id,
        year=year,
        make=make,
        model=model,
        trim="Base",
        title=title,
        description=f"Seller description for {title}",
        photo_url="https://example.test/car.jpg",
        source="raw",
        source_row=2,
        source_listing_id=None,
        source_refs="raw:2",
        year_original=year,
        make_original=make,
        model_original=model,
        trim_original="Base",
        title_original=title,
        description_original=f"Original seller description for {title}",
        title_clean=title,
        description_clean=f"Seller description for {title}",
        search_text=title,
        embedding_text=title,
        price_aed=price,
        mileage_km=mileage,
    )


class RetrievalAndApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as database, database.begin():
            database.add_all(
                [
                    make_car("CAR_A", 2022, "Toyota", "RAV4", 80000, 50000),
                    make_car("CAR_B", 2020, "Toyota", "Camry", None, None),
                    make_car("CAR_C", 2021, "BMW", "X5", 120000, 30000),
                ]
            )
        client = QdrantClient(":memory:")
        client.create_collection(
            collection_name="cars",
            vectors_config={
                "": models.VectorParams(size=3, distance=models.Distance.COSINE)
            },
        )
        self.store = VectorStore.__new__(VectorStore)
        self.store.collection = "cars"
        self.store.client = client
        self.store.vector_name = None
        self.store.ensure_collection(3)
        rows = [
            {
                "listing_id": car_id,
                "year": year,
                "make": make,
                "model": model,
                "trim": "Base",
                "embedding_hash": car_id,
            }
            for car_id, year, make, model in (
                ("CAR_A", 2022, "Toyota", "RAV4"),
                ("CAR_B", 2020, "Toyota", "Camry"),
                ("CAR_C", 2021, "BMW", "X5"),
            )
        ]
        self.store.upsert(rows, [[1, 0, 0], [0.8, 0.2, 0], [0, 1, 0]], "test-model")
        self.embedder = Mock()
        self.embedder.embed_query.return_value = [0, 1, 0]
        self.retrieval = RetrievalService(self.engine, self.embedder, self.store)
        self.memory = MemoryService(self.engine)
        self.booking = BookingService(self.engine)
        self.chat_model = Mock()
        self.chat_model.plan.return_value = [ToolCall("greet", {})]
        self.agent = ChatAgent(
            AgentTools(
                self.retrieval, self.memory, self.booking, LeadService(self.engine)
            ),
            self.chat_model,
        )
        app.dependency_overrides = {
            dependencies.get_engine: lambda: self.engine,
            dependencies.get_vector_store: lambda: self.store,
            dependencies.get_car_repository: lambda: CarRepository(self.engine),
            dependencies.get_retrieval_service: lambda: self.retrieval,
            dependencies.get_memory_service: lambda: self.memory,
            dependencies.get_booking_service: lambda: self.booking,
            dependencies.get_agent_service: lambda: self.agent,
        }
        self.api = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.api.close()
        self.engine.dispose()

    def test_structured_search_and_missing_fields(self) -> None:
        found = self.retrieval.structured_search(
            SearchFilters(make="toyota", min_year=2021)
        )
        self.assertEqual([car.listing_id for car in found], ["CAR_A"])
        priced = self.retrieval.structured_search(SearchFilters(max_price_aed=90000))
        self.assertEqual([car.listing_id for car in priced], ["CAR_A"])
        self.assertIsNone(self.retrieval.get_car("CAR_B").price_aed)
        self.assertIsNone(self.retrieval.get_car("CAR_B").mileage_km)
        self.assertEqual(
            self.retrieval.structured_search(SearchFilters(max_mileage_km=40000))[
                0
            ].listing_id,
            "CAR_C",
        )

    def test_fuzzy_semantic_search_resolves_qdrant_ids_to_full_postgres_rows(
        self,
    ) -> None:
        found = self.retrieval.semantic_search("sporty luxury crossover", top_k=1)
        self.assertEqual([car.listing_id for car in found], ["CAR_C"])
        self.assertEqual(
            found[0].description_original, "Original seller description for 2021 BMW X5"
        )
        self.embedder.embed_query.assert_called_once_with("sporty luxury crossover")

    def test_hybrid_hard_filters_beat_stronger_semantic_result(self) -> None:
        found = self.retrieval.hybrid_search(
            SearchFilters(make="Toyota", min_year=2022, max_price_aed=90000),
            "sporty luxury crossover",
            top_k=3,
        )
        self.assertEqual([car.listing_id for car in found], ["CAR_A"])
        self.assertNotIn("CAR_C", [car.listing_id for car in found])

    def test_zero_result_skips_embedding_and_unknown_price_never_passes_budget(
        self,
    ) -> None:
        self.assertEqual(
            self.retrieval.structured_search(SearchFilters(max_price_aed=1000)), []
        )
        self.assertEqual(
            self.retrieval.hybrid_search(
                SearchFilters(max_price_aed=1000), "cheap car"
            ),
            [],
        )
        self.embedder.embed_query.assert_not_called()
        self.assertEqual(
            self.retrieval.semantic_search(
                "family car", SearchFilters(max_price_aed=90000)
            )[0].listing_id,
            "CAR_A",
        )

    def test_api_health_car_search_and_agent_boundary(self) -> None:
        health = self.api.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ready")
        car = self.api.get("/cars/CAR_B")
        self.assertEqual(car.status_code, 200)
        self.assertIsNone(car.json()["price_aed"])
        self.assertIsNone(car.json()["mileage_km"])
        self.assertEqual(self.api.get("/cars/MISSING").status_code, 404)
        search = self.api.post(
            "/cars/search",
            json={
                "mode": "hybrid",
                "filters": {"make": "Toyota", "min_year": 2022},
                "semantic_query": "sporty luxury crossover",
                "top_k": 3,
            },
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(
            [row["listing_id"] for row in search.json()["results"]], ["CAR_A"]
        )
        self.assertEqual(
            self.api.post(
                "/cars/search",
                json={
                    "mode": "structured",
                    "filters": {"max_price_aed": 1000},
                },
            ).json()["results"],
            [],
        )
        self.assertEqual(
            self.api.post(
                "/cars/search",
                json={
                    "mode": "structured",
                    "filters": {"color": "white"},
                },
            ).status_code,
            422,
        )
        created = self.api.post(
            "/sessions", json={"user_id": "user-1", "display_name": "Amal"}
        )
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["session_id"]
        self.assertEqual(
            self.api.get(f"/sessions/{session_id}").json()["display_name"], "Amal"
        )
        chat = self.api.post(
            "/chat", json={"session_id": session_id, "message": "Hello"}
        )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["session_id"], session_id)

    def test_backend_generates_and_persists_user_id(self) -> None:
        first = self.api.post("/sessions", json={"display_name": "Amina"})
        self.assertEqual(first.status_code, 201)
        identity = first.json()
        self.assertEqual(str(UUID(identity["user_id"])), identity["user_id"])
        with Session(self.engine) as database:
            self.assertEqual(
                database.get(User, identity["user_id"]).display_name, "Amina"
            )
        returning = self.api.post(
            "/sessions",
            json={
                "user_id": identity["user_id"],
                "display_name": "Amina",
            },
        )
        self.assertEqual(returning.status_code, 201)
        self.assertEqual(returning.json()["user_id"], identity["user_id"])
        self.assertNotEqual(returning.json()["session_id"], identity["session_id"])
        same_name_other_person = self.api.post(
            "/sessions", json={"display_name": "Amina"}
        )
        self.assertNotEqual(
            same_name_other_person.json()["user_id"], identity["user_id"]
        )

    def test_resolve_user_reuses_stable_uuid_and_separates_sessions(self) -> None:
        first = self.api.post("/users", json={"display_name": "Test User"})
        self.assertEqual(first.status_code, 200, first.text)
        user_id = first.json()["user_id"]
        self.assertEqual(str(UUID(user_id)), user_id)
        session_a = self.api.post(
            "/sessions",
            json={
                "user_id": user_id,
                "display_name": "Test User",
            },
        ).json()
        returning = self.api.post("/users", json={"display_name": "  test   user "})
        self.assertEqual(returning.status_code, 200, returning.text)
        self.assertEqual(returning.json()["user_id"], user_id)
        session_b = self.api.post(
            "/sessions",
            json={
                "user_id": user_id,
                "display_name": returning.json()["display_name"],
            },
        ).json()
        self.assertNotEqual(session_a["session_id"], session_b["session_id"])
        self.assertEqual(session_b["user_id"], user_id)
        with Session(self.engine) as database:
            self.assertEqual(database.get(User, user_id).display_name, "Test User")

    def test_resolve_user_claims_unique_legacy_name_without_merging_duplicates(
        self,
    ) -> None:
        legacy = self.api.post(
            "/sessions", json={"display_name": "Legacy User"}
        ).json()["user_id"]
        claimed = self.api.post("/users", json={"display_name": "legacy user"}).json()[
            "user_id"
        ]
        self.assertEqual(claimed, legacy)

        older_a = self.api.post(
            "/sessions", json={"display_name": "Shared Name"}
        ).json()["user_id"]
        older_b = self.api.post(
            "/sessions", json={"display_name": "Shared Name"}
        ).json()["user_id"]
        resolved = self.api.post("/users", json={"display_name": "Shared Name"}).json()[
            "user_id"
        ]
        self.assertNotIn(resolved, {older_a, older_b})
        self.assertEqual(
            self.api.post("/users", json={"display_name": "shared name"}).json()[
                "user_id"
            ],
            resolved,
        )

    def test_booking_window_and_pending_confirmation(self) -> None:
        session_id = self.memory.create_session("user-2", "Sam").session_id
        today = datetime.now(DUBAI)
        days_until_saturday = (5 - today.weekday()) % 7 or 7
        saturday = (today + timedelta(days=days_until_saturday)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        body = {
            "session_id": session_id,
            "listing_id": "CAR_A",
            "proposed_at": saturday.isoformat(),
        }
        accepted = self.api.post("/bookings", json=body)
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(accepted.json()["status"], "pending_confirmation")
        self.assertIn("not confirmed", accepted.json()["message"])
        # Every canonical listing is managed, including those without a price.
        another = self.api.post("/bookings", json={**body, "listing_id": "CAR_B"})
        self.assertEqual(another.status_code, 202)
        self.assertEqual(another.json()["status"], "pending_confirmation")
        self.assertEqual(
            self.api.post(
                "/bookings",
                json={
                    **body,
                    "proposed_at": (saturday + timedelta(days=1)).isoformat(),
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.api.post(
                "/bookings",
                json={
                    **body,
                    "proposed_at": saturday.replace(hour=21).isoformat(),
                },
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
