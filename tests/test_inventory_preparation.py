"""Focused invariants for exact grouping and embedding text."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from inventory_text import has_noise, make_embedding_text
from prepare_inventory import build, exact_fingerprint


def source_record(
    *,
    source: str,
    source_row: int,
    description: str,
    photo_url: str,
    trim: str = "Sport",
) -> dict:
    record = {
        "source": source,
        "source_row": source_row,
        "source_listing_id": source_row if source == "cleaned" else None,
        "original": {
            "year": 2020.0,
            "make": "Example",
            "model": "ModelA",
            "trim": trim,
            "title": "2020 Example ModelA Sport",
            "description": description,
            "photo_url": photo_url,
        },
        "year": 2020,
        "make": "Example",
        "model": "ModelA",
        "trim": trim,
        "title_clean": "2020 Example ModelA Sport",
        "description_clean": description,
        "input_order": source_row,
    }
    record["exact_fingerprint"] = exact_fingerprint(record)
    return record


class ExactDeduplicationTests(unittest.TestCase):
    def test_fingerprint_ignores_provenance_and_photo_but_not_content(self) -> None:
        first = source_record(
            source="raw",
            source_row=2,
            description="GCC warranty. 42,000 km",
            photo_url="https://example.com/one.jpg",
        )
        second = source_record(
            source="cleaned",
            source_row=99,
            description="GCC   WARRANTY.\n42,000 km",
            photo_url="https://example.com/two.jpg",
        )
        changed = source_record(
            source="raw",
            source_row=3,
            description="GCC warranty. 43,000 km",
            photo_url="https://example.com/one.jpg",
        )
        self.assertEqual(first["exact_fingerprint"], second["exact_fingerprint"])
        self.assertNotEqual(first["exact_fingerprint"], changed["exact_fingerprint"])

    def test_exact_group_merges_and_ambiguous_block_stays_separate(self) -> None:
        first = source_record(
            source="raw",
            source_row=2,
            description="GCC warranty. 42,000 km",
            photo_url="https://example.com/one.jpg",
        )
        second = source_record(
            source="cleaned",
            source_row=99,
            description="GCC warranty. 42,000 km",
            photo_url="https://example.com/two.jpg",
        )
        ambiguous = source_record(
            source="raw",
            source_row=3,
            description="GCC warranty. 43,000 km",
            photo_url="https://example.com/three.jpg",
        )
        inventory, merges, conflicts, review, duplicate_groups = build(
            [first, ambiguous, second]
        )
        self.assertEqual((len(inventory), len(merges), duplicate_groups), (2, 1, 1))
        self.assertEqual(len(review), 1)
        self.assertEqual(
            len(conflicts), 1
        )  # Photo difference is audited, never scored.
        merged = next(row for row in inventory if row["source"] == "merged")
        self.assertEqual(len(json.loads(merged["source_refs"])), 2)
        self.assertEqual(merged["description_original"], "GCC warranty. 42,000 km")


class EmbeddingTextTests(unittest.TestCase):
    def test_retains_vehicle_facts_and_arabic_without_contact_noise(self) -> None:
        row = {
            "year": 2024,
            "make": "Example",
            "model": "ModelA",
            "trim": "Sport",
            "title_clean": "Example ModelA 2024 GCC",
            "description_clean": (
                "Example ModelA 2024 GCC. 42,000 km. 2-year warranty.\n"
                "سيارة بحالة ممتازة وبدون حوادث\n"
                "Contact us on WhatsApp +971501234567 or visit "
                "https://example.com/showroom\n"
                "Selling Price: AED 65,000"
            ),
        }
        result = make_embedding_text(row)
        for fact in (
            "42,000 km",
            "2-year warranty",
            "سيارة بحالة ممتازة",
            "AED 65,000",
        ):
            self.assertIn(fact, result)
        self.assertEqual(result.count("Example ModelA 2024 GCC"), 1)
        self.assertFalse(has_noise(result))

    def test_keeps_specs_before_financing_and_arabic_after_contact(self) -> None:
        row = {
            "year": 2019,
            "make": "Example",
            "model": "ModelA",
            "trim": "Sport",
            "title_clean": "Example ModelA 2019",
            "description_clean": (
                "American Spec - 36000 km - Price 32000 AED "
                "Service we provide: bank finance and registration.\n"
                "Contact us: +971501234567\n"
                "السيارة بحالة ممتازة بدون حوادث"
            ),
        }
        result = make_embedding_text(row)
        self.assertIn("36000 km", result)
        self.assertIn("32000 AED", result)
        self.assertIn("السيارة بحالة ممتازة", result)
        self.assertNotIn("bank finance", result.casefold())
        self.assertFalse(has_noise(result))


if __name__ == "__main__":
    unittest.main()
