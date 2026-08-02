from __future__ import annotations

import csv
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from src.normalization.normalize_csvs import ADAPTERS
from src.outputs.google_sheets import UploadReport
from src.pipeline import PipelineConfig, load_config, run_pipeline


DATE_FORMATS = {
    "ga4": "%Y%m%d",
    "meta": "%Y-%m-%d",
    "naver_search": "%Y.%m.%d.",
    "naver_gfa": "%m/%d/%Y",
    "kakao_moment": "%Y%m%d",
}


def write_raw_fixtures(directory: Path, *, omitted_channel: str | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for adapter in ADAPTERS:
        if adapter.channel == omitted_channel:
            continue
        headers = list(adapter.signature)
        required_columns = [
            adapter.date_column,
            adapter.campaign_column,
            *[column for column in adapter.metric_columns.values() if column],
            *adapter.source_dimension_columns,
        ]
        if adapter.conversion_definition_column:
            required_columns.append(adapter.conversion_definition_column)
        for column in required_columns:
            if column not in headers:
                headers.append(column)

        rows = []
        for offset in range(14):
            raw_date = (date(2026, 7, 13) + timedelta(days=offset)).strftime(
                DATE_FORMATS[adapter.channel]
            )
            row = {header: "기준값" for header in headers}
            row[adapter.date_column] = raw_date
            row[adapter.campaign_column] = f"{adapter.channel}-campaign"
            for field, source_column in adapter.metric_columns.items():
                if source_column:
                    row[source_column] = {
                        "cost": "1000",
                        "impressions": "100",
                        "clicks": "10",
                        "conversions": "2",
                        "revenue": "5000",
                    }[field]
            if adapter.conversion_definition_column:
                row[adapter.conversion_definition_column] = "구매"
            rows.append(row)

        path = directory / f"{adapter.channel}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)


def make_config(root: Path, *, upload_enabled: bool, dry_run: bool) -> PipelineConfig:
    credentials = root / "secret" / "service-account.json"
    credentials.parent.mkdir(parents=True, exist_ok=True)
    credentials.write_text("{}", encoding="utf-8")
    return PipelineConfig(
        repository_root=root,
        input_dir=root / "input",
        normalized_output_dir=root / "output" / "normalized",
        report_output_dir=root / "output" / "reports",
        log_dir=root / "output" / "logs",
        spreadsheet_id="test-spreadsheet",
        credentials_path=credentials,
        upload_enabled=upload_enabled,
        dry_run=dry_run,
    )


class PipelineTest(unittest.TestCase):
    def test_load_config_resolves_paths_and_spreadsheet_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_path = root / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DATA_INPUT_DIR=data/input",
                        "NORMALIZED_OUTPUT_DIR=output/normalized",
                        "REPORT_OUTPUT_DIR=output/reports",
                        "LOG_DIR=output/logs",
                        "GOOGLE_SHEETS_SPREADSHEET_ID=https://docs.google.com/spreadsheets/d/test-id/edit",
                        "GOOGLE_APPLICATION_CREDENTIALS=secret/account.json",
                        "UPLOAD_ENABLED=true",
                        "DRY_RUN=false",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(env_path, repository_root=root, environ={})

            self.assertEqual(config.input_dir, root / "data" / "input")
            self.assertEqual(config.spreadsheet_id, "test-id")
            self.assertEqual(config.credentials_path, root / "secret" / "account.json")
            self.assertTrue(config.upload_enabled)
            self.assertFalse(config.dry_run)

    def test_pipeline_generates_all_outputs_without_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_config(root, upload_enabled=False, dry_run=False)
            write_raw_fixtures(config.input_dir)

            result = run_pipeline(config)

            self.assertEqual(result.normalized_rows, 70)
            self.assertEqual(result.metric_groups, 5)
            self.assertEqual(result.comparison_rows, 40)
            self.assertEqual(result.current_week_start, date(2026, 7, 20))
            self.assertEqual(result.validated_tabs, 6)
            self.assertEqual(result.upload_status, "disabled")
            self.assertTrue(result.log_path.is_file())
            self.assertEqual(len(list(config.normalized_output_dir.glob("*.csv"))), 5)
            self.assertTrue((config.report_output_dir / "derived_metrics.csv").is_file())
            self.assertTrue((config.report_output_dir / "weekly_comparison.csv").is_file())

    def test_dry_run_validates_payloads_without_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_config(root, upload_enabled=True, dry_run=True)
            write_raw_fixtures(config.input_dir)
            called = False

            def forbidden_upload(*_args: object) -> UploadReport:
                nonlocal called
                called = True
                raise AssertionError("dry-run에서 업로드 호출 금지")

            result = run_pipeline(config, upload_action=forbidden_upload)

            self.assertFalse(called)
            self.assertEqual(result.upload_status, "dry-run")

    def test_missing_channel_stops_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_config(root, upload_enabled=True, dry_run=False)
            write_raw_fixtures(config.input_dir, omitted_channel="ga4")
            called = False

            def forbidden_upload(*_args: object) -> UploadReport:
                nonlocal called
                called = True
                raise AssertionError("검증 실패 후 업로드 호출 금지")

            with self.assertRaisesRegex(ValueError, "채널 구성 불일치"):
                run_pipeline(config, upload_action=forbidden_upload)
            self.assertFalse(called)

    def test_success_upload_runs_after_local_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_config(root, upload_enabled=True, dry_run=False)
            write_raw_fixtures(config.input_dir)

            def fake_upload(
                received: PipelineConfig, payloads: object
            ) -> UploadReport:
                self.assertTrue(
                    (received.report_output_dir / "weekly_comparison.csv").is_file()
                )
                self.assertEqual(len(payloads), 6)  # type: ignore[arg-type]
                return UploadReport(
                    spreadsheet_id=received.spreadsheet_id,
                    channel_count=6,
                    data_rows=50,
                    updated_cells=100,
                    created_sheets=(),
                )

            result = run_pipeline(config, upload_action=fake_upload)

            self.assertEqual(result.upload_status, "uploaded")
            self.assertEqual(result.uploaded_rows, 50)


if __name__ == "__main__":
    unittest.main()
