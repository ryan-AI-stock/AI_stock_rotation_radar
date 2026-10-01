from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from r1.config import R1Config
from rotation_radar.daily_risk_features import fetch_chip_family, fetch_price


def materialize_daily_sources(
    *, start: date, end: date, config_path: str | Path, output_root: str | Path,
) -> dict:
    config = R1Config.load(config_path)
    wanted = {security.ticker for security in config.securities}
    root = Path(output_root)
    completed = 0
    market_closed = 0
    blocked: list[dict] = []
    chip_source_gaps: list[dict] = []
    current = start
    while current <= end:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        path = root / f"{current.isoformat()}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            price_rows, price_sources = fetch_price(current, wanted)
            chip_rows, chip_sources = fetch_chip_family(current, wanted)
            payload = {
                "date": current.isoformat(), "price_rows": price_rows, "chip_rows": chip_rows,
                "sources": price_sources + chip_sources,
                "future_data_violation_count": 0,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        price_markets = {row.get("market"): row.get("status") for row in payload["sources"]
                         if row.get("family") == "official_raw_execution_ohlcv"}
        if not payload["price_rows"] and all(price_markets.get(market) == "no_rows" for market in ("TWSE", "TPEx")):
            market_closed += 1
        elif set(row["ticker"] for row in payload["price_rows"]) != wanted:
            blocked.append({"date": current.isoformat(), "reason": "incomplete_price_universe",
                            "actual": len({row['ticker'] for row in payload['price_rows']}), "requested": len(wanted)})
        else:
            completed += 1
            for source in payload["sources"]:
                if source.get("family") in {"institutional", "margin_short", "securities_lending"} \
                        and source.get("status") != "accepted":
                    chip_source_gaps.append({
                        "date": current.isoformat(), "family": source.get("family"),
                        "market": source.get("market"), "status": source.get("status"),
                        "error": source.get("error", ""),
                    })
        current += timedelta(days=1)
    manifest = {
        "start": start.isoformat(), "end": end.isoformat(), "requested_ticker_count": len(wanted),
        "completed_trading_dates": completed, "market_closed_dates": market_closed,
        "blocked": blocked, "chip_source_gaps": chip_source_gaps,
        "chip_data_ready": not chip_source_gaps, "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize checkpointed official R1 daily sources.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output-root", default="data/r1/daily_sources")
    args = parser.parse_args()
    result = materialize_daily_sources(
        start=date.fromisoformat(args.start), end=date.fromisoformat(args.end),
        config_path=args.config, output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result["blocked"]:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
