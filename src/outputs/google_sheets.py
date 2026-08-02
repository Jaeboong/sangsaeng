from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

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

INTEGER_FIELDS = {
    "cost",
    "impressions",
    "clicks",
    "conversions",
    "revenue",
    "source_row_number",
}

CHANNEL_SHEETS = {
    "ga4": ("ga4_normalized.csv", "GA4"),
    "meta": ("meta_normalized.csv", "Meta"),
    "naver_search": ("naver_search_normalized.csv", "네이버 검색광고"),
    "naver_gfa": ("naver_gfa_normalized.csv", "네이버 GFA"),
    "kakao_moment": ("kakao_moment_normalized.csv", "카카오 모먼트"),
}

CHANNEL_TAB_COLORS = {
    "ga4": {"red": 0.2588, "green": 0.5216, "blue": 0.9569},
    "meta": {"red": 0.0941, "green": 0.4667, "blue": 0.9490},
    "naver_search": {"red": 0.0118, "green": 0.7804, "blue": 0.3059},
    "naver_gfa": {"red": 0.0000, "green": 0.6196, "blue": 0.5843},
    "kakao_moment": {"red": 0.9961, "green": 0.8392, "blue": 0.0000},
    "weekly_comparison": {"red": 0.5569, "green": 0.2667, "blue": 0.6784},
}

WEEKLY_COMPARISON_FIELDS = [
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
]


def quote_sheet_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


@dataclass(frozen=True)
class SheetPayload:
    channel: str
    sheet_title: str
    source_path: Path
    values: list[list[Any]]

    @property
    def data_range(self) -> str:
        return f"{quote_sheet_title(self.sheet_title)}!A1"

    @property
    def clear_range(self) -> str:
        return quote_sheet_title(self.sheet_title)

    @property
    def verification_range(self) -> str:
        last_column = column_name(len(self.values[0]))
        return (
            f"{quote_sheet_title(self.sheet_title)}!"
            f"A1:{last_column}{len(self.values)}"
        )

    @property
    def data_rows(self) -> int:
        return len(self.values) - 1


@dataclass(frozen=True)
class UploadReport:
    spreadsheet_id: str
    channel_count: int
    data_rows: int
    updated_cells: int
    created_sheets: tuple[str, ...]


class SheetsGateway(Protocol):
    spreadsheet_id: str

    def list_sheet_titles(self) -> set[str]: ...

    def add_sheets(self, titles: Sequence[str]) -> None: ...

    def clear_ranges(self, ranges: Sequence[str]) -> None: ...

    def write_ranges(self, data: dict[str, list[list[Any]]]) -> int: ...

    def read_ranges(self, ranges: Sequence[str]) -> dict[str, list[list[Any]]]: ...

    def format_sheets(self, payloads: Sequence[SheetPayload]) -> None: ...


