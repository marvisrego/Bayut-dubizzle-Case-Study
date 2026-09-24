"""Explicit session state and persistent user preferences in PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unicodedata import normalize
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.state import (
    ChatMessage,
    ConversationSession,
    LikedCar,
    User,
    UserName,
    UserPreference,
)
from app.schemas.api import SessionResponse, UserResponse


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    user_id: str
    display_name: str
    last_search_results: list[str]
    selected_car_id: str | None
    active_filters: dict
    recent_messages: list[dict[str, str]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UserMemory:
    user_id: str
    display_name: str
    preferred_makes: list[str]
    preferred_models: list[str]
    preferred_body_type: str | None
    budget_min_aed: int | None
    budget_max_aed: int | None
    preferred_colors: list[str]
    min_year: int | None
    max_mileage_km: int | None
    other_preferences: list[str]
    liked_car_ids: list[str]


class MemoryService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def resolve_user(self, display_name: str) -> UserResponse:
        """Resolve a demo name to one UUID, claiming unique older profiles."""
        name = " ".join(normalize("NFKC", display_name).split())
        if not name:
            raise ValueError("Name must not be blank")
        key = name.casefold()
        now = datetime.now(UTC)
        try:
            with Session(self.engine) as database, database.begin():
                mapping = database.get(UserName, key)
                if mapping is not None:
                    user = database.get(User, mapping.user_id)
                    return UserResponse(
                        user_id=user.user_id, display_name=user.display_name
                    )

                # Older sessions had UUID users but no stable name lookup. Reuse a
                # unique match; ambiguous older names receive a fresh profile.
                matches = [
                    user
                    for user in database.scalars(select(User))
                    if " ".join(normalize("NFKC", user.display_name).split()).casefold()
                    == key
                ]
                user = matches[0] if len(matches) == 1 else None
                if user is None:
                    user = User(
                        user_id=str(uuid4()),
                        display_name=name,
                        created_at=now,
                        updated_at=now,
                    )
                    database.add(user)
                    database.flush()
                database.add(UserName(name_key=key, user_id=user.user_id))
                result = UserResponse(
                    user_id=user.user_id, display_name=user.display_name
                )
            return result
        except IntegrityError:
            # A concurrent request may have inserted the same name mapping.
            with Session(self.engine) as database:
                mapping = database.get(UserName, key)
                if mapping is None:
                    raise
                user = database.get(User, mapping.user_id)
                return UserResponse(
                    user_id=user.user_id, display_name=user.display_name
                )

    def create_session(self, user_id: str | None, display_name: str) -> SessionResponse:
        now = datetime.now(UTC)
        user_id = user_id or str(uuid4())
        session_id = str(uuid4())
        with Session(self.engine) as database, database.begin():
            user = database.get(User, user_id)
            if user is None:
                database.add(
                    User(
                        user_id=user_id,
                        display_name=display_name,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                user.display_name = display_name
                user.updated_at = now
            database.flush()  # Ensure the user exists before the session FK insert.
            database.add(
                ConversationSession(
                    session_id=session_id,
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                    last_search_ids=[],
                    active_filters={},
                )
            )
        return SessionResponse(
            session_id=session_id,
            user_id=user_id,
            display_name=display_name,
            created_at=now,
        )

    def get_session(self, session_id: str) -> SessionResponse | None:
        context = self.get_session_context(session_id, recent_limit=0)
        if context is None:
            return None
        return SessionResponse(
            session_id=context.session_id,
            user_id=context.user_id,
            display_name=context.display_name,
            created_at=context.created_at,
        )

    def get_session_context(
        self, session_id: str, recent_limit: int = 8
    ) -> SessionContext | None:
        with Session(self.engine) as database:
            current = database.get(ConversationSession, session_id)
            if current is None:
                return None
            user = database.get(User, current.user_id)
            if user is None:
                return None
            messages = []
            if recent_limit:
                messages = list(
                    database.scalars(
                        select(ChatMessage)
                        .where(ChatMessage.session_id == session_id)
                        .order_by(
                            ChatMessage.created_at.desc(), ChatMessage.message_id.desc()
                        )
                        .limit(recent_limit)
                    )
                )
            return SessionContext(
                session_id=session_id,
                user_id=current.user_id,
                display_name=user.display_name,
                last_search_results=list(current.last_search_ids or []),
                selected_car_id=current.selected_listing_id,
                active_filters=dict(current.active_filters or {}),
                recent_messages=[
                    {"role": item.role, "content": item.content[:500]}
                    for item in reversed(messages)
                ],
                created_at=current.created_at,
                updated_at=current.updated_at or current.created_at,
            )

    def record_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        *,
        search_ids: list[str] | None = None,
        selected_car_id: str | None = None,
        active_filters: dict | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with Session(self.engine) as database, database.begin():
            current = database.get(ConversationSession, session_id)
            if current is None:
                raise LookupError("Session not found")
            if search_ids is not None:
                current.last_search_ids = search_ids[:50]
                current.selected_listing_id = None
                current.active_filters = active_filters or {}
            if selected_car_id is not None:
                current.selected_listing_id = selected_car_id
            current.updated_at = now
            database.add_all(
                [
                    ChatMessage(
                        message_id=str(uuid4()),
                        session_id=session_id,
                        role="user",
                        content=user_message,
                        created_at=now,
                    ),
                    ChatMessage(
                        message_id=str(uuid4()),
                        session_id=session_id,
                        role="assistant",
                        content=assistant_message,
                        created_at=now + timedelta(microseconds=1),
                    ),
                ]
            )

    def get_user_memory(self, user_id: str) -> UserMemory | None:
        with Session(self.engine) as database:
            user = database.get(User, user_id)
            if user is None:
                return None
            preference = database.get(UserPreference, user_id)
            liked_ids = list(
                database.scalars(
                    select(LikedCar.listing_id)
                    .where(LikedCar.user_id == user_id)
                    .order_by(LikedCar.created_at, LikedCar.listing_id)
                )
            )
            return UserMemory(
                user_id=user_id,
                display_name=user.display_name,
                preferred_makes=list(preference.preferred_makes or [])
                if preference
                else [],
                preferred_models=list(preference.preferred_models or [])
                if preference
                else [],
                preferred_body_type=preference.preferred_body_type
                if preference
                else None,
                budget_min_aed=preference.budget_min_aed if preference else None,
                budget_max_aed=preference.budget_max_aed if preference else None,
                preferred_colors=list(preference.preferred_colors or [])
                if preference
                else [],
                min_year=preference.min_year if preference else None,
                max_mileage_km=preference.max_mileage_km if preference else None,
                other_preferences=list(preference.other_preferences or [])
                if preference
                else [],
                liked_car_ids=liked_ids,
            )

    def update_user_preferences(self, user_id: str, updates: dict) -> UserMemory:
        allowed = {
            "preferred_makes",
            "preferred_models",
            "preferred_body_type",
            "budget_min_aed",
            "budget_max_aed",
            "preferred_colors",
            "min_year",
            "max_mileage_km",
            "other_preferences",
        }
        if not updates or set(updates) - allowed:
            raise ValueError("Unsupported or empty preference update")
        now = datetime.now(UTC)
        with Session(self.engine) as database, database.begin():
            if database.get(User, user_id) is None:
                raise LookupError("User not found")
            preference = database.get(UserPreference, user_id)
            if preference is None:
                preference = UserPreference(
                    user_id=user_id,
                    preferred_makes=[],
                    preferred_models=[],
                    preferred_colors=[],
                    other_preferences=[],
                    updated_at=now,
                )
                database.add(preference)
            for field, value in updates.items():
                if field in (
                    "preferred_makes",
                    "preferred_models",
                    "preferred_colors",
                    "other_preferences",
                ):
                    existing = list(getattr(preference, field) or [])
                    setattr(
                        preference, field, list(dict.fromkeys(existing + value))[:20]
                    )
                else:
                    setattr(preference, field, value)
            preference.updated_at = now
        result = self.get_user_memory(user_id)
        assert result is not None
        return result

    def remember_liked_car(self, user_id: str, listing_id: str) -> bool:
        with Session(self.engine) as database, database.begin():
            if (
                database.get(User, user_id) is None
                or database.get(Car, listing_id) is None
            ):
                return False
            if database.get(LikedCar, (user_id, listing_id)) is None:
                database.add(
                    LikedCar(
                        user_id=user_id,
                        listing_id=listing_id,
                        created_at=datetime.now(UTC),
                    )
                )
        return True
