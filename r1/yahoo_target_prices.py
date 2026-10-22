from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import yfinance as yf

from r1.config import R1Config


def _fetch_targets_with_retry(symbol: str, *, attempts: int = 3, delay_seconds: float = 2):
    """Retry acquisition errors only; valid missing fields are handled by parse_targets."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return yf.Ticker(symbol).get_analyst_price_targets()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


def parse_targets(payload: dict[str, Any] | None, *, ticker: str, symbol: str,
                  retrieved_at: str) -> dict[str, Any]:
    """Preserve Yahoo's anonymous aggregate without calling it named consensus."""
    payload = payload or {}
    values: dict[str, float] = {}
    for key in ("current", "mean", "median"):
        value = payload.get(key)
        if value is None or float(value) <= 0:
            raise ValueError(f"{key}_target_missing")
        values[key] = float(value)
    optional: dict[str, float | None] = {}
    for key in ("low", "high"):
        value = payload.get(key)
        optional[key] = float(value) if value is not None and float(value) > 0 else None
    complete_range = optional["low"] is not None and optional["high"] is not None
    return {
        "ticker": ticker, "symbol": symbol,
        "current_price": values["current"],
        "target_low": optional["low"], "target_mean": values["mean"],
        "target_median": values["median"], "target_high": optional["high"],
        "mean_upside": values["mean"] / values["current"] - 1,
        "median_upside": values["median"] / values["current"] - 1,
        "available_at": retrieved_at, "retrieved_at": retrieved_at,
        "source": "Yahoo Finance analyst price-target aggregate",
        "source_url": f"https://finance.yahoo.com/quote/{symbol}/analysis/",
        "status": "READY_AGGREGATE_ONLY" if complete_range else "READY_AGGREGATE_PARTIAL",
        "scoreable": False,
        "note": "匿名彙總；無法驗證各機構名稱，不取代R1具名三機構共識。"
                + ("" if complete_range else "最高／最低區間不完整。"),
    }


def acquire(*, config_path: str | Path, output_path: str | Path,
            checkpoint_path: str | Path, retrieved_at: str | None = None) -> dict[str, Any]:
    retrieved_at = retrieved_at or date.today().isoformat()
    config = R1Config.load(config_path)
    checkpoint = Path(checkpoint_path)
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if state.get("retrieved_at") != retrieved_at:
        state = {"retrieved_at": retrieved_at, "completed": {}, "failed": {}}
    allowed = {security.ticker: security.market for security in config.securities}
    state["completed"] = {k: v for k, v in state.get("completed", {}).items() if k in allowed}
    state["failed"] = {k: v for k, v in state.get("failed", {}).items() if k in allowed}
    for ticker, market in allowed.items():
        if ticker in state["completed"]:
            continue
        symbol = ticker + (".TWO" if market == "TPEx" else ".TW")
        try:
            state["completed"][ticker] = parse_targets(
                _fetch_targets_with_retry(symbol),
                ticker=ticker, symbol=symbol, retrieved_at=retrieved_at,
            )
            state["failed"].pop(ticker, None)
        except Exception as exc:
            state["failed"][ticker] = {"symbol": symbol, "error": f"{type(exc).__name__}:{exc}"}
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = sorted(state["completed"].values(), key=lambda row: row["ticker"])
    result = {
        "date": retrieved_at, "requested_ticker_count": len(allowed),
        "ready_aggregate_count": len(rows), "failed_ticker_count": len(state["failed"]),
        "scoreable_count": 0, "rows": rows, "failed": state["failed"],
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire non-scoreable Yahoo aggregate analyst targets.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output", default="data/r1/target_prices/yahoo_aggregate_latest.json")
    parser.add_argument("--checkpoint", default="data/r1/target_prices/yahoo_aggregate_checkpoint.json")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args()
    result = acquire(config_path=args.config, output_path=args.output,
                     checkpoint_path=args.checkpoint, retrieved_at=args.retrieved_at)
    print(json.dumps({k: v for k, v in result.items() if k not in {"rows", "failed"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
