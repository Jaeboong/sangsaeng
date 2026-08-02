from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.comparison.weekly_comparison import (
    METRICS,
    OUTPUT_FIELDS,
    build_weekly_comparison,
    compare_weeks,
    resolve_current_week_start,
)
from src.metrics.calculate_metrics import RATIO_SCALE, read_normalized_input


ROOT = Path(__file__).resolve().parents[2]


def row(
    day: date,
    *,
    campaign: str = "A",
    channel: str = "meta",
    cost: object = "100",
    impressions: object = "1000",
    clicks: object = "100",
    conversions: object = "10",
    revenue: object = "200",
    vat_basis: str = "included",
    conversion_definition: str = "purchase",
    revenue_definition: str = "purchase_value",
) -> dict[str, object]:
    return {
        "date": day.isoformat(),
        "channel": channel,
        "campaign": campaign,
        "cost": cost,
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "revenue": revenue,
        "vat_basis": vat_basis,
        "conversion_definition": conversion_definition,
        "revenue_definition": revenue_definition,
    }


def week(start: date, **kwargs: object) -> list[dict[str, object]]:
    return [row(start + timedelta(days=offset), **kwargs) for offset in range(7)]


def metric(rows: list[dict[str, object]], campaign: str, name: str) -> dict[str, object]:
    return next(item for item in rows if item["campaign"] == campaign and item["metric"] == name)


class WeeklyComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_start = date(2026, 7, 13)
        self.current_start = date(2026, 7, 20)

    def test_latest_complete_iso_week_and_two_periods(self) -> None:
        rows = week(self.previous_start) + week(self.current_start)

        resolved, comparisons = build_weekly_comparison(rows)

        self.assertEqual(self.current_start, resolved)
        self.assertEqual(len(METRICS), len(comparisons))
        self.assertEqual("2026-07-13", comparisons[0]["previous_week_start"])
        self.assertEqual("2026-07-26", comparisons[0]["current_week_end"])
        self.assertTrue(all(item["previous_days"] == 7 for item in comparisons))
        self.assertTrue(all(item["current_days"] == 7 for item in comparisons))

    def test_ratios_are_recalculated_after_weekly_source_sums(self) -> None:
        previous = [
            row(self.previous_start, cost="100", conversions="1"),
            row(self.previous_start + timedelta(days=1), cost="200", conversions="9"),
        ]
        current = [row(self.current_start, cost="400", conversions="10")]

        comparisons = compare_weeks(previous + current, self.current_start)

        cpa = metric(comparisons, "A", "cpa")
        self.assertEqual(Decimal("30.00"), cpa["previous_value"])
        self.assertEqual(Decimal("40.00"), cpa["current_value"])
        self.assertNotEqual(Decimal("61.11"), cpa["previous_value"])

    def test_change_and_change_rate(self) -> None:
        rows = week(self.previous_start, cost="100") + week(self.current_start, cost="150")

        cost = metric(compare_weeks(rows, self.current_start), "A", "cost")

        self.assertEqual(700, cost["previous_value"])
        self.assertEqual(1050, cost["current_value"])
        self.assertEqual(350, cost["change"])
        self.assertEqual(Decimal("0.500000"), cost["change_rate"])
        self.assertEqual("comparable", cost["comparison_status"])

    def test_previous_zero_keeps_change_but_excludes_rate(self) -> None:
        rows = week(self.previous_start, impressions="0") + week(
            self.current_start, impressions="10"
        )

        impressions = metric(compare_weeks(rows, self.current_start), "A", "impressions")

        self.assertEqual(70, impressions["change"])
        self.assertIsNone(impressions["change_rate"])
        self.assertEqual("previous_zero", impressions["comparison_status"])
        self.assertIn("증감률", impressions["exclusion_reason"])

    def test_new_and_current_not_run(self) -> None:
        rows = week(self.previous_start, campaign="old") + week(
            self.current_start, campaign="new"
        )

        comparisons = compare_weeks(rows, self.current_start)

        self.assertEqual("current_not_run", metric(comparisons, "old", "cost")["comparison_status"])
        self.assertEqual("new", metric(comparisons, "new", "cost")["comparison_status"])
        self.assertEqual(0, metric(comparisons, "new", "cost")["previous_days"])
        self.assertEqual(0, metric(comparisons, "old", "cost")["current_days"])

    def test_missing_value_is_not_replaced_with_zero(self) -> None:
        rows = week(self.previous_start, revenue="") + week(self.current_start, revenue="")

        revenue = metric(compare_weeks(rows, self.current_start), "A", "revenue")

        self.assertIsNone(revenue["previous_value"])
        self.assertIsNone(revenue["current_value"])
        self.assertEqual("excluded", revenue["comparison_status"])
        self.assertIn("필수 값 결측", revenue["exclusion_reason"])

    def test_definition_mismatch_excludes_only_affected_metrics(self) -> None:
        rows = week(
            self.previous_start,
            vat_basis="included",
            conversion_definition="purchase",
            revenue_definition="purchase_value",
        ) + week(
            self.current_start,
            vat_basis="excluded",
            conversion_definition="lead",
            revenue_definition="gross_sales",
        )

        comparisons = compare_weeks(rows, self.current_start)

        expected_excluded = {"cost", "conversions", "revenue", "cpa", "roas", "conversion_rate"}
        for name in METRICS:
            item = metric(comparisons, "A", name)
            expected = "excluded" if name in expected_excluded else "comparable"
            self.assertEqual(expected, item["comparison_status"], name)

    def test_incomplete_period_reports_actual_days_without_interpretation(self) -> None:
        rows = week(self.previous_start)[:3] + week(self.current_start)[:5]

        comparisons = compare_weeks(rows, self.current_start)
        cost = metric(comparisons, "A", "cost")

        self.assertEqual(3, cost["previous_days"])
        self.assertEqual(5, cost["current_days"])
        self.assertEqual("전주 기간 불완전: 3/7일 | 금주 기간 불완전: 5/7일", cost["period_warning"])
        self.assertEqual(set(OUTPUT_FIELDS), set(cost))
        self.assertNotIn("summary", cost)
        self.assertNotIn("performance_judgement", cost)

    def test_reference_date_uses_latest_elapsed_week(self) -> None:
        rows = week(self.previous_start) + week(self.current_start)

        sunday = resolve_current_week_start(rows, reference_date=date(2026, 7, 26))
        monday = resolve_current_week_start(rows, reference_date=date(2026, 7, 27))

        self.assertEqual(self.current_start, sunday)
        self.assertEqual(self.current_start, monday)

    def test_explicit_current_week_must_be_monday(self) -> None:
        with self.assertRaisesRegex(ValueError, "월요일"):
            resolve_current_week_start([], current_week_start=date(2026, 7, 21))

    def test_provided_data_acceptance(self) -> None:
        rows = read_normalized_input(ROOT / "output" / "normalized")

        current_start, comparisons = build_weekly_comparison(rows)

        self.assertEqual(date(2026, 7, 20), current_start)
        self.assertEqual(88, len(comparisons))
        self.assertTrue(all(item["previous_days"] == 7 for item in comparisons))
        self.assertTrue(all(item["current_days"] == 7 for item in comparisons))
        self.assertTrue(all(item["period_warning"] == "" for item in comparisons))
        self.assertEqual(set(OUTPUT_FIELDS), set(comparisons[0]))

        target_campaign = "NSA_여름 크루즈 프로모션"
        previous_rows = [
            item
            for item in rows
            if item["campaign"] == target_campaign
            and self.previous_start.isoformat() <= item["date"] <= "2026-07-19"
        ]
        expected_cost = sum(int(item["cost"]) for item in previous_rows)
        expected_conversions = sum(int(item["conversions"]) for item in previous_rows)
        expected_cpa = (Decimal(expected_cost) / Decimal(expected_conversions)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(expected_cost, metric(comparisons, target_campaign, "cost")["previous_value"])
        self.assertEqual(expected_cpa, metric(comparisons, target_campaign, "cpa")["previous_value"])


if __name__ == "__main__":
    unittest.main()
