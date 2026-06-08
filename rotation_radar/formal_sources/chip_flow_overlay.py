from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TARGET_UNIVERSE = [
    ("0050", "0050.TW", "元大台灣50"),
    ("00631L", "00631L.TW", "元大台灣50正2"),
    ("2330", "2330.TW", "台積電"),
    ("2454", "2454.TW", "聯發科"),
    ("2308", "2308.TW", "台達電"),
    ("2317", "2317.TW", "鴻海"),
    ("2382", "2382.TW", "廣達"),
    ("3231", "3231.TW", "緯創"),
    ("6669", "6669.TW", "緯穎"),
]

INSTITUTIONAL_FIELDS = [
    "date",
    "symbol",
    "ticker",
    "name",
    "foreign_net_buy_shares",
    "foreign_net_buy_twd",
    "investment_trust_net_buy_shares",
    "investment_trust_net_buy_twd",
    "dealer_net_buy_shares",
    "dealer_net_buy_twd",
    "total_institutional_net_buy_twd",
    "foreign_consecutive_buy_days",
    "foreign_consecutive_sell_days",
    "trust_consecutive_buy_days",
    "trust_consecutive_sell_days",
    "data_source",
    "source_url",
    "data_quality_status",
]

MARGIN_FIELDS = [
    "date",
    "symbol",
    "margin_balance_shares",
    "margin_change_shares",
    "short_balance_shares",
    "short_change_shares",
    "borrowed_sell_balance_shares",
    "borrowed_sell_change_shares",
    "margin_utilization_signal",
    "short_lending_pressure_signal",
    "data_source",
    "source_url",
    "data_quality_status",
]

DAY_TRADING_FIELDS = [
    "date",
    "symbol",
    "day_trade_volume",
    "day_trade_value_twd",
    "day_trade_volume_ratio",
    "day_trade_value_ratio",
    "data_source",
    "source_url",
    "data_quality_status",
]

SECTOR_PEER_FIELDS = [
    "date",
    "theme",
    "symbol",
    "ticker",
    "name",
    "official_turnover_twd",
    "turnover_share_in_theme",
    "turnover_share_change_5d",
    "turnover_share_change_20d",
    "relative_price_momentum_20d",
    "relative_price_momentum_60d",
    "theme_rank_by_turnover",
    "stock_rank_in_theme_by_turnover",
    "stock_rank_in_theme_by_score",
    "fundamental_pass",
    "data_quality_status",
]

FEATURE_FIELDS = [
    "date",
    "symbol",
    "ticker",
    "name",
    "foreign_flow_score",
    "trust_flow_score",
    "dealer_flow_score",
    "institutional_flow_score",
    "margin_overheat_score",
    "short_lending_risk_score",
    "day_trade_heat_score",
    "sector_rotation_in_score",
    "sector_rotation_out_score",
    "chip_risk_score",
    "chip_support_score",
    "overheat_warning",
    "distribution_warning",
    "rotation_out_warning",
    "data_quality_status",
]

GAP_FIELDS = [
    "gap_type",
    "symbol",
    "ticker",
    "name",
    "field_group",
    "missing_fields",
    "required_source",
    "current_status",
    "partial_fallback",
    "blocking",
    "checked_at",
]

REQUIRED_READINESS_FIELDS = [
    "ready",
    "source_mode",
    "start_date",
    "end_date",
    "symbol_count",
    "trading_day_count",
    "institutional_flow_coverage_ratio",
    "margin_short_coverage_ratio",
    "day_trade_coverage_ratio",
    "sector_peer_flow_coverage_ratio",
    "feature_score_ready",
    "future_data_violation_count",
    "missing_symbol_date_count",
    "blocking_issues",
    "warnings",
]


