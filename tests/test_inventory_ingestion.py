"""Focused offline checks for canonical import and vector indexing behavior."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from qdrant_client import QdrantClient, models

from app.core.config import Settings, load_settings
from app.models.car import CANONICAL_COLUMNS
from app.services.embedding_service import EmbeddingService, text_hash
from app.services.vector_store import VectorStore, point_id
from scripts.ingest_inventory import (
    DEFAULT_WORKBOOK,
    IngestionReport,
    index_vectors,
    read_inventory,
    safe_failure,
)


class InventorySourceTests(unittest.TestCase):
    def test_merged_sheet_matches_all_database_columns_and_preserves_unicode(
        self,
    ) -> None:
        rows = read_inventory(DEFAULT_WORKBOOK)
        self.assertEqual(len(rows), 189)
        self.assertEqual(len({row["listing_id"] for row in rows}), 189)
        self.assertEqual(set(rows[0]), set(CANONICAL_COLUMNS))
        self.assertTrue(
            any(
                any("\u0600" <= c <= "\u06ff" for c in row["description_original"])
                for row in rows
            )
        )

    def test_hash_changes_only_when_meaningful_text_changes(self) -> None:
        self.assertEqual(text_hash("  سيارة   عائلية  "), text_hash("سيارة عائلية"))
        self.assertNotEqual(text_hash("سيارة عائلية"), text_hash("سيارة رياضية"))


class ConfigurationTests(unittest.TestCase):
    def test_password_with_url_reserved_characters_is_encoded_by_sqlalchemy(
        self,
    ) -> None:
        settings = Settings(
            db_user="postgres", db_password="p@ss:/?#", db_host="db.example.test"
        )
        url = settings.sqlalchemy_url.render_as_string(hide_password=False)
        self.assertIn("p%40ss%3A%2F%3F%23", url)
        self.assertNotIn("p@ss:/?#", repr(settings))

    def test_full_postgres_uri_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text(
                "Supabase_Link=postgresql://postgres.project:old@pooler.example.test:5432/postgres\n"
                "Supabase_Pass=new-secret\nuser=wrong\nport=6543\ndatabase=wrong\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(env, require_vector=False)
        self.assertEqual(settings.db_host, "pooler.example.test")
        self.assertEqual(settings.db_user, "postgres.project")
        self.assertEqual(settings.db_port, 5432)
        self.assertEqual(settings.db_name, "postgres")
        self.assertEqual(settings.db_password, "old")
        self.assertEqual(settings.sqlalchemy_url.username, "postgres.project")

    def test_error_message_classification_omits_host_and_password(self) -> None:
        error = RuntimeError(
            "could not translate host db.private.test with password secret"
        )
        safe = safe_failure(error)
        self.assertIn("did not resolve", safe)
        self.assertNotIn("secret", safe)
        self.assertNotIn("db.private.test", safe)


class EmbeddingTests(unittest.TestCase):
    def test_429_retry_then_ordered_batch_vectors(self) -> None:
        settings = Settings(
            db_user="postgres",
            db_password="secret",
            db_host="db.example.test",
            nvidia_key="secret",
        )
        with tempfile.TemporaryDirectory() as directory:
            service = EmbeddingService(settings, Path(directory) / "rate.json")
            service.limiter.acquire = Mock()
            service.client.post = Mock(
                side_effect=[
                    httpx.Response(429, headers={"Retry-After": "0"}),
                    httpx.Response(
                        200,
                        json={
                            "data": [
                                {"index": 1, "embedding": [0.0, 1.0]},
                                {"index": 0, "embedding": [1.0, 0.0]},
                            ]
                        },
                    ),
                ]
            )
            with patch("app.services.embedding_service.time.sleep") as sleep:
                vectors = service.embed_passages(["first", "second"])
            self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
            self.assertEqual(service.request_count, 2)
            sleep.assert_called_once_with(0.0)
            service.close()

    def test_rejected_large_batch_is_split(self) -> None:
        settings = Settings(
            db_user="postgres", db_password="secret", db_host="db.example.test"
        )
        with tempfile.TemporaryDirectory() as directory:
            service = EmbeddingService(settings, Path(directory) / "rate.json")
            service.limiter.acquire = Mock()
            service.client.post = Mock(
                side_effect=[
                    httpx.Response(413),
                    httpx.Response(
                        200, json={"data": [{"index": 0, "embedding": [1.0]}]}
                    ),
                    httpx.Response(
                        200, json={"data": [{"index": 0, "embedding": [2.0]}]}
                    ),
                ]
            )
            self.assertEqual(service.embed_passages(["one", "two"]), [[1.0], [2.0]])
            self.assertEqual(service.request_count, 3)
            service.close()


class QdrantTests(unittest.TestCase):
    def test_existing_named_vector_dimension_and_idempotent_upsert(self) -> None:
        client = QdrantClient(":memory:")
        client.create_collection(
            collection_name="cars",
            vectors_config={
                "": models.VectorParams(size=3, distance=models.Distance.COSINE)
            },
        )
        store = VectorStore.__new__(VectorStore)
        store.collection = "cars"
        store.client = client
        store.vector_name = None
        store.ensure_collection(3)
        self.assertEqual(store.vector_name, "")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            store.ensure_collection(2)
        row = {
            "listing_id": "CAR_0001",
            "year": 2022,
            "make": "Toyota",
            "model": "RAV4",
            "trim": "X",
            "embedding_hash": "abc",
        }
        store.upsert([row], [[1.0, 0.0, 0.0]], "test-model")
        store.upsert([row], [[1.0, 0.0, 0.0]], "test-model")
        self.assertEqual(client.count("cars", exact=True).count, 1)
        self.assertEqual(store.search([1.0, 0.0, 0.0], 1), ["CAR_0001"])
        self.assertEqual(str(store.all_points()[0].id), point_id("CAR_0001"))

    def test_unchanged_second_run_makes_zero_embedding_calls(self) -> None:
        settings = Settings(
            db_user="postgres", db_password="secret", db_host="db.example.test"
        )
        rows = [
            {
                "listing_id": "CAR_0001",
                "embedding_text": "سيارة عائلية",
                "year": 2022,
                "make": "Toyota",
                "model": "RAV4",
                "trim": "X",
            }
        ]
        fingerprint = text_hash(rows[0]["embedding_text"])
        point = SimpleNamespace(
            payload={
                "listing_id": "CAR_0001",
                "embedding_hash": fingerprint,
                "embedding_model": settings.nvidia_model,
                "year": 2022,
                "make": "Toyota",
                "model": "RAV4",
                "trim": "X",
            }
        )
        store = Mock()
        store.collection = settings.qdrant_collection
        store.client.collection_exists.return_value = True
        store.existing_points.return_value = {point_id("CAR_0001"): point}
        store.client.count.return_value.count = 1
        states = {
            "CAR_0001": SimpleNamespace(
                embedding_hash=fingerprint,
                model=settings.nvidia_model,
                dimensions=2048,
            )
        }
        with (
            patch("scripts.ingest_inventory.VectorStore", return_value=store),
            patch("scripts.ingest_inventory._states", return_value=states),
            patch("scripts.ingest_inventory.EmbeddingService") as embedding_service,
        ):
            report = IngestionReport()
            index_vectors(Mock(), rows, settings, report)
        embedding_service.assert_not_called()
        self.assertEqual(report.embeddings_requested, 0)
        self.assertEqual(report.embeddings_skipped_unchanged, 1)
        self.assertEqual(report.qdrant_vector_count, 1)


if __name__ == "__main__":
    unittest.main()
