from __future__ import annotations

import csv
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence

from src.outputs.google_sheets import (
    CHANNEL_SHEETS,
    DISPLAY_HEADER_LABELS,
    OUTPUT_FIELDS,
    WEEKLY_COMPARISON_FIELDS,
    build_display_values,
    build_format_requests,
    load_channel_payloads,
    load_weekly_comparison,
    upload_channel_payloads,
    upload_payloads,
)


def write_fixture_files(directory: Path) -> None:
    vat_basis_by_channel = {
        "ga4": "not_applicable",
        "meta": "unknown",
        "naver_search": "excluded",
        "naver_gfa": "included",
        "kakao_moment": "unknown",
    }
    for index, (channel, (filename, _)) in enumerate(CHANNEL_SHEETS.items(), start=1):
        row = {field: "" for field in OUTPUT_FIELDS}
        row.update(
            {
                "date": "2026-07-13",
                "channel": channel,
                "campaign": f"campaign-{index}",
                "cost": str(index * 100),
                "impressions": str(index * 1000),
                "clicks": str(index * 10),
                "conversions": str(index),
                "vat_basis": vat_basis_by_channel[channel],
                "source_file": f"source-{index}.csv",
                "source_row_number": "2",
                "source_file_hash": f"hash-{index}",
                "schema_version": "1.0",
                "adapter_version": "1.0",
            }
        )
        with (directory / filename).open(
            "w", encoding="utf-8-sig", newline=""
        ) as output_file:
            writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerow(row)


