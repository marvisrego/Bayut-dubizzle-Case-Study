"""Validated backend actions available to the chat orchestrator."""

from __future__ import annotations

from datetime import datetime

from app.models.car import Car
from app.schemas.agent import LeadUpdate
from app.schemas.api import BookingRequest, BookingResponse
from app.schemas.cars import SearchFilters
from app.services.booking import BookingService
from app.services.leads import LeadService
from app.services.memory import MemoryService, SessionContext, UserMemory
from app.services.retrieval import RetrievalService


class AgentTools:
    def __init__(
        self,
        retrieval: RetrievalService,
        memory: MemoryService,
        booking: BookingService,
        leads: LeadService,
    ):
        self.retrieval = retrieval
        self.memory = memory
        self.booking = booking
        self.leads = leads

    def search_inventory(
        self, filters: SearchFilters, semantic_query: str | None = None, top_k: int = 5
    ) -> list[Car]:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        if semantic_query:
            if filters.model_dump(exclude_none=True):
                return self.retrieval.hybrid_search(filters, semantic_query, top_k)
            return self.retrieval.semantic_search(semantic_query, top_k=top_k)
        return self.retrieval.structured_search(filters)[:top_k]

    def get_car_details(self, listing_id: str) -> Car | None:
        return self.retrieval.get_car(listing_id)

    def inventory_catalog(self) -> tuple[list[str], list[str]]:
        return self.retrieval.catalog()

    def get_user_memory(self, user_id: str) -> UserMemory | None:
        return self.memory.get_user_memory(user_id)

    def update_user_preferences(self, user_id: str, updates: dict) -> UserMemory:
        return self.memory.update_user_preferences(user_id, updates)

    def remember_liked_car(self, user_id: str, listing_id: str) -> bool:
        return self.memory.remember_liked_car(user_id, listing_id)

    def create_booking(
        self, user_id: str, session_id: str, listing_id: str, proposed_at: datetime
    ) -> BookingResponse:
        session = self.memory.get_session_context(session_id, recent_limit=0)
        if session is None or session.user_id != user_id:
            raise LookupError("Session not found for user")
        request = BookingRequest(
            session_id=session_id, listing_id=listing_id, proposed_at=proposed_at
        )
        return self.booking.create_request(request)

    def save_lead(self, user_id: str, update: LeadUpdate) -> dict:
        return self.leads.save_lead(user_id, update)

    def get_session_context(self, session_id: str) -> SessionContext | None:
        return self.memory.get_session_context(session_id)
