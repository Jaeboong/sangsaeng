from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from src.metrics.calculate_metrics import (
        RATIO_SCALE,
        aggregate_metrics,
        read_normalized_input,
    )
except ModuleNotFoundError:  # 직접 파일 실행 지원
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.metrics.calculate_metrics import (  # type: ignore[no-redef]
        RATIO_SCALE,
        aggregate_metrics,
        read_normalized_input,
    )


GROUP_FIELDS = ("channel", "campaign")
METRICS = (
    "cost",
    "impressions",
    "clicks",
    "conversions",
    "revenue",
    "cpa",
    "roas",
    "conversion_rate",
)
RAW_SUM_FIELDS = {
    "cost": "cost_sum",
    "impressions": "impressions_sum",
    "clicks": "clicks_sum",
    "conversions": "conversions_sum",
    "revenue": "revenue_sum",
}
DERIVED_REASON_FIELDS = {
    "cpa": "cpa_reason",
    "roas": "roas_reason",
    "conversion_rate": "conversion_rate_reason",
}
SEMANTIC_FIELDS = {
    "cost": ("vat_basis_values",),
    "impressions": (),
    "clicks": (),
    "conversions": ("conversion_definition_values",),
    "revenue": ("revenue_definition_values",),
    "cpa": ("vat_basis_values", "conversion_definition_values"),
    "roas": ("vat_basis_values", "revenue_definition_values"),
    "conversion_rate": ("conversion_definition_values",),
}
SEMANTIC_LABELS = {
    "vat_basis_values": "VAT 기준",
    "conversion_definition_values": "전환 정의",
    "revenue_definition_values": "매출 정의",
}
OUTPUT_FIELDS = (
    "channel",
    "campaign",
    "metric",
    "previous_week_start",
    "previous_week_end",
    "current_week_start",
    "current_week_end",
    "previous_value",
    "current_value",
    "change",
    "change_rate",
    "previous_days",
    "current_days",
    "comparison_status",
    "exclusion_reason",
    "period_warning",
)


def _parse_row_date(row: Mapping[str, object], row_number: int) -> date:
    raw = row.get("date")
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{row_number}행 date ISO 형식 오류: {raw!r}") from error


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def resolve_current_week_start(
    rows: Sequence[Mapping[str, object]],
    *,
    current_week_start: date | None = None,
    reference_date: date | None = None,
) -> date:
    """비교할 금주 시작일을 결정한다.

    기본값은 데이터 안에서 월~일 7개 날짜가 모두 존재하는 최신 ISO 주간이다.
    기준일 지정 시 기준일 현재 완전히 종료된 최신 주간을 사용한다. 일요일은
    해당 주간, 월~토요일은 직전 주간을 선택한다.
    """

    if current_week_start is not None and reference_date is not None:
        raise ValueError("current_week_start와 reference_date 동시 지정 불가")
    if current_week_start is not None:
        if current_week_start.weekday() != 0:
            raise ValueError("current_week_start는 월요일이어야 함")
        return current_week_start
    if reference_date is not None:
        week_start = _monday(reference_date)
        return week_start if reference_date.weekday() == 6 else week_start - timedelta(days=7)

    if not rows:
        raise ValueError("비교할 정규화 데이터 없음")
    dates = {_parse_row_date(row, number) for number, row in enumerate(rows, start=2)}
    dates_by_week: dict[date, set[date]] = defaultdict(set)
    for day in dates:
        dates_by_week[_monday(day)].add(day)
    complete_weeks = [
        week_start
        for week_start, actual_dates in dates_by_week.items()
        if actual_dates == {week_start + timedelta(days=offset) for offset in range(7)}
    ]
    if not complete_weeks:
        raise ValueError("월~일 7일이 모두 존재하는 완전 주간 없음")
    return max(complete_weeks)


def _group_key(row: Mapping[str, object]) -> tuple[str, str]:
    return (str(row.get("channel", "")), str(row.get("campaign", "")))