def build_chip_flow_overlay_package(
    *,
    output_dir: str | Path,
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
    trading_day_count: int = 507,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = _package_paths(output)

    _write_rows(paths["institutional"], INSTITUTIONAL_FIELDS, [])
    _write_rows(paths["margin"], MARGIN_FIELDS, [])
    _write_rows(paths["day_trading"], DAY_TRADING_FIELDS, [])
    _write_rows(paths["sector_peer"], SECTOR_PEER_FIELDS, [])
    _write_rows(paths["features"], FEATURE_FIELDS, [])

    checked_at = _utc_now_iso()
    gap_rows: list[dict[str, str]] = []
    for symbol, ticker, name in TARGET_UNIVERSE:
        gap_rows.extend(
            [
                _gap_row(
                    "institutional_flows_daily",
                    symbol,
                    ticker,
                    name,
                    "institutional_flow",
                    "foreign/investment_trust/dealer daily net buy shares and TWD",
                    "TWSE/TPEX daily institutional trading by stock with date and source URL",
                    "not_ingested",
                    "No formal fallback; existing report foreign_5d/trust_5d snapshots are derived and insufficient for raw overlay.",
                    "yes",
                    checked_at,
                ),
                _gap_row(
                    "margin_short_lending_daily",
                    symbol,
                    ticker,
                    name,
                    "margin_short_lending",
                    "margin, short, borrowed sell daily balances and changes",
                    "TWSE/TPEX margin/short/lending daily stock-level source with date and source URL",
                    "not_ingested",
                    "No formal fallback; existing margin_change_5d snapshots are derived and insufficient for raw overlay.",
                    "yes",
                    checked_at,
                ),
                _gap_row(
                    "day_trading_daily",
                    symbol,
                    ticker,
                    name,
                    "day_trading",
                    "day trade volume/value and ratios",
                    "TWSE/TPEX day-trading daily stock-level source with date and source URL",
                    "not_ingested",
                    "Can omit ETF rows if exchange source lacks ETF-equivalent data, but must be explicit before overlay_ready.",
                    "yes",
                    checked_at,
                ),
            ]
        )
    gap_rows.append(
        _gap_row(
            "sector_peer_flow_daily",
            "",
            "",
            "9-stock pool",
            "sector_peer_flow",
            "theme peer turnover share changes and relative momentum",
            "official turnover plus stable peer/theme mapping for the 9-stock pool",
            "not_generated",
            "Can be added after raw chip-flow sources are ingested; not enough for overlay_ready by itself.",
            "yes",
            checked_at,
        )
    )
    gap_rows.append(
        _gap_row(
            "chip_flow_overlay_features",
            "",
            "",
            "9-stock pool",
            "feature_scores",
            "all chip-flow score fields",
            "raw institutional, margin/short/lending, day-trading, and sector peer flow tables",
            "not_generated",
            "feature_score_ready=false; BACKTEST_LAB may only use this package as a source gap audit.",
            "yes",
            checked_at,
        )
    )
    _write_rows(paths["gap"], GAP_FIELDS, gap_rows)

    readiness = {
        "ready": False,
        "source_mode": "overlay_blocked",
        "start_date": start_date,
        "end_date": end_date,
        "symbol_count": len(TARGET_UNIVERSE),
        "trading_day_count": trading_day_count,
        "institutional_flow_coverage_ratio": 0.0,
        "margin_short_coverage_ratio": 0.0,
        "day_trade_coverage_ratio": 0.0,
        "sector_peer_flow_coverage_ratio": 0.0,
        "feature_score_ready": False,
        "future_data_violation_count": 0,
        "missing_symbol_date_count": len(TARGET_UNIVERSE) * trading_day_count,
        "blocking_issues": [
            "institutional_flows_daily_not_ingested",
            "margin_short_lending_daily_not_ingested",
            "day_trading_daily_not_ingested",
            "feature_scores_not_ready",
        ],
        "warnings": [
            "Existing RADAR report-level foreign_5d, trust_5d, and margin_change_5d are derived snapshot fields and are not used as raw formal overlay sources.",
            "ETF rows may require separate handling because exchange chip-flow datasets may not expose ETF-equivalent fields in the same format.",
            "This package is a formal gap audit for BACKTEST_LAB shadow overlay v1, not an overlay-ready feature table.",
        ],
    }
    _write_json(paths["readiness"], readiness)

    manifest = {
        "created_at": checked_at,
        "package": "chip_flow_overlay_2021_2023",
        "status": "overlay_blocked",
        "target_universe": [
            {"symbol": symbol, "ticker": ticker, "name": name}
            for symbol, ticker, name in TARGET_UNIVERSE
        ],
        "outputs": {key: str(path) for key, path in paths.items()},
        "notes": [
            "Empty raw CSVs are intentional because formal historical chip-flow sources are not ingested yet.",
            "Do not use derived daily report snapshot fields as formal raw chip-flow evidence.",
        ],
    }
    _write_json(paths["manifest"], manifest)
    return readiness


def validate_chip_flow_overlay_package(*, output_dir: str | Path) -> dict[str, Any]:
    paths = _package_paths(Path(output_dir))
    missing_files = [str(path) for path in paths.values() if not path.exists()]
    if missing_files:
        raise FileNotFoundError(f"chip-flow overlay package missing files: {', '.join(missing_files)}")

    _assert_header(paths["institutional"], INSTITUTIONAL_FIELDS)
    _assert_header(paths["margin"], MARGIN_FIELDS)
    _assert_header(paths["day_trading"], DAY_TRADING_FIELDS)
    _assert_header(paths["sector_peer"], SECTOR_PEER_FIELDS)
    _assert_header(paths["features"], FEATURE_FIELDS)
    _assert_header(paths["gap"], GAP_FIELDS)

    readiness = _read_json(paths["readiness"])
    missing_fields = [field for field in REQUIRED_READINESS_FIELDS if field not in readiness]
    if missing_fields:
        raise ValueError(f"readiness missing required fields: {', '.join(missing_fields)}")
    if readiness["source_mode"] not in {"overlay_ready", "overlay_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "overlay_ready":
        raise ValueError("ready=true requires source_mode=overlay_ready")
    if not readiness["ready"] and readiness["source_mode"] != "overlay_blocked":
        raise ValueError("ready=false requires source_mode=overlay_blocked")
    if readiness["future_data_violation_count"] != 0:
        raise ValueError("future_data_violation_count must be zero")
    if not readiness["ready"] and not readiness["blocking_issues"]:
        raise ValueError("overlay_blocked requires blocking_issues")
    return readiness


def _package_paths(output: Path) -> dict[str, Path]:
    return {
        "institutional": output / "institutional_flows_daily_2021_2023.csv",
        "margin": output / "margin_short_lending_daily_2021_2023.csv",
        "day_trading": output / "day_trading_daily_2021_2023.csv",
        "sector_peer": output / "sector_peer_flow_daily_2021_2023.csv",
        "features": output / "chip_flow_overlay_features_2021_2023.csv",
        "readiness": output / "chip_flow_overlay_readiness.json",
        "gap": output / "chip_flow_overlay_gap_report.csv",
        "manifest": output / "chip_flow_overlay_manifest.json",
    }


def _gap_row(
    gap_type: str,
    symbol: str,
    ticker: str,
    name: str,
    field_group: str,
    missing_fields: str,
    required_source: str,
    current_status: str,
    partial_fallback: str,
    blocking: str,
    checked_at: str,
) -> dict[str, str]:
    return {
        "gap_type": gap_type,
        "symbol": symbol,
        "ticker": ticker,
        "name": name,
        "field_group": field_group,
        "missing_fields": missing_fields,
        "required_source": required_source,
        "current_status": current_status,
        "partial_fallback": partial_fallback,
        "blocking": blocking,
        "checked_at": checked_at,
    }


def _assert_header(path: Path, expected_fields: list[str]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if header != expected_fields:
        raise ValueError(f"{path} header mismatch")


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
