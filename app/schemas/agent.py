"""Validated tool inputs for user memory and lead records."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_makes: list[str] | None = None
    preferred_models: list[str] | None = None
    preferred_body_type: str | None = None
    budget_min_aed: int | None = Field(default=None, ge=0)
    budget_max_aed: int | None = Field(default=None, ge=0)
    preferred_colors: list[str] | None = None
    min_year: int | None = Field(default=None, ge=1900, le=2100)
    max_mileage_km: int | None = Field(default=None, ge=0)
    other_preferences: list[str] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> PreferenceUpdate:
        if (
            self.budget_min_aed is not None
            and self.budget_max_aed is not None
            and self.budget_min_aed > self.budget_max_aed
        ):
            raise ValueError("Minimum budget exceeds maximum budget")
        return self


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_email: str | None = None
    phone: str | None = None
    budget_min_aed: int | None = Field(default=None, ge=0)
    budget_max_aed: int | None = Field(default=None, ge=0)
    desired_make: str | None = None
    desired_model: str | None = None
    desired_body_type: str | None = None
    needs: list[str] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> LeadUpdate:
        if (
            self.budget_min_aed is not None
            and self.budget_max_aed is not None
            and self.budget_min_aed > self.budget_max_aed
        ):
            raise ValueError("Minimum budget exceeds maximum budget")
        return self