def column_name(column_number: int) -> str:
    if column_number < 1:
        raise ValueError("열 번호는 1 이상 필요")
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def build_format_requests(sheet_id: int, payload: SheetPayload) -> list[dict[str, Any]]:
    if payload.channel == "weekly_comparison":
        return build_weekly_comparison_format_requests(sheet_id, payload)
    row_count = len(payload.values)
    column_count = len(payload.values[0])
    full_range = {
        "sheetId": sheet_id,
        "startRowIndex": 0,
        "endRowIndex": row_count,
        "startColumnIndex": 0,
        "endColumnIndex": column_count,
    }
    header_range = {**full_range, "endRowIndex": 1}
    data_range = {**full_range, "startRowIndex": 1}
    header_color = {"red": 0.1216, "green": 0.2314, "blue": 0.3529}
    white = {"red": 1.0, "green": 1.0, "blue": 1.0}
    border_color = {"red": 0.8510, "green": 0.8784, "blue": 0.9059}

    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                    "tabColorStyle": {
                        "rgbColor": CHANNEL_TAB_COLORS[payload.channel]
                    },
                },
                "fields": "gridProperties.frozenRowCount,tabColorStyle",
            }
        },
        {
            "repeatCell": {
                "range": header_range,
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": header_color,
                        "textFormat": {
                            "foregroundColor": white,
                            "bold": True,
                            "fontSize": 10,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": (
                    "userEnteredFormat(backgroundColor,textFormat,"
                    "horizontalAlignment,verticalAlignment,wrapStrategy)"
                ),
            }
        },
        {
            "repeatCell": {
                "range": data_range,
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,textFormat.fontSize)",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 3, "endColumnIndex": 8},
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
                        "horizontalAlignment": "RIGHT",
                    }
                },
                "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 2, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 8, "endColumnIndex": 11},
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,wrapStrategy)",
            }
        },
        {
            "updateBorders": {
                "range": full_range,
                "innerHorizontal": {"style": "SOLID", "color": border_color},
                "bottom": {"style": "SOLID", "color": border_color},
            }
        },
        {"setBasicFilter": {"filter": {"range": full_range}}},
    ]

    for start_index, end_index, pixel_size in (
        (0, 1, 100),
        (1, 2, 95),
        (2, 3, 250),
        (3, 8, 105),
        (8, 11, 155),
        (11, 17, 160),
    ):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "properties": {"pixelSize": pixel_size},
                    "fields": "pixelSize",
                }
            }
        )

    requests.extend(
        [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 36},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": row_count,
                    },
                    "properties": {"pixelSize": 28},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "properties": {"hiddenByUser": True},
                    "fields": "hiddenByUser",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 11,
                        "endIndex": 17,
                    },
                    "properties": {"hiddenByUser": True},
                    "fields": "hiddenByUser",
                }
            },
        ]
    )
    return requests


def build_weekly_comparison_format_requests(
    sheet_id: int, payload: SheetPayload
) -> list[dict[str, Any]]:
    row_count = len(payload.values)
    column_count = len(payload.values[0])
    full_range = {
        "sheetId": sheet_id,
        "startRowIndex": 0,
        "endRowIndex": row_count,
        "startColumnIndex": 0,
        "endColumnIndex": column_count,
    }
    header_range = {**full_range, "endRowIndex": 1}
    data_range = {**full_range, "startRowIndex": 1}
    header_color = {"red": 0.2353, "green": 0.1608, "blue": 0.3765}
    white = {"red": 1.0, "green": 1.0, "blue": 1.0}
    border_color = {"red": 0.8510, "green": 0.8784, "blue": 0.9059}

    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                    "tabColorStyle": {
                        "rgbColor": CHANNEL_TAB_COLORS[payload.channel]
                    },
                },
                "fields": "gridProperties.frozenRowCount,tabColorStyle",
            }
        },
        {
            "repeatCell": {
                "range": header_range,
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": header_color,
                        "textFormat": {
                            "foregroundColor": white,
                            "bold": True,
                            "fontSize": 10,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": (
                    "userEnteredFormat(backgroundColor,textFormat,"
                    "horizontalAlignment,verticalAlignment,wrapStrategy)"
                ),
            }
        },
        {
            "repeatCell": {
                "range": data_range,
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,textFormat.fontSize)",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 3, "endColumnIndex": 7},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 10, "endColumnIndex": 11},
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "PERCENT", "pattern": "0.0%"},
                        "horizontalAlignment": "RIGHT",
                    }
                },
                "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 11, "endColumnIndex": 14},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 1, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "repeatCell": {
                "range": {**data_range, "startColumnIndex": 14, "endColumnIndex": 16},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "updateBorders": {
                "range": full_range,
                "innerHorizontal": {"style": "SOLID", "color": border_color},
                "bottom": {"style": "SOLID", "color": border_color},
            }
        },
        {"setBasicFilter": {"filter": {"range": full_range}}},
    ]

    for start_index, end_index, pixel_size in (
        (0, 1, 120),
        (1, 2, 240),
        (2, 3, 120),
        (3, 7, 110),
        (7, 10, 120),
        (10, 11, 105),
        (11, 13, 90),
        (13, 14, 115),
        (14, 15, 360),
        (15, 16, 240),
    ):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                    "properties": {"pixelSize": pixel_size},
                    "fields": "pixelSize",
                }
            }
        )

    requests.extend(
        [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 40},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": row_count,
                    },
                    "properties": {"pixelSize": 32},
                    "fields": "pixelSize",
                }
            },
        ]
    )

    for row_index, values in enumerate(payload.values[1:], start=1):
        metric = str(values[2])
        status = str(values[13])
        if metric == "conversion_rate":
            number_format = {"type": "PERCENT", "pattern": "0.00%"}
        elif metric == "roas":
            number_format = {"type": "NUMBER", "pattern": "0.00x"}
        else:
            number_format = {"type": "NUMBER", "pattern": "#,##0"}
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 7,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": number_format,
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
                }
            }
        )
        status_format = (
            {
                "backgroundColor": {"red": 0.9922, "green": 0.8980, "blue": 0.8980},
                "textFormat": {
                    "foregroundColor": {"red": 0.6000, "green": 0.0000, "blue": 0.0000},
                    "bold": True,
                },
            }
            if status == "excluded"
            else {
                "backgroundColor": {"red": 0.9020, "green": 0.9608, "blue": 0.9137},
                "textFormat": {
                    "foregroundColor": {"red": 0.0784, "green": 0.3608, "blue": 0.1490},
                    "bold": True,
                },
            }
        )
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 13,
                        "endColumnIndex": 14,
                    },
                    "cell": {"userEnteredFormat": status_format},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )
    return requests


