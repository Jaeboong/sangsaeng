from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


SCHEMA_VERSION = "1.0"
ADAPTER_VERSION = "1.0"

OUTPUT_FIELDS = [
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
]

CHANNEL_OUTPUT_FILENAMES = {
    "ga4": "ga4_normalized.csv",
    "meta": "meta_normalized.csv",
    "naver_search": "naver_search_normalized.csv",
    "naver_gfa": "naver_gfa_normalized.csv",
    "kakao_moment": "kakao_moment_normalized.csv",
}


def parse_date(fmt: str) -> Callable[[str], str]:
    def parser(value: str) -> str:
        return datetime.strptime(value.strip(), fmt).date().isoformat()

    return parser


@dataclass(frozen=True)
class Adapter:
    channel: str
    signature: frozenset[str]
    date_column: str
    date_parser: Callable[[str], str]
    campaign_column: str
    metric_columns: dict[str, str | None]
    vat_basis: str
    conversion_definition: str | None
    revenue_definition: str
    source_dimension_columns: tuple[str, ...] = ()
    conversion_definition_column: str | None = None


ADAPTERS = (
    Adapter(
        channel="ga4",
        signature=frozenset(
            {"날짜", "세션 기본 채널 그룹", "세션 캠페인", "주요 이벤트 수", "총 수익"}
        ),
        date_column="날짜",
        date_parser=parse_date("%Y%m%d"),
        campaign_column="세션 캠페인",
        metric_columns={
            "cost": None,
            "impressions": None,
            "clicks": None,
            "conversions": "주요 이벤트 수",
            "revenue": "총 수익",
        },
        vat_basis="not_applicable",
        conversion_definition="주요 이벤트",
        revenue_definition="총 수익",
        source_dimension_columns=("세션 기본 채널 그룹",),
    ),
    Adapter(
        channel="meta",
        signature=frozenset(
            {
                "Reporting starts",
                "Reporting ends",
                "Campaign name",
                "Amount spent (KRW)",
                "Impressions",
                "Link clicks",
                "Results",
                "Result type",
            }
        ),
        date_column="Reporting starts",
        date_parser=parse_date("%Y-%m-%d"),
        campaign_column="Campaign name",
        metric_columns={
            "cost": "Amount spent (KRW)",
            "impressions": "Impressions",
            "clicks": "Link clicks",
            "conversions": "Results",
            "revenue": None,
        },
        vat_basis="unknown",
        conversion_definition=None,
        conversion_definition_column="Result type",
        revenue_definition="",
    ),
    Adapter(
        channel="naver_search",
        signature=frozenset(
            {"일별", "캠페인", "노출수", "클릭수", "총비용(VAT제외,원)", "전환수", "전환매출액(원)"}
        ),
        date_column="일별",
        date_parser=parse_date("%Y.%m.%d."),
        campaign_column="캠페인",
        metric_columns={
            "cost": "총비용(VAT제외,원)",
            "impressions": "노출수",
            "clicks": "클릭수",
            "conversions": "전환수",
            "revenue": "전환매출액(원)",
        },
        vat_basis="excluded",
        conversion_definition="전환수(원본 정의 미표기)",
        revenue_definition="전환매출액",
    ),
    Adapter(
        channel="naver_gfa",
        signature=frozenset(
            {"기간", "캠페인명", "광고비(VAT포함,원)", "노출", "클릭", "전환수(구매완료)"}
        ),
        date_column="기간",
        date_parser=parse_date("%m/%d/%Y"),
        campaign_column="캠페인명",
        metric_columns={
            "cost": "광고비(VAT포함,원)",
            "impressions": "노출",
            "clicks": "클릭",
            "conversions": "전환수(구매완료)",
            "revenue": None,
        },
        vat_basis="included",
        conversion_definition="구매완료",
        revenue_definition="",
    ),
    Adapter(
        channel="kakao_moment",
        signature=frozenset(
            {"일자", "캠페인", "비용(원)", "노출수", "클릭수", "전환(구매)", "전환값(원)"}
        ),
        date_column="일자",
        date_parser=parse_date("%Y%m%d"),
        campaign_column="캠페인",
        metric_columns={
            "cost": "비용(원)",
            "impressions": "노출수",
            "clicks": "클릭수",
            "conversions": "전환(구매)",
            "revenue": "전환값(원)",
        },
        vat_basis="unknown",
        conversion_definition="구매",
        revenue_definition="전환값",
    ),
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], int]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("#")),
        None,
    )
    if header_index is None:
        raise ValueError("헤더 미발견")
    if header_index > 5:
        raise ValueError(f"헤더 전 선행 행 과다: {header_index}개")

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    headers = reader.fieldnames or []
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("헤더보다 많은 필드가 있는 행 발견")
    return headers, rows, header_index + 2


