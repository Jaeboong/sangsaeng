from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_GROUP_BY = ("channel", "campaign")
NORMALIZED_FIELDS = (
    "date",
    "channel",
    "campaign",
    "cost",
    "impressions",
    "clicks",
    "conversions",
    "revenue",
    "vat_basis",
    "conversion_definition",
    "revenue_definition",
    "source_dimensions",
    "source_file",
    "source_row_number",
    "source_file_hash",
    "schema_version",
    "adapter_version",
)
NUMERIC_FIELDS = ("cost", "impressions", "clicks", "conversions", "revenue")
RESULT_FIELDS = (
    "row_count",
    "cost_sum",
    "cost_missing_count",
    "impressions_sum",
    "impressions_missing_count",
    "clicks_sum",
    "clicks_missing_count",
    "conversions_sum",
    "conversions_missing_count",
    "revenue_sum",
    "revenue_missing_count",
    "vat_basis_values",
    "conversion_definition_values",
    "revenue_definition_values",
    "cpa",
    "cpa_reason",
    "roas",
    "roas_percent",
    "roas_reason",
    "conversion_rate",
    "conversion_rate_percent",
    "conversion_rate_reason",
)

CPA_SCALE = Decimal("0.01")
RATIO_SCALE = Decimal("0.000001")
PERCENT_SCALE = Decimal("0.0001")
NORMALIZED_INTEGER_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def read_normalized_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if tuple(reader.fieldnames or ()) != NORMALIZED_FIELDS:
            raise ValueError(f"공통 스키마 불일치: {path}")
        return list(reader)


def read_normalized_input(path: Path) -> list[dict[str, str]]:
    """단일 정규화 CSV 또는 채널별 정규화 CSV 디렉터리를 읽는다."""

    if path.is_file():
        return read_normalized_csv(path)
    if not path.is_dir():
        raise ValueError(f"정규화 입력 경로 없음: {path}")

    csv_paths = sorted(path.glob("*.csv"), key=lambda item: item.name)
    input_paths = [item for item in csv_paths if item.name.endswith("_normalized.csv")]
    unexpected_paths = [item.name for item in csv_paths if item not in input_paths]
    if unexpected_paths:
        raise ValueError(
            f"정규화 파일명 규칙 불일치: {', '.join(unexpected_paths)}"
        )
    if not input_paths:
        raise ValueError(f"채널별 정규화 CSV 없음: {path}")
    return [row for input_path in input_paths for row in read_normalized_csv(input_path)]


def _row_location(row: Mapping[str, object], fallback_row_number: int) -> str:
    source_file = str(row.get("source_file") or "").strip()
    source_row_number = str(row.get("source_row_number") or "").strip()
    if source_file and source_row_number:
        return f"{source_file}:{source_row_number}"
    if source_file:
        return source_file
    return f"{fallback_row_number}행"


def _parse_nonnegative_integer(value: object, field: str, location: str) -> int | None:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{location} {field}: 정수 아님 {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{location} {field}: 음수 {value!r}")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{location} {field}: 정수 아님 {value!r}")

    text = value.strip()
    if not NORMALIZED_INTEGER_PATTERN.fullmatch(text):
        raise ValueError(f"{location} {field}: 정수 파싱 실패 {value!r}")
    try:
        return int(text)
    except ValueError as error:
        raise ValueError(f"{location} {field}: 정수 파싱 실패 {value!r}") from error


def _complete_sum(values: Sequence[int | None]) -> int | None:
    return None if any(value is None for value in values) else sum(value for value in values if value is not None)


def _distinct_text(rows: Sequence[Mapping[str, object]], field: str) -> list[str]:
    values: set[str] = set()
    for row in rows:
        raw = row.get(field)
        if raw is not None and str(raw).strip():
            values.add(str(raw).strip())
    return sorted(values)


def _is_missing_text(value: object) -> bool:
    return value is None or not isinstance(value, str) or not value.strip()


def _join_reasons(reasons: Iterable[str]) -> str:
    return " | ".join(dict.fromkeys(reason for reason in reasons if reason))


