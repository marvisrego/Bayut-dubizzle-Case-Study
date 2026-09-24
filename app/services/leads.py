"""PostgreSQL lead upserts and an atomic local CSV export."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.state import LeadRecord, User
from app.schemas.agent import LeadUpdate

CSV_FIELDS = (
    "user_id",
    "name",
    "contact_email",
    "phone",
    "budget_min_aed",
    "budget_max_aed",
    "desired_make",
    "desired_model",
    "desired_body_type",
    "needs",
    "updated_at",
)


class LeadService:
    def __init__(self, engine: Engine, csv_path: Path | None = None):
        self.engine = engine
        self.csv_path = (
            csv_path or Path(__file__).resolve().parents[2] / "data" / "leads.csv"
        )

    def save_lead(self, user_id: str, update: LeadUpdate) -> dict:
        changes = update.model_dump(exclude_none=True)
        if not changes:
            raise ValueError("No lead information supplied")
        with Session(self.engine) as database, database.begin():
            user = database.get(User, user_id)
            if user is None:
                raise LookupError("User not found")
            lead = database.get(LeadRecord, user_id)
            if lead is None:
                lead = LeadRecord(
                    user_id=user_id,
                    name=user.display_name,
                    needs=[],
                    updated_at=datetime.now(UTC),
                )
                database.add(lead)
            lead.name = user.display_name
            for field, value in changes.items():
                if field == "needs":
                    lead.needs = list(dict.fromkeys(list(lead.needs or []) + value))[
                        :20
                    ]
                else:
                    setattr(lead, field, value)
            lead.updated_at = datetime.now(UTC)
        self.export_csv()
        return self.get_lead(user_id) or {}

    def get_lead(self, user_id: str) -> dict | None:
        with Session(self.engine) as database:
            lead = database.get(LeadRecord, user_id)
            if lead is None:
                return None
            return {field: getattr(lead, field) for field in CSV_FIELDS}

    def export_csv(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.csv_path) + ".lock")
        with lock, Session(self.engine) as database:
            leads = list(
                database.scalars(select(LeadRecord).order_by(LeadRecord.user_id))
            )
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    newline="",
                    delete=False,
                    dir=self.csv_path.parent,
                    prefix=".leads-",
                    suffix=".tmp",
                ) as handle:
                    temp_name = handle.name
                    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                    writer.writeheader()
                    for lead in leads:
                        row = {field: getattr(lead, field) for field in CSV_FIELDS}
                        row["needs"] = json.dumps(
                            row["needs"] or [], ensure_ascii=False
                        )
                        row["updated_at"] = row["updated_at"].isoformat()
                        writer.writerow(row)
                os.replace(temp_name, self.csv_path)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
