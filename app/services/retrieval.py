"""Source-grounded structured, semantic, and hybrid car retrieval."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from app.models.car import Car
from app.schemas.cars import SearchFilters
from app.services.car_repository import CarRepository
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore


class RetrievalService:
    def __init__(
        self,
        engine: Engine,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ):
        self.cars = CarRepository(engine)
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    @staticmethod
    def _check_query(query: str, top_k: int) -> str:
        query = query.strip()
        if not query or not 1 <= top_k <= 50:
            raise ValueError(
                "Provide a non-empty semantic query and top_k between 1 and 50"
            )
        return query

    def structured_search(self, filters: SearchFilters) -> list[Car]:
        return self.cars.structured_search(filters)

    def semantic_search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        top_k: int = 10,
    ) -> list[Car]:
        if filters is not None and filters.model_dump(exclude_none=True):
            return self.hybrid_search(filters, query, top_k)
        query = self._check_query(query, top_k)
        vector = self.embedding_service.embed_query(query)
        self.vector_store.ensure_collection(len(vector))
        listing_ids = self.vector_store.search(vector, top_k=top_k)
        return self.cars.get_many_ordered(listing_ids)

    def hybrid_search(
        self,
        filters: SearchFilters,
        semantic_query: str,
        top_k: int = 10,
    ) -> list[Car]:
        semantic_query = self._check_query(semantic_query, top_k)
        eligible_ids = self.cars.eligible_ids(filters)
        if not eligible_ids:
            return []
        vector = self.embedding_service.embed_query(semantic_query)
        self.vector_store.ensure_collection(len(vector))
        ranked_ids = self.vector_store.search(
            vector, top_k=top_k, allowed_listing_ids=eligible_ids
        )
        # Recheck SQL-approved IDs if a stale Qdrant point is returned.
        eligible_set = set(eligible_ids)
        return self.cars.get_many_ordered(
            [listing_id for listing_id in ranked_ids if listing_id in eligible_set]
        )

    def get_car(self, listing_id: str) -> Car | None:
        return self.cars.get(listing_id)

    def catalog(self) -> tuple[list[str], list[str]]:
        return self.cars.catalog()