def _ratio(numerator: int, denominator: int) -> Decimal:
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        RATIO_SCALE, rounding=ROUND_HALF_UP
    )


def _percent(ratio: Decimal) -> Decimal:
    return (ratio * 100).quantize(PERCENT_SCALE, rounding=ROUND_HALF_UP)


def _metric_missing_reason(field: str, count: int) -> str:
    return f"필수 값 결측: {field} {count}행"


def aggregate_metrics(
    rows: Iterable[Mapping[str, object]],
    group_by: Sequence[str] = DEFAULT_GROUP_BY,
) -> list[dict[str, object]]:
    """원천 지표를 그룹별로 합산한 뒤 CPA·ROAS·전환율을 계산한다.

    하나라도 결측인 원천 지표는 부분 합계로 대체하지 않는다. VAT 기준 또는
    전환 정의가 그룹 안에서 섞이면 해당 그룹의 모든 파생 지표를 제외한다.
    """

    group_fields = tuple(group_by)
    if not group_fields:
        raise ValueError("그룹 기준은 한 개 이상 필요")
    if any(not isinstance(field, str) or not field.strip() for field in group_fields):
        raise ValueError("그룹 기준은 비어 있지 않은 문자열만 허용")
    if len(group_fields) != len(set(group_fields)):
        raise ValueError("그룹 기준 중복")

    materialized = list(rows)
    prepared_rows: list[
        tuple[Mapping[str, object], tuple[str, ...], dict[str, int | None]]
    ] = []
    for row_number, row in enumerate(materialized, start=2):
        location = _row_location(row, row_number)
        missing_group_fields = [field for field in group_fields if field not in row]
        if missing_group_fields:
            raise ValueError(
                f"{location} 그룹 필드 누락: {', '.join(missing_group_fields)}"
            )
        invalid_group_fields = [
            field
            for field in group_fields
            if not isinstance(row[field], str) or not row[field].strip()
        ]
        if invalid_group_fields:
            raise ValueError(
                f"{location} 그룹 필드 값 오류: {', '.join(invalid_group_fields)}"
            )
        key = tuple(row[field] for field in group_fields)
        parsed_metrics = {
            field: _parse_nonnegative_integer(row.get(field), field, location)
            for field in NUMERIC_FIELDS
        }
        prepared_rows.append((row, key, parsed_metrics))

    groups: dict[
        tuple[str, ...],
        list[tuple[Mapping[str, object], dict[str, int | None]]],
    ] = defaultdict(list)
    for row, key, parsed_metrics in prepared_rows:
        groups[key].append((row, parsed_metrics))

    results: list[dict[str, object]] = []
    for key in sorted(groups):
        group_items = groups[key]
        group_rows = [row for row, _ in group_items]
        parsed: dict[str, list[int | None]] = {
            field: [parsed_metrics[field] for _, parsed_metrics in group_items]
            for field in NUMERIC_FIELDS
        }
        totals = {field: _complete_sum(values) for field, values in parsed.items()}
        missing_counts = {
            field: sum(value is None for value in values) for field, values in parsed.items()
        }

        vat_values = _distinct_text(group_rows, "vat_basis")
        conversion_values = _distinct_text(group_rows, "conversion_definition")
        revenue_values = _distinct_text(group_rows, "revenue_definition")

        semantic_reasons: list[str] = []
        vat_missing_count = sum(
            _is_missing_text(row.get("vat_basis")) for row in group_rows
        )
        conversion_definition_missing_count = sum(
            parsed["conversions"][index] is not None
            and _is_missing_text(row.get("conversion_definition"))
            for index, row in enumerate(group_rows)
        )
        revenue_definition_missing_count = sum(
            parsed["revenue"][index] is not None
            and _is_missing_text(row.get("revenue_definition"))
            for index, row in enumerate(group_rows)
        )
        if vat_missing_count:
            semantic_reasons.append(f"VAT 기준 결측: {vat_missing_count}행")
        if len(vat_values) > 1:
            semantic_reasons.append(f"VAT 기준 혼합: {', '.join(vat_values)}")
        if conversion_definition_missing_count:
            semantic_reasons.append(
                f"전환 정의 결측: {conversion_definition_missing_count}행"
            )
        if len(conversion_values) > 1:
            semantic_reasons.append(f"전환 정의 혼합: {', '.join(conversion_values)}")

        cpa_reasons = list(semantic_reasons)
        for field in ("cost", "conversions"):
            if missing_counts[field]:
                cpa_reasons.append(_metric_missing_reason(field, missing_counts[field]))
        if totals["conversions"] == 0:
            cpa_reasons.append("분모 0: conversions")

        roas_reasons = list(semantic_reasons)
        for field in ("revenue", "cost"):
            if missing_counts[field]:
                roas_reasons.append(_metric_missing_reason(field, missing_counts[field]))
        if totals["cost"] == 0:
            roas_reasons.append("분모 0: cost")
        if len(revenue_values) > 1:
            roas_reasons.append(f"매출 정의 혼합: {', '.join(revenue_values)}")
        if revenue_definition_missing_count:
            roas_reasons.append(f"매출 정의 결측: {revenue_definition_missing_count}행")

        conversion_rate_reasons = list(semantic_reasons)
        for field in ("conversions", "clicks"):
            if missing_counts[field]:
                conversion_rate_reasons.append(
                    _metric_missing_reason(field, missing_counts[field])
                )
        if totals["clicks"] == 0:
            conversion_rate_reasons.append("분모 0: clicks")

        cpa = None
        if not cpa_reasons:
            cpa = (Decimal(totals["cost"]) / Decimal(totals["conversions"])).quantize(
                CPA_SCALE, rounding=ROUND_HALF_UP
            )

        roas = None
        roas_percent = None
        if not roas_reasons:
            roas = _ratio(totals["revenue"], totals["cost"])
            roas_percent = _percent(roas)

        conversion_rate = None
        conversion_rate_percent = None
        if not conversion_rate_reasons:
            conversion_rate = _ratio(totals["conversions"], totals["clicks"])
            conversion_rate_percent = _percent(conversion_rate)

        result: dict[str, object] = dict(zip(group_fields, key))
        summary_fields = {
            key: value
            for field in NUMERIC_FIELDS
            for key, value in (
                (f"{field}_sum", totals[field]),
                (f"{field}_missing_count", missing_counts[field]),
            )
        }
        result.update(
            {
                "row_count": len(group_rows),
                **summary_fields,
                "vat_basis_values": ",".join(vat_values),
                "conversion_definition_values": ",".join(conversion_values),
                "revenue_definition_values": ",".join(revenue_values),
                "cpa": cpa,
                "cpa_reason": _join_reasons(cpa_reasons),
                "roas": roas,
                "roas_percent": roas_percent,
                "roas_reason": _join_reasons(roas_reasons),
                "conversion_rate": conversion_rate,
                "conversion_rate_percent": conversion_rate_percent,
                "conversion_rate_reason": _join_reasons(conversion_rate_reasons),
            }
        )
        results.append(result)

    return results


def write_metrics_csv(
    rows: Sequence[Mapping[str, object]], output_path: Path, group_by: Sequence[str]
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [*group_by, *RESULT_FIELDS]
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: "" if row.get(field) is None else row.get(field) for field in fields}
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="정규화 데이터의 CPA·ROAS·전환율 계산")
    parser.add_argument(
        "input_path",
        type=Path,
        help="단일 정규화 CSV 또는 *_normalized.csv 파일이 있는 디렉터리",
    )
    parser.add_argument("output_csv", type=Path)
    parser.add_argument(
        "--group-by",
        default=",".join(DEFAULT_GROUP_BY),
        help="쉼표로 구분한 집계 기준(기본값: channel,campaign)",
    )
    args = parser.parse_args()

    group_by = tuple(field.strip() for field in args.group_by.split(",") if field.strip())
    try:
        results = aggregate_metrics(read_normalized_input(args.input_path), group_by)
        write_metrics_csv(results, args.output_csv, group_by)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    print(f"metric_groups={len(results)}")
    print(f"group_by={','.join(group_by)}")
    print(f"output={args.output_csv.resolve()}")


if __name__ == "__main__":
    main()
