from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from src.comparison.weekly_comparison import (
    build_weekly_comparison,
    write_comparison_csv,
)
from src.metrics.calculate_metrics import (
    DEFAULT_GROUP_BY,
    aggregate_metrics,
    write_metrics_csv,
)
from src.normalization.normalize_csvs import (
    CHANNEL_OUTPUT_FILENAMES,
    normalize_directory,
    write_channel_csvs,
)
from src.outputs.google_sheets import (
    GoogleSheetsGateway,
    SheetPayload,
    UploadReport,
    build_google_service,
    load_channel_payloads,
    load_weekly_comparison,
    upload_payloads,
)


REPOSITORY_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
DERIVED_METRICS_FILENAME = "derived_metrics.csv"
WEEKLY_COMPARISON_FILENAME = "weekly_comparison.csv"
SPREADSHEET_URL_PATTERN = re.compile(r"/spreadsheets/d/([^/]+)")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class PipelineConfig:
    repository_root: Path
    input_dir: Path
    normalized_output_dir: Path
    report_output_dir: Path
    log_dir: Path
    spreadsheet_id: str
    credentials_path: Path | None
    upload_enabled: bool
    dry_run: bool
    current_week_start: date | None = None
    reference_date: date | None = None


@dataclass(frozen=True)
class PipelineResult:
    normalized_rows: int
    metric_groups: int
    comparison_rows: int
    current_week_start: date
    validated_tabs: int
    upload_status: str
    uploaded_rows: int
    log_path: Path


UploadAction = Callable[[PipelineConfig, Sequence[SheetPayload]], UploadReport]


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"환경 설정 파일 없음: {path}")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path.name}:{line_number}: KEY=VALUE 형식 필요")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path.name}:{line_number}: 환경 변수 이름 결측")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"{key} 불리언 값 오류: {value!r}")


def _parse_optional_date(value: str, key: str) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{key} YYYY-MM-DD 형식 필요: {value!r}") from error


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _spreadsheet_id(value: str) -> str:
    stripped = value.strip()
    match = SPREADSHEET_URL_PATTERN.search(stripped)
    return match.group(1) if match else stripped


