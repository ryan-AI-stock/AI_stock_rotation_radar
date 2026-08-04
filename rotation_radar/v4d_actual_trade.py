from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_STATE = {
    "schema_version": 1,
    "actual_trades": [],
    "position": None,
}

DEFAULT_PRICE_SOURCE = Path(
    "data/current_base_cycle_source_cache/official_recent_full_market.csv.gz"
)


def resolve_trade_metadata(
    price_source: Path,
    *,
    ticker: str,
    trade_date: str,
) -> dict:
    ticker = str(ticker).zfill(4)
    prices = pd.read_csv(price_source, dtype={"ticker": str})
    prices["ticker"] = prices["ticker"].str.zfill(4)
    prices["date"] = pd.to_datetime(prices["date"])
    prior = prices[
        prices["ticker"].eq(ticker)
        & prices["date"].lt(pd.Timestamp(trade_date))
    ].sort_values("date")
    if prior.empty:
        raise ValueError(
            f"No prior official price/name metadata for {ticker} before {trade_date}."
        )
    row = prior.iloc[-1]
    return {
        "name": str(row["name"]),
        "signal_date": row["date"].date().isoformat(),
        "signal_close": float(row["close"]),
    }


def load_actual_trade_state(path: Path) -> dict:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("schema_version", 1)
    state.setdefault("actual_trades", [])
    state.setdefault("position", None)
    return state


def record_actual_trade(
    state: dict,
    *,
    action: str,
    trade_date: str,
    ticker: str,
    name: str,
    average_price: float,
    shares: int,
    fee: float = 0.0,
    signal_date: str = "",
    signal_close: float | None = None,
    note: str = "",
) -> dict:
    if action not in {"legacy_sell", "v4d_buy", "v4d_sell"}:
        raise ValueError(f"Unsupported actual trade action: {action}")
    if average_price <= 0 or shares <= 0 or fee < 0:
        raise ValueError("Actual trade requires positive price/shares and non-negative fee.")
    ticker = str(ticker).zfill(4)
    trade = {
        "trade_date": trade_date,
        "action": action,
        "ticker": ticker,
        "name": name,
        "average_price": float(average_price),
        "shares": int(shares),
        "fee": float(fee),
        "price_cost_basis": "broker_average_price_includes_transaction_cost",
        "signal_date": signal_date,
        "signal_close": signal_close,
        "note": note,
        "source": "user_actual_trade_workflow",
    }
    state = json.loads(json.dumps(state))
    state.setdefault("actual_trades", []).append(trade)
    if action == "v4d_buy":
        if state.get("position"):
            raise ValueError("An active V4-D position already exists.")
        if not signal_date or signal_close is None or float(signal_close) <= 0:
            raise ValueError("V4-D buy requires signal date and positive signal close.")
        state["position"] = {
            "ticker": ticker,
            "name": name,
            "signal_date": signal_date,
            "signal_close": float(signal_close),
            "execution_date": trade_date,
            "entry_close": float(average_price),
            "shares": int(shares),
            "buy_fee": float(fee),
            "status": "holding",
            "daily_marks": {},
            "pending_exit": None,
            "actual_position_confirmed": True,
        }
    elif action == "v4d_sell":
        position = state.get("position")
        if not position or str(position.get("ticker")).zfill(4) != ticker:
            raise ValueError("V4-D sell does not match the active position.")
        state["position"] = None
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an actual V4-D trade fill.")
    parser.add_argument("--state", default="data/formal_v4d_actual_trade_state.json")
    parser.add_argument("--action", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--average-price", required=True, type=float)
    parser.add_argument("--shares", required=True, type=int)
    parser.add_argument("--price-source", default=str(DEFAULT_PRICE_SOURCE))
    args = parser.parse_args()
    path = Path(args.state)
    metadata = resolve_trade_metadata(
        Path(args.price_source), ticker=args.ticker, trade_date=args.trade_date
    )
    signal_date = metadata["signal_date"] if args.action == "v4d_buy" else ""
    signal_close = metadata["signal_close"] if args.action == "v4d_buy" else None
    state = record_actual_trade(
        load_actual_trade_state(path),
        action=args.action,
        trade_date=args.trade_date,
        ticker=args.ticker,
        name=metadata["name"],
        average_price=args.average_price,
        shares=args.shares,
        fee=0.0,
        signal_date=signal_date,
        signal_close=signal_close,
        note="券商成交均價已反映交易成本",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
