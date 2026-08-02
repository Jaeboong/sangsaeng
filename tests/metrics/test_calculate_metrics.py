from __future__ import annotations

import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.metrics.calculate_metrics import (
    NORMALIZED_FIELDS,
    aggregate_metrics,
    read_normalized_input,
)


def row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "channel": "test",
        "campaign": "campaign",
        "cost": "100",
        "impressions": "1000",
        "clicks": "20",
        "conversions": "4",
        "revenue": "400",
        "vat_basis": "included",
        "conversion_definition": "구매",
        "revenue_definition": "구매매출",
    }
    base.update(overrides)
    return base


def write_normalized_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        for source in rows:
            writer.writerow({field: source.get(field, "") for field in NORMALIZED_FIELDS})


class AggregateMetricsTest(unittest.TestCase):
    def test_calculates_ratio_after_summing_raw_metrics(self) -> None:
        result = aggregate_metrics(
            [
                row(cost="100", conversions="1", clicks="10", revenue="200"),
                row(cost="300", conversions="3", clicks="30", revenue="1200"),
            ]
        )[0]

        self.assertEqual(result["cpa"], Decimal("100.00"))
        self.assertEqual(result["roas"], Decimal("3.500000"))
        self.assertEqual(result["roas_percent"], Decimal("350.0000"))
        self.assertEqual(result["conversion_rate"], Decimal("0.100000"))
        self.assertEqual(result["conversion_rate_percent"], Decimal("10.0000"))
        self.assertNotEqual(result["roas"], Decimal("3"))  # 행별 ROAS 평균

    def test_reports_zero_denominators(self) -> None:
        result = aggregate_metrics([row(cost="0", clicks="0", conversions="0")])[0]

        self.assertIsNone(result["cpa"])
        self.assertIn("분모 0: conversions", result["cpa_reason"])
        self.assertIsNone(result["roas"])
        self.assertIn("분모 0: cost", result["roas_reason"])
        self.assertIsNone(result["conversion_rate"])
        self.assertIn("분모 0: clicks", result["conversion_rate_reason"])

    def test_reports_each_required_missing_value(self) -> None:
        result = aggregate_metrics(
            [row(cost="", revenue="", clicks="", conversions="")]
        )[0]

        self.assertIn("cost", result["cpa_reason"])
        self.assertIn("conversions", result["cpa_reason"])
        self.assertIn("revenue", result["roas_reason"])
        self.assertIn("cost", result["roas_reason"])
        self.assertIn("clicks", result["conversion_rate_reason"])
        self.assertIn("conversions", result["conversion_rate_reason"])
        self.assertIsNone(result["cost_sum"])

    def test_partial_missing_value_does_not_become_partial_sum(self) -> None:
        result = aggregate_metrics([row(cost="100"), row(cost="")])[0]

        self.assertIsNone(result["cost_sum"])
        self.assertEqual(result["cost_missing_count"], 1)
        self.assertIsNone(result["cpa"])

    def test_mixed_vat_basis_excludes_group_metrics(self) -> None:
        result = aggregate_metrics(
            [row(vat_basis="included"), row(vat_basis="excluded")]
        )[0]

        for metric in ("cpa", "roas", "conversion_rate"):
            self.assertIsNone(result[metric])
            self.assertIn("VAT 기준 혼합", result[f"{metric}_reason"])

    def test_mixed_conversion_definition_excludes_group_metrics(self) -> None:
        result = aggregate_metrics(
            [row(conversion_definition="구매"), row(conversion_definition="회원가입")]
        )[0]

        for metric in ("cpa", "roas", "conversion_rate"):
            self.assertIsNone(result[metric])
            self.assertIn("전환 정의 혼합", result[f"{metric}_reason"])

    def test_custom_grouping_is_reusable_for_weekly_comparison(self) -> None:
        rows = [
            row(date="2026-07-13", campaign="a"),
            row(date="2026-07-13", campaign="b"),
        ]
        result = aggregate_metrics(rows, group_by=("date", "channel"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date"], "2026-07-13")
        self.assertEqual(result[0]["row_count"], 2)

    def test_rejects_invalid_normalized_integers_as_value_error(self) -> None:
        invalid_values: tuple[object, ...] = (
            "12.5",
            "Infinity",
            "NaN",
            "sNaN",
            "1e400",
            "1,2,3",
            "1_000",
            "-1",
            "9" * 5000,
            -1,
            1.0,
            True,
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "cost"):
                    aggregate_metrics([row(cost=value)])

    def test_reports_source_file_and_row_for_invalid_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "input.csv:17 cost"):
            aggregate_metrics(
                [row(cost="oops", source_file="input.csv", source_row_number="17")]
            )

    def test_rejects_missing_empty_and_non_string_group_values(self) -> None:
        for value in (None, "", "   ", 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "그룹 필드 값 오류: campaign"):
                    aggregate_metrics([row(campaign=value)])

    def test_rejects_invalid_group_by_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "그룹 기준은 한 개 이상 필요"):
            aggregate_metrics([row()], group_by=())
        with self.assertRaisesRegex(ValueError, "그룹 기준 중복"):
            aggregate_metrics([row()], group_by=("channel", "channel"))
        for invalid_group_by in (("",), (1,)):
            with self.subTest(group_by=invalid_group_by):
                with self.assertRaisesRegex(ValueError, "비어 있지 않은 문자열"):
                    aggregate_metrics([row()], group_by=invalid_group_by)
        with self.assertRaisesRegex(ValueError, "그룹 필드 누락: week"):
            aggregate_metrics([row()], group_by=("week",))

    def test_missing_semantic_definitions_exclude_affected_metrics(self) -> None:
        vat_result = aggregate_metrics([row(vat_basis="")])[0]
        conversion_result = aggregate_metrics([row(conversion_definition="")])[0]
        revenue_result = aggregate_metrics([row(revenue_definition="")])[0]

        for metric in ("cpa", "roas", "conversion_rate"):
            self.assertIsNone(vat_result[metric])
            self.assertIn("VAT 기준 결측", vat_result[f"{metric}_reason"])
            self.assertIsNone(conversion_result[metric])
            self.assertIn("전환 정의 결측", conversion_result[f"{metric}_reason"])
        self.assertIsNotNone(revenue_result["cpa"])
        self.assertIsNone(revenue_result["roas"])
        self.assertIn("매출 정의 결측", revenue_result["roas_reason"])
        self.assertIsNotNone(revenue_result["conversion_rate"])

    def test_mixed_revenue_definition_excludes_only_roas(self) -> None:
        result = aggregate_metrics(
            [row(revenue_definition="구매매출"), row(revenue_definition="총수익")]
        )[0]

        self.assertIsNotNone(result["cpa"])
        self.assertIsNone(result["roas"])
        self.assertIn("매출 정의 혼합", result["roas_reason"])
        self.assertIsNotNone(result["conversion_rate"])


