"""Deterministic PostgreSQL inventory queries."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.car import Car
from app.schemas.cars import SearchFilters


class CarRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def filtered_query(filters: SearchFilters) -> Select:
        statement = select(Car)
        for field in ("make", "model", "trim", "source"):
            value = getattr(filters, field)
            if value is not None:
                statement = statement.where(
                    func.lower(getattr(Car, field)) == value.lower()
                )
        if filters.year is not None:
            statement = statement.where(Car.year == filters.year)
        for filter_name, column, operator in (
            ("min_year", Car.year, "min"),
            ("max_year", Car.year, "max"),
            ("min_price_aed", Car.price_aed, "min"),
            ("max_price_aed", Car.price_aed, "max"),
            ("min_mileage_km", Car.mileage_km, "min"),
            ("max_mileage_km", Car.mileage_km, "max"),
        ):
            value = getattr(filters, filter_name)
            if value is not None:
                statement = statement.where(
                    column >= value if operator == "min" else column <= value
                )
        return statement

    def structured_search(
        self, filters: SearchFilters, limit: int | None = None
    ) -> list[Car]:
        statement = self.filtered_query(filters).order_by(
            Car.year.desc(), Car.listing_id
        )
        if limit is not None:
            statement = statement.limit(limit)
        with Session(self.engine) as session:
            return list(session.scalars(statement))

    def eligible_ids(self, filters: SearchFilters) -> list[str]:
        statement = (
            self.filtered_query(filters)
            .with_only_columns(Car.listing_id)
            .order_by(Car.listing_id)
        )
        with Session(self.engine) as session:
            return list(session.scalars(statement))

    def get_many_ordered(self, listing_ids: list[str]) -> list[Car]:
        if not listing_ids:
            return []
        with Session(self.engine) as session:
            found = {
                car.listing_id: car
                for car in session.scalars(
                    select(Car).where(Car.listing_id.in_(listing_ids))
                )
            }
            return [
                found[listing_id] for listing_id in listing_ids if listing_id in found
            ]

    def get(self, listing_id: str) -> Car | None:
        with Session(self.engine) as session:
            return session.get(Car, listing_id)

    def count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Car)) or 0

    def catalog(self) -> tuple[list[str], list[str]]:
        with Session(self.engine) as session:
            makes = list(session.scalars(select(Car.make).distinct()))
            models = list(session.scalars(select(Car.model).distinct()))
        return makes, models
