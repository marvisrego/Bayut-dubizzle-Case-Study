"""Qdrant index with deterministic point IDs and PostgreSQL listing references."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.core.config import Settings


def point_id(listing_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"dubizzle/cars/{listing_id}"))


class VectorStore:
    def __init__(self, settings: Settings):
        self.collection = settings.qdrant_collection
        self.client = QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_key, timeout=60
        )
        self.vector_name: str | None = None

    def ensure_collection(self, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError("Embedding dimension must be positive")
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=dimensions, distance=models.Distance.COSINE
                ),
            )
            return
        config = self.client.get_collection(self.collection).config.params.vectors
        if isinstance(config, dict):
            if len(config) != 1:
                raise ValueError(
                    "Existing Qdrant collection must have exactly one vector field"
                )
            self.vector_name, config = next(iter(config.items()))
        if config.size != dimensions or config.distance != models.Distance.COSINE:
            raise ValueError(
                f"Qdrant expects {config.size} dimensions/{config.distance}; "
                f"NVIDIA returned {dimensions} dimensions/Cosine"
            )

    def existing_points(self, listing_ids: list[str]) -> dict[str, models.Record]:
        result: dict[str, models.Record] = {}
        for offset in range(0, len(listing_ids), 100):
            batch = listing_ids[offset : offset + 100]
            records = self.client.retrieve(
                collection_name=self.collection,
                ids=[point_id(listing_id) for listing_id in batch],
                with_payload=True,
                with_vectors=False,
            )
            result.update({str(record.id): record for record in records})
        return result

    def upsert(self, rows: list[dict], vectors: list[list[float]], model: str) -> None:
        if len(rows) != len(vectors):
            raise ValueError("Rows and vectors have different lengths")
        points = [
            models.PointStruct(
                id=point_id(row["listing_id"]),
                vector={self.vector_name: vector}
                if self.vector_name is not None
                else vector,
                payload={
                    "listing_id": row["listing_id"],
                    "year": row["year"],
                    "make": row["make"],
                    "model": row["model"],
                    "trim": row["trim"],
                    "embedding_hash": row["embedding_hash"],
                    "embedding_model": model,
                },
            )
            for row, vector in zip(rows, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection, points=points, wait=True)

    def search(
        self,
        vector: list[float],
        top_k: int = 5,
        allowed_listing_ids: list[str] | None = None,
    ) -> list[str]:
        if allowed_listing_ids is not None and not allowed_listing_ids:
            return []
        query_filter = (
            models.Filter(
                must=[
                    models.HasIdCondition(
                        has_id=[point_id(item) for item in allowed_listing_ids]
                    )
                ]
            )
            if allowed_listing_ids is not None
            else None
        )
        hits = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using=self.vector_name,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        ).points
        return [
            hit.payload["listing_id"]
            for hit in hits
            if hit.payload and hit.payload.get("listing_id")
        ]

    def all_points(self) -> list[models.Record]:
        records: list[models.Record] = []
        offset = None
        while True:
            page, offset = self.client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            records.extend(page)
            if offset is None:
                break
        return records
