"""Standalone end-to-end semantic search against Qdrant and PostgreSQL.

Run: uv run python -m scripts.search_inventory "family SUV" --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import load_settings
from app.core.database import make_engine
from app.models.car import Car
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore


def search(query: str, top_k: int = 5) -> list[dict]:
    if not query.strip() or top_k < 1:
        raise ValueError("Provide a non-empty query and a positive top-k")
    settings = load_settings()
    service = EmbeddingService(settings)
    try:
        vector = service.embed_query(query)
    finally:
        service.close()
    store = VectorStore(settings)
    store.ensure_collection(len(vector))
    ids = store.search(vector, top_k)
    engine = make_engine(settings)
    try:
        with Session(engine) as session:
            cars = {
                car.listing_id: car
                for car in session.execute(
                    select(Car).where(Car.listing_id.in_(ids))
                ).scalars()
            }
            columns = [column.name for column in Car.__table__.columns]
            return [
                {name: getattr(cars[listing_id], name) for name in columns}
                for listing_id in ids
                if listing_id in cars
            ]
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    try:
        results = search(args.query, args.top_k)
    except ValueError as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - sanitize third-party errors at CLI boundary
        print(
            f"Search failed ({type(exc).__name__}); credentials and request "
            "data withheld",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