def detect_adapter(headers: list[str]) -> Adapter:
    header_set = frozenset(headers)
    matches = [adapter for adapter in ADAPTERS if adapter.signature <= header_set]
    if len(matches) != 1:
        channels = ", ".join(adapter.channel for adapter in matches) or "없음"
        raise ValueError(f"채널 판별 실패 또는 모호함: {channels}")
    return matches[0]


def parse_nonnegative_integer(value: str, field: str) -> str:
    stripped = value.strip().replace(",", "")
    if stripped == "":
        return ""
    try:
        parsed = int(stripped)
    except ValueError as error:
        raise ValueError(f"{field} 정수 파싱 실패: {value!r}") from error
    if parsed < 0:
        raise ValueError(f"{field} 음수: {parsed}")
    return str(parsed)


def normalize_file(path: Path) -> list[dict[str, str]]:
    headers, source_rows, first_data_line = read_csv(path)
    adapter = detect_adapter(headers)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    normalized_rows: list[dict[str, str]] = []

    for offset, source in enumerate(source_rows):
        source_row_number = first_data_line + offset
        try:
            campaign = source[adapter.campaign_column].strip()
            if not campaign:
                raise ValueError("캠페인 결측")

            metrics = {
                target: ""
                if source_column is None
                else parse_nonnegative_integer(source[source_column], target)
                for target, source_column in adapter.metric_columns.items()
            }
            if metrics["clicks"] and metrics["impressions"]:
                if int(metrics["clicks"]) > int(metrics["impressions"]):
                    raise ValueError("클릭 수가 노출 수보다 큼")

            dimensions = {
                column: source[column].strip() for column in adapter.source_dimension_columns
            }
            conversion_definition = (
                source[adapter.conversion_definition_column].strip()
                if adapter.conversion_definition_column
                else adapter.conversion_definition or ""
            )

            normalized_rows.append(
                {
                    "date": adapter.date_parser(source[adapter.date_column]),
                    "channel": adapter.channel,
                    "campaign": campaign,
                    **metrics,
                    "vat_basis": adapter.vat_basis,
                    "conversion_definition": conversion_definition,
                    "revenue_definition": adapter.revenue_definition,
                    "source_dimensions": (
                        json.dumps(dimensions, ensure_ascii=False, sort_keys=True)
                        if dimensions
                        else ""
                    ),
                    "source_file": path.name,
                    "source_row_number": str(source_row_number),
                    "source_file_hash": file_hash,
                    "schema_version": SCHEMA_VERSION,
                    "adapter_version": ADAPTER_VERSION,
                }
            )
        except (KeyError, ValueError) as error:
            raise ValueError(f"{path.name}:{source_row_number}: {error}") from error

    return normalized_rows


def normalize_directory(input_dir: Path) -> list[dict[str, str]]:
    paths = sorted(input_dir.glob("*.csv"))
    if not paths:
        raise ValueError(f"CSV 파일 없음: {input_dir}")

    rows = [row for path in paths for row in normalize_file(path)]
    seen: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["date"], row["channel"], row["campaign"])
        if key in seen:
            previous = seen[key]
            raise ValueError(
                "공통 키 중복: "
                f"{key} ({previous['source_file']}:{previous['source_row_number']}, "
                f"{row['source_file']}:{row['source_row_number']})"
            )
        seen[key] = row

    return sorted(rows, key=lambda row: (row["date"], row["channel"], row["campaign"]))


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_channel_csvs(
    rows: list[dict[str, str]], output_dir: Path
) -> dict[str, Path]:
    rows_by_channel: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_channel.setdefault(row["channel"], []).append(row)

    unknown_channels = sorted(set(rows_by_channel) - set(CHANNEL_OUTPUT_FILENAMES))
    if unknown_channels:
        raise ValueError(f"출력 파일명이 없는 채널: {', '.join(unknown_channels)}")

    output_paths: dict[str, Path] = {}
    for channel, filename in CHANNEL_OUTPUT_FILENAMES.items():
        channel_rows = rows_by_channel.get(channel)
        if not channel_rows:
            continue
        output_path = output_dir / filename
        write_csv(channel_rows, output_path)
        output_paths[channel] = output_path

    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="채널별 CSV를 공통 스키마의 채널별 파일로 정규화"
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    rows = normalize_directory(args.input_dir)
    output_paths = write_channel_csvs(rows, args.output_dir)
    print(f"normalized_files={len(list(args.input_dir.glob('*.csv')))}")
    print(f"normalized_rows={len(rows)}")
    print(f"output_files={len(output_paths)}")
    for channel, output_path in output_paths.items():
        channel_rows = sum(row["channel"] == channel for row in rows)
        print(f"output[{channel}]={output_path.resolve()} rows={channel_rows}")


if __name__ == "__main__":
    main()
