"""Validate Dubai viewing windows and record simulated requests."""

from __future__ import annotations

from datetime import UTC, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.state import BookingRecord, ConversationSession
from app.schemas.api import BookingRequest, BookingResponse

DUBAI = ZoneInfo("Asia/Dubai")


class BookingError(ValueError):
    pass


class BookingService:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def validate_slot(proposed_at: datetime, now: datetime | None = None) -> datetime:
        if proposed_at.tzinfo is None or proposed_at.utcoffset() is None:
            raise BookingError("A timezone-aware proposed_at is required")
        local = proposed_at.astimezone(DUBAI)
        now = now or datetime.now(UTC)
        if local <= now.astimezone(DUBAI):
            raise BookingError("The proposed slot must be in the future")
        if local.weekday() == 6 or not time(8, 0) <= local.time().replace(
            tzinfo=None
        ) <= time(20, 0):
            raise BookingError(
                "Viewing requests must be Monday-Saturday, 08:00-20:00 Dubai time"
            )
        return local

    def create_request(self, request: BookingRequest) -> BookingResponse:
        local = self.validate_slot(request.proposed_at)
        booking_id = str(uuid4())
        with Session(self.engine) as database, database.begin():
            if database.get(ConversationSession, request.session_id) is None:
                raise LookupError("Session not found")
            if database.get(Car, request.listing_id) is None:
                raise LookupError("Car not found")
            database.add(
                BookingRecord(
                    booking_id=booking_id,
                    session_id=request.session_id,
                    listing_id=request.listing_id,
                    proposed_at=local,
                    status="pending_confirmation",
                    created_at=datetime.now(UTC),
                )
            )
        return BookingResponse(
            booking_id=booking_id,
            session_id=request.session_id,
            listing_id=request.listing_id,
            proposed_at=local,
            status="pending_confirmation",
            message=(
                "Simulated viewing request recorded; slot availability is not "
                "confirmed."
            ),
        )
