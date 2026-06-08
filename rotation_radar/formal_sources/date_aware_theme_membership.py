from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMBERSHIP_FIELDS = [
    "symbol",
    "name",
    "theme",
    "effective_start",
    "effective_end",
    "source_date",
    "source_type",
    "source_url",
    "confidence",
    "notes",
]

GAP_FIELDS = [
    "symbol",
    "name",
    "current_theme",
    "missing_field",
    "missing_reason",
    "suggested_source",
    "checked_at",
]

VALID_CONFIDENCE = {"high", "medium", "low"}
STATIC_SOURCE_TYPES = {"", "current_static_map", "theme_map", "static_theme_map"}


@dataclass(frozen=True)
class FormalUniverseSymbol:
    symbol: str
    name: str
    current_theme: str


def validate_date_aware_theme_membership(
    *,
    membership_file: str | Path,
    formal_universe_path: str | Path,
    output_path: str | Path,
    gap_report_path: str | Path,
    theme_map_path: str | Path | None = None,
    theme: str | None = None,
    target_symbols: set[str] | None = None,
) -> dict[str, Any]:
    formal_universe = load_formal_universe(formal_universe_path)
    if theme:
        formal_universe = [item for item in formal_universe if item.current_theme == theme]
    if target_symbols is not None:
        formal_universe = [item for item in formal_universe if item.symbol in target_symbols]
    current_theme_by_symbol = load_current_theme_map(theme_map_path) if theme_map_path else {}
    membership_rows = _read_membership_rows(Path(membership_file))
    if theme:
        membership_rows = [row for row in membership_rows if row.get("theme") == theme]
    if target_symbols is not None:
        membership_rows = [row for row in membership_rows if row.get("symbol") in target_symbols]
    usable_rows, invalid_rows = classify_membership_rows(membership_rows)

    usable_by_symbol: dict[str, dict[str, str]] = {}
    formal_symbols = {item.symbol for item in formal_universe}
    for row in usable_rows:
        if row["symbol"] in formal_symbols:
            usable_by_symbol[row["symbol"]] = row

    checked_at = _utc_now_iso()
    gap_rows = build_gap_rows(
        formal_universe=formal_universe,
        usable_by_symbol=usable_by_symbol,
        invalid_rows=invalid_rows,
        current_theme_by_symbol=current_theme_by_symbol,
        checked_at=checked_at,
    )
    readiness = build_readiness(
        formal_universe=formal_universe,
        usable_by_symbol=usable_by_symbol,
        invalid_rows=invalid_rows,
        gap_rows=gap_rows,
        theme=theme,
    )

    _write_rows(Path(gap_report_path), GAP_FIELDS, gap_rows)
    _write_json(Path(output_path), readiness)
    return readiness


def load_formal_universe(path: str | Path) -> list[FormalUniverseSymbol]:
    output: list[FormalUniverseSymbol] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            output.append(
                FormalUniverseSymbol(
                    symbol=symbol,
                    name=str(row.get("name", "")).strip(),
                    current_theme=str(row.get("theme", "")).strip(),
                )
            )
    output.sort(key=lambda item: item.symbol)
    return output


def load_current_theme_map(path: str | Path) -> dict[str, str]:
    output: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            theme = str(row.get("theme", "")).strip()
            primary = str(row.get("primary", "")).strip().lower()
            if symbol and theme and symbol not in output:
                output[symbol] = theme
            if symbol and theme and primary == "yes":
                output[symbol] = theme
    return output


def classify_membership_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    usable: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    for row in rows:
        missing = _missing_required_fields(row)
        if missing:
            invalid.append({**row, "_invalid_reason": f"missing:{','.join(missing)}"})
            continue
        if row["confidence"] not in VALID_CONFIDENCE:
            invalid.append({**row, "_invalid_reason": "invalid_confidence"})
            continue
        if row["source_type"] in STATIC_SOURCE_TYPES:
            invalid.append({**row, "_invalid_reason": "static_source_not_date_aware"})
            continue
        try:
            _parse_iso_date(row["effective_start"])
            _parse_iso_date(row["source_date"])
            if row["effective_end"]:
                end = _parse_iso_date(row["effective_end"])
                if end < _parse_iso_date(row["effective_start"]):
                    invalid.append({**row, "_invalid_reason": "effective_end_before_start"})
                    continue
        except ValueError as exc:
            invalid.append({**row, "_invalid_reason": str(exc)})
            continue
        usable.append(row)
    return usable, invalid