class ProvidedDataAcceptanceTest(unittest.TestCase):
    def test_distinguishes_calculable_channels_in_provided_output(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        normalized_path = project_root / "output" / "normalized"
        rows = read_normalized_input(normalized_path)

        results = aggregate_metrics(rows, group_by=("channel",))
        by_channel = {result["channel"]: result for result in results}

        self.assertEqual(len(rows), 154)
        self.assertEqual(set(by_channel), {"ga4", "meta", "naver_gfa", "naver_search", "kakao_moment"})
        self.assertIsNone(by_channel["ga4"]["cpa"])
        self.assertIsNone(by_channel["ga4"]["roas"])
        self.assertIsNone(by_channel["ga4"]["conversion_rate"])
        for channel in ("meta", "naver_gfa"):
            self.assertIsNotNone(by_channel[channel]["cpa"])
            self.assertIsNone(by_channel[channel]["roas"])
            self.assertIsNotNone(by_channel[channel]["conversion_rate"])
        for channel in ("naver_search", "kakao_moment"):
            self.assertIsNotNone(by_channel[channel]["cpa"])
            self.assertIsNotNone(by_channel[channel]["roas"])
            self.assertIsNotNone(by_channel[channel]["conversion_rate"])

        self.assertEqual(by_channel["meta"]["cost_sum"], 9510000)
        self.assertEqual(by_channel["meta"]["cpa"], Decimal("9885.65"))
        self.assertEqual(by_channel["naver_search"]["revenue_sum"], 196160000)
        self.assertEqual(
            by_channel["naver_search"]["roas"], Decimal("56.504206")
        )

        default_results = aggregate_metrics(rows)
        self.assertEqual(len(default_results), 11)
        self.assertEqual(
            {
                metric: sum(result[metric] is not None for result in default_results)
                for metric in ("cpa", "roas", "conversion_rate")
            },
            {"cpa": 8, "roas": 3, "conversion_rate": 8},
        )

    def test_preserves_single_csv_input_compatibility(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        input_path = project_root / "output" / "normalized" / "ga4_normalized.csv"

        rows = read_normalized_input(input_path)

        self.assertEqual(len(rows), 42)
        self.assertEqual({row["channel"] for row in rows}, {"ga4"})

    def test_rejects_a_channel_file_with_a_different_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "wrong_normalized.csv"
            with input_path.open("w", encoding="utf-8", newline="") as output_file:
                writer = csv.writer(output_file)
                writer.writerow(["channel", "campaign"])
                writer.writerow(["test", "campaign"])

            with self.assertRaisesRegex(ValueError, "공통 스키마 불일치"):
                read_normalized_input(Path(temporary_directory))

    def test_rejects_missing_path_and_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            with self.assertRaisesRegex(ValueError, "정규화 입력 경로 없음"):
                read_normalized_input(directory / "missing")
            with self.assertRaisesRegex(ValueError, "채널별 정규화 CSV 없음"):
                read_normalized_input(directory)

    def test_rejects_csv_with_unexpected_directory_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_normalized_csv(directory / "kakao.csv", [row()])

            with self.assertRaisesRegex(ValueError, "정규화 파일명 규칙 불일치"):
                read_normalized_input(directory)

    def test_directory_merge_order_is_filename_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            write_normalized_csv(
                directory / "b_normalized.csv", [row(campaign="from-b")]
            )
            write_normalized_csv(
                directory / "a_normalized.csv", [row(campaign="from-a")]
            )

            rows = read_normalized_input(directory)

            self.assertEqual(
                [source["campaign"] for source in rows], ["from-a", "from-b"]
            )


if __name__ == "__main__":
    unittest.main()