def _index_aggregates(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], dict[str, object]]:
    return {
        (str(item["channel"]), str(item["campaign"])): item
        for item in aggregate_metrics(rows, GROUP_FIELDS)
    }


def _group_days(
    dated_rows: Sequence[tuple[Mapping[str, object], date]],
) -> dict[tuple[str, str], int]:
    days: dict[tuple[str, str], set[date]] = defaultdict(set)
    for row, day in dated_rows:
        days[_group_key(row)].add(day)
    return {key: len(values) for key, values in days.items()}


def _metric_value(summary: Mapping[str, object], metric: str) -> object | None:
    return summary.get(RAW_SUM_FIELDS.get(metric, metric))


def _definition_values(summary: Mapping[str, object], field: str) -> tuple[str, ...]:
    raw = str(summary.get(field, "")).strip()
    return tuple(value for value in raw.split(",") if value) if raw else ()


def _join_reasons(reasons: Iterable[str]) -> str:
    return " | ".join(dict.fromkeys(reason for reason in reasons if reason))


def _unavailable_reasons(
    metric: str,
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> str:
    reasons: list[str] = []
    for field in SEMANTIC_FIELDS[metric]:
        label = SEMANTIC_LABELS[field]
        previous_values = _definition_values(previous, field)
        current_values = _definition_values(current, field)
        if len(previous_values) > 1:
            reasons.append(f"전주 {label} 혼합: {', '.join(previous_values)}")
        if len(current_values) > 1:
            reasons.append(f"금주 {label} 혼합: {', '.join(current_values)}")
        if previous_values != current_values:
            previous_text = ", ".join(previous_values) or "결측"
            current_text = ", ".join(current_values) or "결측"
            reasons.append(f"{label} 불일치: 전주={previous_text}, 금주={current_text}")

    if metric in RAW_SUM_FIELDS:
        for period_label, summary in (("전주", previous), ("금주", current)):
            missing_count = int(summary.get(f"{metric}_missing_count", 0) or 0)
            if missing_count:
                reasons.append(f"{period_label} 필수 값 결측: {metric} {missing_count}행")
    else:
        reason_field = DERIVED_REASON_FIELDS[metric]
        for period_label, summary in (("전주", previous), ("금주", current)):
            reason = str(summary.get(reason_field, "")).strip()
            if reason:
                reasons.append(f"{period_label} 계산 제외: {reason}")
    return _join_reasons(reasons)


def _period_warning(previous_days: int, current_days: int) -> str:
    warnings: list[str] = []
    if 0 < previous_days < 7:
        warnings.append(f"전주 기간 불완전: {previous_days}/7일")
    if 0 < current_days < 7:
        warnings.append(f"금주 기간 불완전: {current_days}/7일")
    return " | ".join(warnings)


def compare_weeks(
    rows: Iterable[Mapping[str, object]], current_week_start: date
) -> list[dict[str, object]]:
    """동일 채널·캠페인의 전주와 금주 원천 합계 및 파생 지표 비교."""

    if current_week_start.weekday() != 0:
        raise ValueError("current_week_start는 월요일이어야 함")
    materialized = list(rows)
    dated_rows = [
        (row, _parse_row_date(row, number))
        for number, row in enumerate(materialized, start=2)
    ]
    previous_week_start = current_week_start - timedelta(days=7)
    previous_week_end = previous_week_start + timedelta(days=6)
    current_week_end = current_week_start + timedelta(days=6)

    previous_dated = [
        (row, day)
        for row, day in dated_rows
        if previous_week_start <= day <= previous_week_end
    ]
    current_dated = [
        (row, day)
        for row, day in dated_rows
        if current_week_start <= day <= current_week_end
    ]
    if not previous_dated and not current_dated:
        raise ValueError("선택한 전주·금주 구간에 데이터 없음")

    previous_index = _index_aggregates([row for row, _ in previous_dated])
    current_index = _index_aggregates([row for row, _ in current_dated])
    previous_days_by_group = _group_days(previous_dated)
    current_days_by_group = _group_days(current_dated)

    results: list[dict[str, object]] = []
    for key in sorted(set(previous_index) | set(current_index)):
        previous = previous_index.get(key)
        current = current_index.get(key)
        previous_days = previous_days_by_group.get(key, 0)
        current_days = current_days_by_group.get(key, 0)
        warning = _period_warning(previous_days, current_days)

        for metric in METRICS:
            previous_value = _metric_value(previous, metric) if previous else None
            current_value = _metric_value(current, metric) if current else None
            change: object | None = None
            change_rate: Decimal | None = None
            exclusion_reason = ""

            if previous is None:
                status = "new"
            elif current is None:
                status = "current_not_run"
            else:
                exclusion_reason = _unavailable_reasons(metric, previous, current)
                if previous_value is None or current_value is None:
                    if not exclusion_reason:
                        exclusion_reason = "전주·금주 중 비교 값 결측"
                    status = "excluded"
                elif exclusion_reason:
                    status = "excluded"
                else:
                    change = current_value - previous_value  # type: ignore[operator]
                    if Decimal(previous_value) == 0:
                        status = "previous_zero"
                        exclusion_reason = "전주 0으로 증감률 계산 제외"
                    else:
                        status = "comparable"
                        change_rate = (
                            Decimal(change) / Decimal(previous_value)
                        ).quantize(RATIO_SCALE, rounding=ROUND_HALF_UP)

            results.append(
                {
                    "channel": key[0],
                    "campaign": key[1],
                    "metric": metric,
                    "previous_week_start": previous_week_start.isoformat(),
                    "previous_week_end": previous_week_end.isoformat(),
                    "current_week_start": current_week_start.isoformat(),
                    "current_week_end": current_week_end.isoformat(),
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "change": change,
                    "change_rate": change_rate,
                    "previous_days": previous_days,
                    "current_days": current_days,
                    "comparison_status": status,
                    "exclusion_reason": exclusion_reason,
                    "period_warning": warning,
                }
            )
    return results


def build_weekly_comparison(
    rows: Iterable[Mapping[str, object]],
    *,
    current_week_start: date | None = None,
    reference_date: date | None = None,
) -> tuple[date, list[dict[str, object]]]:
    materialized = list(rows)
    resolved_start = resolve_current_week_start(
        materialized,
        current_week_start=current_week_start,
        reference_date=reference_date,
    )
    return resolved_start, compare_weeks(materialized, resolved_start)


def write_comparison_csv(
    rows: Sequence[Mapping[str, object]], output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: "" if row.get(field) is None else row.get(field) for field in OUTPUT_FIELDS}
            )


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("YYYY-MM-DD 형식 필요") from error


def main() -> None:
    parser = argparse.ArgumentParser(description="ISO 주간 기준 전주 대비 지표 비교")
    parser.add_argument(
        "input_path",
        type=Path,
        help="단일 정규화 CSV 또는 *_normalized.csv 파일이 있는 디렉터리",
    )
    parser.add_argument("output_csv", type=Path)
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--current-week-start",
        type=_iso_date,
        help="금주 월요일. 생략 시 데이터의 최신 완전 주간",
    )
    period_group.add_argument(
        "--reference-date",
        type=_iso_date,
        help="해당 날짜 현재 완전히 종료된 최신 ISO 주간 선택",
    )
    args = parser.parse_args()

    current_start, comparisons = build_weekly_comparison(
        read_normalized_input(args.input_path),
        current_week_start=args.current_week_start,
        reference_date=args.reference_date,
    )
    write_comparison_csv(comparisons, args.output_csv)
    print(f"comparison_rows={len(comparisons)}")
    print(f"previous_week={current_start - timedelta(days=7)}~{current_start - timedelta(days=1)}")
    print(f"current_week={current_start}~{current_start + timedelta(days=6)}")
    print(f"output={args.output_csv.resolve()}")


if __name__ == "__main__":
    main()
