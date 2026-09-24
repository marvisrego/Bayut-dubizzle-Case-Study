"""SQLAlchemy engine and inventory-only schema creation."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.models import state as _state  # noqa: F401 - register metadata tables
from app.models.car import Base
from app.models.state import UserName


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10, "sslmode": "require"},
        future=True,
    )


def ensure_schema(engine: Engine) -> None:
    # create_all checks existence and never drops an existing table.
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        # Existing live inventory tables predate these nullable factual fields.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE cars ADD COLUMN IF NOT EXISTS price_aed INTEGER")
            )
            connection.execute(
                text("ALTER TABLE cars ADD COLUMN IF NOT EXISTS mileage_km INTEGER")
            )
            connection.execute(
                text("ALTER TABLE cars ADD COLUMN IF NOT EXISTS price_evidence TEXT")
            )
            connection.execute(
                text("ALTER TABLE cars ADD COLUMN IF NOT EXISTS mileage_evidence TEXT")
            )
            connection.execute(
                text(
                    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                    "updated_at TIMESTAMPTZ"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS active_filters JSONB"
                )
            )
            connection.execute(
                text(
                    "UPDATE sessions SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )


def ensure_identity_schema(engine: Engine) -> None:
    """Add the name lookup to an existing database without touching other tables."""
    UserName.__table__.create(engine, checkfirst=True)
