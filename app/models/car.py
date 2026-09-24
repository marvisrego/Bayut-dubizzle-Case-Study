"""Canonical workbook columns and committed vector-index state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


CANONICAL_COLUMNS = (
    "listing_id",
    "exact_fingerprint",
    "year",
    "make",
    "model",
    "trim",
    "title",
    "description",
    "photo_url",
    "source",
    "source_row",
    "source_listing_id",
    "source_refs",
    "year_original",
    "make_original",
    "model_original",
    "trim_original",
    "title_original",
    "description_original",
    "title_clean",
    "description_clean",
    "search_text",
    "embedding_text",
)


class Car(Base):
    __tablename__ = "cars"

    listing_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exact_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    trim: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    photo_url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_listing_id: Mapped[int | None] = mapped_column(Integer)
    source_refs: Mapped[str] = mapped_column(Text, nullable=False)
    year_original: Mapped[int] = mapped_column(Integer, nullable=False)
    make_original: Mapped[str] = mapped_column(Text, nullable=False)
    model_original: Mapped[Any] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    trim_original: Mapped[Any] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    description_original: Mapped[str] = mapped_column(Text, nullable=False)
    title_clean: Mapped[str] = mapped_column(Text, nullable=False)
    description_clean: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable facts are extracted only from explicit source listing text.
    price_aed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    mileage_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)


class CarEmbeddingState(Base):
    __tablename__ = "car_embedding_state"

    listing_id: Mapped[str] = mapped_column(
        Text, ForeignKey("cars.listing_id"), primary_key=True
    )
    embedding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