class GoogleSheetsGateway:
    def __init__(self, service: Any, spreadsheet_id: str) -> None:
        self._service = service
        self.spreadsheet_id = spreadsheet_id

    def list_sheet_titles(self) -> set[str]:
        result = (
            self._service.spreadsheets()
            .get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties.title",
            )
            .execute()
        )
        return {
            sheet["properties"]["title"]
            for sheet in result.get("sheets", [])
            if "title" in sheet.get("properties", {})
        }

    def add_sheets(self, titles: Sequence[str]) -> None:
        if not titles:
            return
        requests = [{"addSheet": {"properties": {"title": title}}} for title in titles]
        (
            self._service.spreadsheets()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            )
            .execute()
        )

    def clear_ranges(self, ranges: Sequence[str]) -> None:
        if not ranges:
            return
        (
            self._service.spreadsheets()
            .values()
            .batchClear(
                spreadsheetId=self.spreadsheet_id,
                body={"ranges": list(ranges)},
            )
            .execute()
        )

    def write_ranges(self, data: dict[str, list[list[Any]]]) -> int:
        result = (
            self._service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": [
                        {"range": data_range, "majorDimension": "ROWS", "values": values}
                        for data_range, values in data.items()
                    ],
                },
            )
            .execute()
        )
        return int(result.get("totalUpdatedCells", 0))

    def read_ranges(self, ranges: Sequence[str]) -> dict[str, list[list[Any]]]:
        result = (
            self._service.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=self.spreadsheet_id,
                ranges=list(ranges),
                majorDimension="ROWS",
                valueRenderOption="UNFORMATTED_VALUE",
            )
            .execute()
        )
        value_ranges = result.get("valueRanges", [])
        return {
            data_range: value_range.get("values", [])
            for data_range, value_range in zip(ranges, value_ranges, strict=True)
        }

    def format_sheets(self, payloads: Sequence[SheetPayload]) -> None:
        result = (
            self._service.spreadsheets()
            .get(
                spreadsheetId=self.spreadsheet_id,
                fields="sheets.properties(sheetId,title)",
            )
            .execute()
        )
        sheet_ids = {
            sheet["properties"]["title"]: sheet["properties"]["sheetId"]
            for sheet in result.get("sheets", [])
        }
        requests: list[dict[str, Any]] = []
        for payload in payloads:
            sheet_id = sheet_ids.get(payload.sheet_title)
            if sheet_id is None:
                raise RuntimeError(f"서식 대상 탭 없음: {payload.sheet_title}")
            requests.extend(build_format_requests(sheet_id, payload))
        if requests:
            (
                self._service.spreadsheets()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": requests},
                )
                .execute()
            )


