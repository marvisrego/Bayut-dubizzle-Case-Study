"""Session, chat, booking, and health API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.cars import CarResponse


class HealthResponse(BaseModel):
    status: str
    postgres_ready: bool
    qdrant_ready: bool
    inventory_count: int | None
    vector_count: int | None


class ResolveUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value


class UserResponse(BaseModel):
    user_id: str
    display_name: str


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("user_id", "display_name")
    @classmethod
    def strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    display_name: str
    created_at: datetime


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("user_id", "session_id", "message")
    @classmethod
    def strip_chat_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value


class ChatResponse(BaseModel):
    message: str
    session_id: str
    cars: list[CarResponse] = Field(default_factory=list)
    listing_ids: list[str] = Field(default_factory=list)
    next_input: str | None = None


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    listing_id: str = Field(min_length=1)
    proposed_at: datetime

    @field_validator("proposed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("proposed_at must include a timezone offset")
        return value


class BookingResponse(BaseModel):
    booking_id: str
    session_id: str
    listing_id: str
    proposed_at: datetime
    status: str
    message: str
