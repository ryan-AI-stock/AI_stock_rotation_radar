from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

from r1.config import R1Config
from rotation_radar.daily_risk_features import fetch_chip_family, fetch_price


def materialize_daily_sources(
    *, start: date, end: date, config_path: str | Path, output_root: str | Path,
    retry_incomplete: bool = False, max_attempts: int = 3, retry_wait_seconds: float = 15.0,
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
            payload = {}
        attempts = max(1, max_attempts if retry_incomplete else 1)
        for attempt in range(attempts):
            price_complete = _price_ready(payload, wanted)
            price_closed = _price_market_closed(payload)
            chip_complete = _chip_ready(payload)
            if payload and (not retry_incomplete or ((price_complete or price_closed) and chip_complete)):
                break

            if not price_complete and not price_closed:
                price_rows, price_sources = fetch_price(current, wanted)
            else:
                price_rows = payload.get("price_rows", [])
                price_sources = _family_sources(payload, "official_raw_execution_ohlcv")
            if not chip_complete:
                chip_rows, chip_sources = fetch_chip_family(current, wanted)
            else:
                chip_rows = payload.get("chip_rows", [])
                chip_sources = [row for row in payload.get("sources", [])
                                if row.get("family") != "official_raw_execution_ohlcv"]
            payload = {
                "date": current.isoformat(), "price_rows": price_rows, "chip_rows": chip_rows,
                "sources": price_sources + chip_sources,
                "future_data_violation_count": 0,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if ((not _price_ready(payload, wanted) and not _price_market_closed(payload))
                    or not _chip_ready(payload)) and attempt + 1 < attempts and retry_wait_seconds > 0:
                time.sleep(retry_wait_seconds)
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


def _chip_ready(payload: dict) -> bool:
    wanted = {("institutional", market) for market in ("TWSE", "TPEx")} | {
        ("margin_short", market) for market in ("TWSE", "TPEx")
    }
    states = {(row.get("family"), row.get("market")): row.get("status") for row in payload.get("sources", [])}
    return all(states.get(key) == "accepted" for key in wanted)


def _price_ready(payload: dict, wanted: set[str]) -> bool:
    return {str(row.get("ticker")) for row in payload.get("price_rows", [])} == wanted


def _price_market_closed(payload: dict) -> bool:
    states = {row.get("market"): row.get("status") for row in payload.get("sources", [])
              if row.get("family") == "official_raw_execution_ohlcv"}
    return not payload.get("price_rows") and all(states.get(market) == "no_rows" for market in ("TWSE", "TPEx"))


def _family_sources(payload: dict, family: str) -> list[dict]:
    return [row for row in payload.get("sources", []) if row.get("family") == family]


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize checkpointed official R1 daily sources.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output-root", default="data/r1/daily_sources")
    parser.add_argument("--retry-incomplete", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-wait-seconds", type=float, default=15.0)
    args = parser.parse_args()
    result = materialize_daily_sources(
        start=date.fromisoformat(args.start), end=date.fromisoformat(args.end),
        config_path=args.config, output_root=args.output_root, retry_incomplete=args.retry_incomplete,
        max_attempts=args.max_attempts, retry_wait_seconds=args.retry_wait_seconds,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result["blocked"]:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