def parse_cell(field: str, value: str, path: Path, row_number: int) -> Any:
    stripped = value.strip()
    if stripped == "" or field not in INTEGER_FIELDS:
        return stripped
    try:
        return int(stripped)
    except ValueError as error:
        raise ValueError(
            f"{path.name}:{row_number}: {field} 정수 파싱 실패: {value!r}"
        ) from error


def load_channel_csv(path: Path, expected_channel: str, sheet_title: str) -> SheetPayload:
    if not path.is_file():
        raise ValueError(f"정규화 CSV 없음: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames != OUTPUT_FIELDS:
            raise ValueError(
                f"{path.name}: 공통 스키마 불일치: {reader.fieldnames!r}"
            )

        values: list[list[Any]] = [list(OUTPUT_FIELDS)]
        seen_keys: set[tuple[str, str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"{path.name}:{row_number}: 헤더보다 많은 필드")
            if row["channel"].strip() != expected_channel:
                raise ValueError(
                    f"{path.name}:{row_number}: 채널 불일치: {row['channel']!r}"
                )
            key = (
                row["date"].strip(),
                row["channel"].strip(),
                row["campaign"].strip(),
            )
            if key in seen_keys:
                raise ValueError(f"{path.name}:{row_number}: 공통 키 중복: {key}")
            seen_keys.add(key)
            values.append(
                [parse_cell(field, row[field], path, row_number) for field in OUTPUT_FIELDS]
            )

    if len(values) == 1:
        raise ValueError(f"{path.name}: 데이터 행 없음")
    return SheetPayload(expected_channel, sheet_title, path, values)


def load_channel_payloads(normalized_dir: Path) -> list[SheetPayload]:
    return [
        load_channel_csv(normalized_dir / filename, channel, sheet_title)
        for channel, (filename, sheet_title) in CHANNEL_SHEETS.items()
    ]


def parse_report_cell(field: str, value: str, path: Path, row_number: int) -> Any:
    stripped = value.strip()
    if stripped == "":
        return ""
    if field in {"previous_days", "current_days"}:
        try:
            return int(stripped)
        except ValueError as error:
            raise ValueError(
                f"{path.name}:{row_number}: {field} 정수 파싱 실패: {value!r}"
            ) from error
    if field in {"previous_value", "current_value", "change", "change_rate"}:
        try:
            return int(stripped) if "." not in stripped else float(stripped)
        except ValueError as error:
            raise ValueError(
                f"{path.name}:{row_number}: {field} 숫자 파싱 실패: {value!r}"
            ) from error
    return stripped


def load_weekly_comparison(path: Path) -> SheetPayload:
    if not path.is_file():
        raise ValueError(f"전주비교 CSV 없음: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames != WEEKLY_COMPARISON_FIELDS:
            raise ValueError(f"{path.name}: 전주비교 스키마 불일치: {reader.fieldnames!r}")
        values: list[list[Any]] = [list(WEEKLY_COMPARISON_FIELDS)]
        seen_keys: set[tuple[str, str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"{path.name}:{row_number}: 헤더보다 많은 필드")
            status = row["comparison_status"].strip()
            if status not in {"comparable", "excluded"}:
                raise ValueError(
                    f"{path.name}:{row_number}: 비교 상태 오류: {status!r}"
                )
            key = (
                row["channel"].strip(),
                row["campaign"].strip(),
                row["metric"].strip(),
            )
            if key in seen_keys:
                raise ValueError(f"{path.name}:{row_number}: 전주비교 키 중복: {key}")
            seen_keys.add(key)
            values.append(
                [
                    parse_report_cell(field, row[field], path, row_number)
                    for field in WEEKLY_COMPARISON_FIELDS
                ]
            )
    if len(values) == 1:
        raise ValueError(f"{path.name}: 데이터 행 없음")
    return SheetPayload("weekly_comparison", "전주비교", path, values)


def pad_readback_rows(values: list[list[Any]], width: int) -> list[list[Any]]:
    return [row + [""] * max(0, width - len(row)) for row in values]


def upload_payloads(
    gateway: SheetsGateway,
    payloads: Sequence[SheetPayload],
    *,
    create_missing_sheets: bool = True,
) -> UploadReport:
    existing_titles = gateway.list_sheet_titles()
    required_titles = [payload.sheet_title for payload in payloads]
    missing_titles = [title for title in required_titles if title not in existing_titles]
    if missing_titles and not create_missing_sheets:
        raise ValueError(f"구글시트 탭 없음: {', '.join(missing_titles)}")
    gateway.add_sheets(missing_titles)

    clear_ranges = [payload.clear_range for payload in payloads]
    write_data = {payload.data_range: payload.values for payload in payloads}
    gateway.clear_ranges(clear_ranges)
    updated_cells = gateway.write_ranges(write_data)

    verification_ranges = [payload.verification_range for payload in payloads]
    actual_data = gateway.read_ranges(verification_ranges)
    for payload in payloads:
        expected_values = payload.values
        actual_values = actual_data.get(payload.verification_range)
        if actual_values is None or pad_readback_rows(
            actual_values, len(expected_values[0])
        ) != expected_values:
            raise RuntimeError(f"업로드 후 값 검증 실패: {payload.verification_range}")
    gateway.format_sheets(payloads)

    return UploadReport(
        spreadsheet_id=gateway.spreadsheet_id,
        channel_count=len(payloads),
        data_rows=sum(payload.data_rows for payload in payloads),
        updated_cells=updated_cells,
        created_sheets=tuple(missing_titles),
    )


def upload_channel_payloads(
    gateway: SheetsGateway,
    payloads: Sequence[SheetPayload],
    *,
    create_missing_sheets: bool = True,
) -> UploadReport:
    return upload_payloads(
        gateway,
        payloads,
        create_missing_sheets=create_missing_sheets,
    )


def build_google_service(credentials_path: Path) -> Any:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as error:
        raise RuntimeError(
            "Google API 라이브러리 필요: "
            "python -m pip install google-api-python-client google-auth"
        ) from error

    if not credentials_path.is_file():
        raise ValueError(f"서비스 계정 JSON 없음: {credentials_path}")
    credentials = Credentials.from_service_account_file(
        str(credentials_path), scopes=[SHEETS_SCOPE]
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="채널별 정규화 CSV와 선택 보고서를 구글시트 탭에 업로드"
    )
    parser.add_argument("normalized_dir", type=Path)
    parser.add_argument("--weekly-comparison", type=Path)
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID"),
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=(
            Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
            if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            else None
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-create-missing-sheets", action="store_true")
    args = parser.parse_args()

    payloads = load_channel_payloads(args.normalized_dir)
    if args.weekly_comparison:
        payloads.append(load_weekly_comparison(args.weekly_comparison))
    print(f"validated_tabs={len(payloads)}")
    print(f"validated_rows={sum(payload.data_rows for payload in payloads)}")
    for payload in payloads:
        print(
            f"sheet[{payload.channel}]={payload.sheet_title} "
            f"rows={payload.data_rows} source={payload.source_path}"
        )

    if args.dry_run:
        print("dry_run=true")
        return
    if not args.spreadsheet_id:
        parser.error("--spreadsheet-id 또는 GOOGLE_SHEETS_SPREADSHEET_ID 필요")
    if args.credentials is None:
        parser.error("--credentials 또는 GOOGLE_APPLICATION_CREDENTIALS 필요")

    service = build_google_service(args.credentials)
    report = upload_payloads(
        GoogleSheetsGateway(service, args.spreadsheet_id),
        payloads,
        create_missing_sheets=not args.no_create_missing_sheets,
    )
    print(f"uploaded_tabs={report.channel_count}")
    print(f"uploaded_rows={report.data_rows}")
    print(f"updated_cells={report.updated_cells}")
    print(f"created_sheets={','.join(report.created_sheets)}")


if __name__ == "__main__":
    main()