def load_config(
    env_path: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    environ: Mapping[str, str] | None = None,
) -> PipelineConfig:
    root = repository_root.resolve()
    values = read_env_file(env_path)
    external = os.environ if environ is None else environ
    for key in (
        "DATA_INPUT_DIR",
        "NORMALIZED_OUTPUT_DIR",
        "REPORT_OUTPUT_DIR",
        "LOG_DIR",
        "GOOGLE_SHEETS_SPREADSHEET_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "UPLOAD_ENABLED",
        "DRY_RUN",
        "CURRENT_WEEK_START",
        "REFERENCE_DATE",
    ):
        if key in external:
            values[key] = external[key]

    def required(key: str) -> str:
        value = values.get(key, "").strip()
        if not value:
            raise ValueError(f"환경 설정 결측: {key}")
        return value

    credentials_value = values.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    current_week_start = _parse_optional_date(
        values.get("CURRENT_WEEK_START", ""), "CURRENT_WEEK_START"
    )
    reference_date = _parse_optional_date(
        values.get("REFERENCE_DATE", ""), "REFERENCE_DATE"
    )
    if current_week_start and reference_date:
        raise ValueError("CURRENT_WEEK_START와 REFERENCE_DATE 동시 설정 금지")

    return PipelineConfig(
        repository_root=root,
        input_dir=_resolve_path(root, required("DATA_INPUT_DIR")),
        normalized_output_dir=_resolve_path(root, required("NORMALIZED_OUTPUT_DIR")),
        report_output_dir=_resolve_path(root, required("REPORT_OUTPUT_DIR")),
        log_dir=_resolve_path(root, required("LOG_DIR")),
        spreadsheet_id=_spreadsheet_id(values.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")),
        credentials_path=(
            _resolve_path(root, credentials_value) if credentials_value else None
        ),
        upload_enabled=_parse_bool(values.get("UPLOAD_ENABLED", "true"), "UPLOAD_ENABLED"),
        dry_run=_parse_bool(values.get("DRY_RUN", "false"), "DRY_RUN"),
        current_week_start=current_week_start,
        reference_date=reference_date,
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_config(config: PipelineConfig) -> None:
    if not config.input_dir.is_dir():
        raise ValueError(f"입력 디렉터리 없음: {config.input_dir}")
    if _is_within(config.normalized_output_dir, config.input_dir):
        raise ValueError("정규화 출력 경로는 입력 디렉터리 내부 사용 금지")
    if _is_within(config.report_output_dir, config.input_dir):
        raise ValueError("보고서 출력 경로는 입력 디렉터리 내부 사용 금지")
    if config.current_week_start and config.current_week_start.weekday() != 0:
        raise ValueError("CURRENT_WEEK_START는 월요일 필요")
    if config.upload_enabled and not config.dry_run:
        if not config.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID 결측")
        if config.credentials_path is None or not config.credentials_path.is_file():
            raise ValueError(f"서비스 계정 JSON 없음: {config.credentials_path}")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.pipeline.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _publish_outputs(
    staging_normalized: Path,
    staging_reports: Path,
    config: PipelineConfig,
) -> None:
    for filename in CHANNEL_OUTPUT_FILENAMES.values():
        _atomic_copy(staging_normalized / filename, config.normalized_output_dir / filename)
    for filename in (DERIVED_METRICS_FILENAME, WEEKLY_COMPARISON_FILENAME):
        _atomic_copy(staging_reports / filename, config.report_output_dir / filename)


def _default_upload(
    config: PipelineConfig, payloads: Sequence[SheetPayload]
) -> UploadReport:
    if config.credentials_path is None:
        raise ValueError("서비스 계정 JSON 경로 결측")
    service = build_google_service(config.credentials_path)
    return upload_payloads(
        GoogleSheetsGateway(service, config.spreadsheet_id),
        payloads,
    )


def _write_log(config: PipelineConfig, started_at: datetime, lines: Sequence[str]) -> Path:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d_%H%M%S_%f")
    path = config.log_dir / f"pipeline_{stamp}.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_pipeline(
    config: PipelineConfig,
    *,
    upload_action: UploadAction | None = None,
) -> PipelineResult:
    started_at = datetime.now().astimezone()
    log_lines = [
        f"started_at={started_at.isoformat()}",
        f"input_dir={config.input_dir}",
        f"normalized_output_dir={config.normalized_output_dir}",
        f"report_output_dir={config.report_output_dir}",
    ]
    try:
        validate_config(config)
        with tempfile.TemporaryDirectory(prefix="sangsaeng-pipeline-") as temporary:
            staging_root = Path(temporary)
            staging_normalized = staging_root / "normalized"
            staging_reports = staging_root / "reports"

            rows = normalize_directory(config.input_dir)
            channels = {row["channel"] for row in rows}
            expected_channels = set(CHANNEL_OUTPUT_FILENAMES)
            if channels != expected_channels:
                missing = sorted(expected_channels - channels)
                unexpected = sorted(channels - expected_channels)
                details = []
                if missing:
                    details.append(f"누락={','.join(missing)}")
                if unexpected:
                    details.append(f"미지원={','.join(unexpected)}")
                raise ValueError(f"채널 구성 불일치: {'; '.join(details)}")

            normalized_paths = write_channel_csvs(rows, staging_normalized)
            if set(normalized_paths) != expected_channels:
                raise ValueError("채널별 정규화 파일 생성 불완전")

            metrics = aggregate_metrics(rows, DEFAULT_GROUP_BY)
            derived_path = staging_reports / DERIVED_METRICS_FILENAME
            write_metrics_csv(metrics, derived_path, DEFAULT_GROUP_BY)

            current_week_start, comparisons = build_weekly_comparison(
                rows,
                current_week_start=config.current_week_start,
                reference_date=config.reference_date,
            )
            comparison_path = staging_reports / WEEKLY_COMPARISON_FILENAME
            write_comparison_csv(comparisons, comparison_path)

            payloads = load_channel_payloads(staging_normalized)
            payloads.append(load_weekly_comparison(comparison_path))
            _publish_outputs(staging_normalized, staging_reports, config)

            upload_status = "disabled"
            uploaded_rows = 0
            if config.upload_enabled and config.dry_run:
                upload_status = "dry-run"
            elif config.upload_enabled:
                report = (upload_action or _default_upload)(config, payloads)
                upload_status = "uploaded"
                uploaded_rows = report.data_rows

        completed_at = datetime.now().astimezone()
        log_lines.extend(
            [
                "status=success",
                f"completed_at={completed_at.isoformat()}",
                f"normalized_rows={len(rows)}",
                f"metric_groups={len(metrics)}",
                f"comparison_rows={len(comparisons)}",
                f"current_week_start={current_week_start.isoformat()}",
                f"validated_tabs={len(payloads)}",
                f"upload_status={upload_status}",
                f"uploaded_rows={uploaded_rows}",
            ]
        )
        log_path = _write_log(config, started_at, log_lines)
        return PipelineResult(
            normalized_rows=len(rows),
            metric_groups=len(metrics),
            comparison_rows=len(comparisons),
            current_week_start=current_week_start,
            validated_tabs=len(payloads),
            upload_status=upload_status,
            uploaded_rows=uploaded_rows,
            log_path=log_path,
        )
    except Exception as error:
        failed_at = datetime.now().astimezone()
        log_lines.extend(
            [
                "status=failed",
                f"failed_at={failed_at.isoformat()}",
                f"error_type={type(error).__name__}",
                f"error={error}",
            ]
        )
        try:
            _write_log(config, started_at, log_lines)
        except OSError:
            pass
        raise


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("YYYY-MM-DD 형식 필요") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P2 정규화, P3 파생 지표, P4 전주 비교, 구글시트 업로드 통합 실행"
    )
    parser.add_argument("--env-file", type=Path, default=REPOSITORY_ROOT / ".env")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--normalized-output-dir", type=Path)
    parser.add_argument("--report-output-dir", type=Path)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--spreadsheet-id")
    parser.add_argument("--credentials", type=Path)
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--current-week-start", type=_date_argument)
    period.add_argument("--reference-date", type=_date_argument)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    return parser


