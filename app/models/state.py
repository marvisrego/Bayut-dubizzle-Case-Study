"""Persistent user sessions and simulated viewing requests."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.car import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserName(Base):
    """Name-only demo identity lookup; the UUID in users remains the user key."""

    __tablename__ = "user_names"

    name_key: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.user_id"), nullable=False
    )


class ConversationSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    selected_listing_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_filters: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    last_search_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )


class BookingRecord(Base):
    __tablename__ = "booking_requests"

    booking_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.session_id"), nullable=False
    )
    listing_id: Mapped[str] = mapped_column(
        Text, ForeignKey("cars.listing_id"), nullable=False
    )
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ChatMessage(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.user_id"), primary_key=True
    )
    preferred_makes: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    preferred_models: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    preferred_body_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_min_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_max_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_colors: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    min_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    other_preferences: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LikedCar(Base):
    __tablename__ = "liked_cars"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.user_id"), primary_key=True
    )
    listing_id: Mapped[str] = mapped_column(
        Text, ForeignKey("cars.listing_id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LeadRecord(Base):
    __tablename__ = "leads"

    user_id: Mapped[str] = mapped_column(
        Text, ForeignKey("users.user_id"), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_min_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_max_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_make: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_body_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
