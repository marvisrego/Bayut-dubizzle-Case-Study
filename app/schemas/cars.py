"""Search filters and source-backed vehicle responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    make: str | None = None
    model: str | None = None
    trim: str | None = None
    source: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    min_year: int | None = Field(default=None, ge=1900, le=2100)
    max_year: int | None = Field(default=None, ge=1900, le=2100)
    min_price_aed: int | None = Field(default=None, ge=0)
    max_price_aed: int | None = Field(default=None, ge=0)
    min_mileage_km: int | None = Field(default=None, ge=0)
    max_mileage_km: int | None = Field(default=None, ge=0)

    @field_validator("make", "model", "trim", "source")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Text filters cannot be empty")
        return value

    @model_validator(mode="after")
    def valid_ranges(self) -> SearchFilters:
        for low, high in (
            (self.min_year, self.max_year),
            (self.min_price_aed, self.max_price_aed),
            (self.min_mileage_km, self.max_mileage_km),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError("Minimum filter value exceeds maximum")
        if self.year is not None and (
            self.min_year is not None
            and self.year < self.min_year
            or self.max_year is not None
            and self.year > self.max_year
        ):
            raise ValueError("Exact year conflicts with year range")
        return self


class CarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    listing_id: str
    year: int
    make: str
    model: str
    trim: str
    title: str
    description: str
    photo_url: str
    source: str
    source_refs: str
    title_original: str
    description_original: str
    title_clean: str
    description_clean: str
    price_aed: int | None
    mileage_km: int | None
    price_evidence: str | None
    mileage_evidence: str | None
    model_original: Any
    trim_original: Any


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["structured", "semantic", "hybrid"]
    filters: SearchFilters = Field(default_factory=SearchFilters)
    semantic_query: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_mode(self) -> SearchRequest:
        if (
            self.mode in ("semantic", "hybrid")
            and not (self.semantic_query or "").strip()
        ):
            raise ValueError(
                "semantic_query is required for semantic and hybrid search"
            )
        if self.semantic_query is not None:
            self.semantic_query = self.semantic_query.strip()
        return self


class SearchResponse(BaseModel):
    results: list[CarResponse]
    count: int
