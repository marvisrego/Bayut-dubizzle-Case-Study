"""Source-backed price and mileage extraction regression tests."""

from __future__ import annotations

import unittest

from app.services.vehicle_facts import extract_vehicle_facts
from scripts.ingest_inventory import DEFAULT_WORKBOOK, read_inventory


class VehicleFactTests(unittest.TestCase):
    def test_cash_price_and_odometer_win_over_monthly_and_warranty_limits(self) -> None:
        facts = extract_vehicle_facts(
            "Haval H9 2026",
            "AED 2,040 monthly for five years. AED 115,750 in cash. "
            "Warranty for six years or 200,000 km. Only 18 km mileage.",
        )
        self.assertEqual(facts["price_aed"], 115750)
        self.assertEqual(facts["mileage_km"], 18)
        self.assertIn("in cash", facts["price_evidence"])

    def test_monthly_payment_service_limit_and_speed_are_not_listing_facts(
        self,
    ) -> None:
        facts = extract_vehicle_facts(
            "AED 1,430 / Month | Ford Territory",
            "Warranty until 2028 or 100,000 kms. Next service at 40,000 km. "
            "Top speed 250 km/h.",
        )
        self.assertIsNone(facts["price_aed"])
        self.assertIsNone(facts["mileage_km"])

    def test_range_and_conflicting_prices_stay_unknown(self) -> None:
        facts = extract_vehicle_facts(
            "BYD EV 701KM",
            "Driving range 701KM per charge. AED 75,000 or AED 80,000 in cash.",
        )
        self.assertIsNone(facts["mileage_km"])
        self.assertEqual(facts["price_aed"], 80000)
        self.assertIsNone(
            extract_vehicle_facts("Car", "AED 75,000. AED 80,000.")["price_aed"]
        )

    def test_real_workbook_examples_and_coverage(self) -> None:
        rows = read_inventory(DEFAULT_WORKBOOK)
        facts = {
            row["listing_id"]: extract_vehicle_facts(row["title"], row["description"])
            for row in rows
        }
        self.assertEqual(facts["CAR_0005"]["price_aed"], 115750)
        self.assertEqual(facts["CAR_0005"]["mileage_km"], 18)
        self.assertIsNone(facts["CAR_0003"]["mileage_km"])
        self.assertEqual(facts["CAR_0105"]["price_aed"], 1349999)
        self.assertEqual(facts["CAR_0105"]["mileage_km"], 18845)
        self.assertEqual(facts["CAR_0052"]["mileage_km"], 26106)
        self.assertEqual(facts["CAR_0039"]["price_aed"], 25000)
        self.assertEqual(facts["CAR_0025"]["price_aed"], 105000)
        self.assertEqual(facts["CAR_0025"]["mileage_km"], 150000)
        self.assertEqual(facts["CAR_0053"]["price_aed"], 79000)
        self.assertEqual(facts["CAR_0181"]["mileage_km"], 23900)
        self.assertGreaterEqual(
            sum(value["price_aed"] is not None for value in facts.values()), 35
        )
        self.assertGreaterEqual(
            sum(value["mileage_km"] is not None for value in facts.values()), 80
        )


if __name__ == "__main__":
    unittest.main()