def build_gap_rows(
    *,
    formal_universe: list[FormalUniverseSymbol],
    usable_by_symbol: dict[str, dict[str, str]],
    invalid_rows: list[dict[str, str]],
    current_theme_by_symbol: dict[str, str],
    checked_at: str,
) -> list[dict[str, str]]:
    invalid_reasons_by_symbol: dict[str, set[str]] = {}
    for row in invalid_rows:
        symbol = row.get("symbol", "")
        if symbol:
            invalid_reasons_by_symbol.setdefault(symbol, set()).add(row.get("_invalid_reason", "invalid_membership_row"))

    gaps: list[dict[str, str]] = []
    for item in formal_universe:
        if item.symbol in usable_by_symbol:
            continue
        current_theme = current_theme_by_symbol.get(item.symbol) or item.current_theme
        reasons = sorted(invalid_reasons_by_symbol.get(item.symbol, set()))
        if reasons:
            missing_field = "date_aware_source_fields"
            missing_reason = ";".join(reasons)
        else:
            missing_field = "effective_start/source_date/source_url/confidence"
            missing_reason = "current_static_map_only"
        gaps.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "current_theme": current_theme,
                "missing_field": missing_field,
                "missing_reason": missing_reason,
                "suggested_source": "dated company filings, product revenue notes, dated research notes, or archived daily radar theme definitions",
                "checked_at": checked_at,
            }
        )
    gaps.sort(key=lambda row: row["symbol"])
    return gaps


def build_readiness(
    *,
    formal_universe: list[FormalUniverseSymbol],
    usable_by_symbol: dict[str, dict[str, str]],
    invalid_rows: list[dict[str, str]],
    gap_rows: list[dict[str, str]],
    theme: str | None = None,
) -> dict[str, Any]:
    formal_count = len(formal_universe)
    row_count = len(usable_by_symbol)
    coverage_ratio = row_count / formal_count if formal_count else 0.0
    confidence_counts = {level: 0 for level in VALID_CONFIDENCE}
    for row in usable_by_symbol.values():
        confidence_counts[row["confidence"]] += 1

    if row_count == 0:
        source_mode = "current_static_map_blocked"
    elif row_count == formal_count:
        source_mode = "date_aware"
    else:
        source_mode = "date_aware_partial"

    blocking_issues: list[str] = []
    if source_mode == "current_static_map_blocked":
        blocking_issues.append("no_usable_date_aware_theme_membership_rows")
    if gap_rows:
        blocking_issues.append("theme_membership_gap_report_not_empty")
    if invalid_rows:
        blocking_issues.append("invalid_membership_rows_excluded")

    return {
        "ready": source_mode in {"date_aware", "date_aware_partial"},
        "theme": theme or "",
        "source_mode": source_mode,
        "target_symbol_count": formal_count,
        "formal_universe_symbol_count": formal_count,
        "date_aware_row_count": row_count,
        "coverage_ratio": round(coverage_ratio, 8),
        "high_confidence_count": confidence_counts["high"],
        "medium_confidence_count": confidence_counts["medium"],
        "low_confidence_count": confidence_counts["low"],
        "static_only_count": len(gap_rows),
        "invalid_row_count": len(invalid_rows),
        "blocking_issues": blocking_issues,
        "source_notes": [
            "Rows sourced only from the current static theme_map.csv are not counted as date-aware evidence.",
            "A usable row must include effective_start, source_date, non-static source_type, source_url, and high/medium/low confidence.",
            "current_static_map_blocked means formal replay must remain research-only for theme membership until dated evidence is added.",
        ],
    }


def ensure_membership_file(path: str | Path) -> Path:
    output = Path(path)
    if not output.exists():
        _write_rows(output, MEMBERSHIP_FIELDS, [])
    return output


def _read_membership_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        missing = [field for field in MEMBERSHIP_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"membership file missing required columns: {', '.join(missing)}")
        return [{field: str(row.get(field, "")).strip() for field in MEMBERSHIP_FIELDS} for row in reader]


def _missing_required_fields(row: dict[str, str]) -> list[str]:
    required = ["symbol", "name", "theme", "effective_start", "source_date", "source_type", "source_url", "confidence"]
    return [field for field in required if not row.get(field, "").strip()]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"invalid_date:{value}") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
