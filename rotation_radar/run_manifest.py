from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def write_run_manifest(path: str | Path, manifest: dict) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_daily_run_manifest(
    *,
    report_date: str,
    quote_date: str,
    quote_time: str,
    html_output: str | Path,
    market_quotes_path: str | Path,
    sector_metrics_path: str | Path,
    stock_metrics_path: str | Path,
    formal_candidates_path: str | Path,
    price_history_path: str | Path,
    depth_refresh_status: str,
    price_refresh_status: str,
    candidate_symbol_count: int,
    warnings: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict:
    timestamp = generated_at or datetime.now(TAIPEI_TZ)
    return {
        "generated_at": timestamp.astimezone(TAIPEI_TZ).isoformat(timespec="seconds"),
        "report_date": report_date,
        "quote_date": quote_date,
        "quote_time": quote_time,
        "outputs": {
            "html": str(html_output),
            "market_quotes": str(market_quotes_path),
            "sector_metrics": str(sector_metrics_path),
            "stock_metrics": str(stock_metrics_path),
            "formal_candidates": str(formal_candidates_path),
            "price_history": str(price_history_path),
        },
        "refresh_status": {
            "depth": depth_refresh_status,
            "price": price_refresh_status,
            "candidate_symbol_count": candidate_symbol_count,
        },
        "warnings": warnings or [],
    }