def _resolved_override(root: Path, value: Path | None) -> Path | None:
    if value is None:
        return None
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def config_from_args(args: argparse.Namespace) -> PipelineConfig:
    env_path = (
        args.env_file.resolve()
        if args.env_file.is_absolute()
        else (REPOSITORY_ROOT / args.env_file).resolve()
    )
    config = load_config(env_path)
    root = config.repository_root
    return replace(
        config,
        input_dir=_resolved_override(root, args.input_dir) or config.input_dir,
        normalized_output_dir=(
            _resolved_override(root, args.normalized_output_dir)
            or config.normalized_output_dir
        ),
        report_output_dir=(
            _resolved_override(root, args.report_output_dir) or config.report_output_dir
        ),
        log_dir=_resolved_override(root, args.log_dir) or config.log_dir,
        spreadsheet_id=(
            _spreadsheet_id(args.spreadsheet_id)
            if args.spreadsheet_id is not None
            else config.spreadsheet_id
        ),
        credentials_path=(
            _resolved_override(root, args.credentials)
            if args.credentials is not None
            else config.credentials_path
        ),
        upload_enabled=False if args.no_upload else config.upload_enabled,
        dry_run=True if args.dry_run else config.dry_run,
        current_week_start=(
            args.current_week_start
            if args.current_week_start is not None
            else (None if args.reference_date is not None else config.current_week_start)
        ),
        reference_date=(
            args.reference_date
            if args.reference_date is not None
            else (None if args.current_week_start is not None else config.reference_date)
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(config_from_args(args))
    except Exception as error:
        print(f"pipeline_status=failed", file=sys.stderr)
        print(f"error={error}", file=sys.stderr)
        return 1

    print("pipeline_status=success")
    print(f"normalized_rows={result.normalized_rows}")
    print(f"metric_groups={result.metric_groups}")
    print(f"comparison_rows={result.comparison_rows}")
    print(f"current_week_start={result.current_week_start}")
    print(f"validated_tabs={result.validated_tabs}")
    print(f"upload_status={result.upload_status}")
    print(f"uploaded_rows={result.uploaded_rows}")
    print(f"log={result.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