def write_weekly_fixture(path: Path) -> None:
    rows = [
        {
            "channel": "meta",
            "campaign": "campaign-1",
            "metric": "cpa",
            "previous_week_start": "2026-07-13",
            "previous_week_end": "2026-07-19",
            "current_week_start": "2026-07-20",
            "current_week_end": "2026-07-26",
            "previous_value": "10000",
            "current_value": "12000",
            "change": "2000",
            "change_rate": "0.2",
            "previous_days": "7",
            "current_days": "7",
            "comparison_status": "comparable",
            "exclusion_reason": "",
            "period_warning": "",
        },
        {
            "channel": "ga4",
            "campaign": "campaign-2",
            "metric": "cost",
            "previous_week_start": "2026-07-13",
            "previous_week_end": "2026-07-19",
            "current_week_start": "2026-07-20",
            "current_week_end": "2026-07-26",
            "previous_value": "",
            "current_value": "",
            "change": "",
            "change_rate": "",
            "previous_days": "7",
            "current_days": "7",
            "comparison_status": "excluded",
            "exclusion_reason": "비용 결측",
            "period_warning": "",
        },
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=WEEKLY_COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class FakeGateway:
    def __init__(
        self,
        *,
        corrupt_readback: bool = False,
        trim_trailing_blanks: bool = False,
        titles: set[str] | None = None,
    ) -> None:
        self.spreadsheet_id = "test-spreadsheet"
        self.titles = {"GA4"} if titles is None else set(titles)
        self.created: list[str] = []
        self.cleared: list[str] = []
        self.data: dict[str, list[list[Any]]] = {}
        self.corrupt_readback = corrupt_readback
        self.trim_trailing_blanks = trim_trailing_blanks
        self.formatted_channels: list[str] = []

    def list_sheet_titles(self) -> set[str]:
        return set(self.titles)

    def add_sheets(self, titles: Sequence[str]) -> None:
        self.created.extend(titles)
        self.titles.update(titles)

    def clear_ranges(self, ranges: Sequence[str]) -> None:
        self.cleared.extend(ranges)

    def write_ranges(self, data: dict[str, list[list[Any]]]) -> int:
        self.data = deepcopy(data)
        return sum(len(row) for values in data.values() for row in values)

    def read_ranges(self, ranges: Sequence[str]) -> dict[str, list[list[Any]]]:
        result = {
            data_range: deepcopy(self.data[data_range.split(":", maxsplit=1)[0]])
            for data_range in ranges
        }
        if self.corrupt_readback:
            first_range = next(iter(result))
            result[first_range][1][2] = "corrupted"
        if self.trim_trailing_blanks:
            for values in result.values():
                for row in values:
                    while row and row[-1] == "":
                        row.pop()
        return result

    def format_sheets(self, payloads: Sequence[Any]) -> None:
        self.formatted_channels.extend(payload.channel for payload in payloads)


class GoogleSheetsOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        write_fixture_files(self.directory)
        self.weekly_path = self.directory / "weekly_comparison.csv"
        write_weekly_fixture(self.weekly_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_all_channel_files_and_types_numbers(self) -> None:
        payloads = load_channel_payloads(self.directory)

        self.assertEqual(len(payloads), 5)
        self.assertEqual(sum(payload.data_rows for payload in payloads), 5)
        self.assertIsInstance(payloads[0].values[1][OUTPUT_FIELDS.index("cost")], int)
        self.assertEqual(payloads[0].values[1][OUTPUT_FIELDS.index("revenue")], "")

    def test_upload_creates_missing_tabs_and_verifies_readback(self) -> None:
        payloads = load_channel_payloads(self.directory)
        gateway = FakeGateway()

        report = upload_channel_payloads(gateway, payloads)

        self.assertEqual(report.channel_count, 5)
        self.assertEqual(report.data_rows, 5)
        self.assertEqual(len(report.created_sheets), 4)
        self.assertEqual(len(gateway.cleared), 5)
        self.assertEqual(len(gateway.formatted_channels), 5)
        self.assertEqual(report.updated_cells, 5 * 2 * len(OUTPUT_FIELDS))
        ga4_values = gateway.data["'GA4'!A1"]
        self.assertEqual(ga4_values[0], [DISPLAY_HEADER_LABELS[field] for field in OUTPUT_FIELDS])
        self.assertEqual(
            ga4_values[1][OUTPUT_FIELDS.index("channel")],
            "구글 애널리틱스 4(GA4)",
        )
        self.assertEqual(ga4_values[1][OUTPUT_FIELDS.index("vat_basis")], "해당 없음")

    def test_display_values_preserve_internal_schema_and_localize_codes(self) -> None:
        channel_payload = load_channel_payloads(self.directory)[0]
        channel_display = build_display_values(channel_payload)

        self.assertEqual(channel_payload.values[0], OUTPUT_FIELDS)
        self.assertEqual(
            channel_display[0],
            [DISPLAY_HEADER_LABELS[field] for field in OUTPUT_FIELDS],
        )
        self.assertEqual(
            channel_display[1][OUTPUT_FIELDS.index("channel")],
            "구글 애널리틱스 4(GA4)",
        )
        self.assertEqual(
            channel_display[1][OUTPUT_FIELDS.index("vat_basis")],
            "해당 없음",
        )

        weekly_payload = load_weekly_comparison(self.weekly_path)
        weekly_display = build_display_values(weekly_payload)
        self.assertEqual(weekly_payload.values[0], WEEKLY_COMPARISON_FIELDS)
        self.assertEqual(
            weekly_display[0],
            [DISPLAY_HEADER_LABELS[field] for field in WEEKLY_COMPARISON_FIELDS],
        )
        self.assertEqual(weekly_display[1][0], "메타")
        self.assertEqual(weekly_display[1][2], "전환당 비용(CPA)")
        self.assertEqual(weekly_display[1][13], "비교 가능")
        self.assertEqual(weekly_display[2][0], "구글 애널리틱스 4(GA4)")
        self.assertEqual(weekly_display[2][2], "비용")
        self.assertEqual(weekly_display[2][13], "비교 제외")

    def test_display_values_reject_unregistered_code(self) -> None:
        payload = load_weekly_comparison(self.weekly_path)
        payload.values[1][2] = "new_metric"

        with self.assertRaisesRegex(ValueError, "표시 코드 미등록"):
            build_display_values(payload)

    def test_format_requests_include_freeze_filter_widths_and_hidden_metadata(self) -> None:
        payload = load_channel_payloads(self.directory)[0]

        requests = build_format_requests(123, payload)

        self.assertTrue(any("updateSheetProperties" in request for request in requests))
        self.assertTrue(any("setBasicFilter" in request for request in requests))
        dimension_requests = [
            request["updateDimensionProperties"]
            for request in requests
            if "updateDimensionProperties" in request
        ]
        self.assertTrue(
            any(
                request["properties"].get("hiddenByUser") is True
                for request in dimension_requests
            )
        )

    def test_weekly_comparison_creates_tab_and_types_values(self) -> None:
        payload = load_weekly_comparison(self.weekly_path)
        gateway = FakeGateway(titles=set())

        report = upload_payloads(gateway, [payload])

        self.assertEqual(report.data_rows, 2)
        self.assertEqual(report.created_sheets, ("전주비교",))
        self.assertEqual(gateway.cleared, ["'전주비교'"])
        self.assertIsInstance(payload.values[1][7], int)
        self.assertIsInstance(payload.values[1][10], float)

    def test_weekly_comparison_updates_existing_tab_without_creation(self) -> None:
        payload = load_weekly_comparison(self.weekly_path)
        gateway = FakeGateway(
            titles={"전주비교"},
            trim_trailing_blanks=True,
        )

        report = upload_payloads(gateway, [payload])

        self.assertEqual(report.created_sheets, ())
        self.assertEqual(len(gateway.formatted_channels), 1)

    def test_weekly_comparison_rejects_readback_mismatch(self) -> None:
        payload = load_weekly_comparison(self.weekly_path)

        with self.assertRaisesRegex(RuntimeError, "업로드 후 값 검증 실패"):
            upload_payloads(
                FakeGateway(corrupt_readback=True, titles={"전주비교"}),
                [payload],
            )

    def test_rejects_missing_channel_file(self) -> None:
        (self.directory / "meta_normalized.csv").unlink()

        with self.assertRaisesRegex(ValueError, "정규화 CSV 없음"):
            load_channel_payloads(self.directory)

    def test_rejects_readback_mismatch(self) -> None:
        payloads = load_channel_payloads(self.directory)

        with self.assertRaisesRegex(RuntimeError, "업로드 후 값 검증 실패"):
            upload_channel_payloads(FakeGateway(corrupt_readback=True), payloads)


if __name__ == "__main__":
    unittest.main()
