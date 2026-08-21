from __future__ import annotations

import json
import math
from pathlib import Path


INITIAL_CAPITAL = 7_000_000.0
BUY_RATE = 0.000855 + 0.001
SELL_RATE = 0.000855 + 0.003 + 0.001

DEFAULT_STATE = {
    "schema_version": 1,
    "account_type": "formal_v4d_forward_simulation",
    "initial_capital": INITIAL_CAPITAL,
    "cash": INITIAL_CAPITAL,
    "transactions": [],
    "position": None,
    "pending_entry": None,
}


def load_simulation_state(path: Path) -> dict:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("schema_version", 1)
    state.setdefault("account_type", "formal_v4d_forward_simulation")
    state.setdefault("initial_capital", INITIAL_CAPITAL)
    state.setdefault("cash", float(state["initial_capital"]))
    state.setdefault("transactions", [])
    state.setdefault("position", None)
    state.setdefault("pending_entry", None)
    return state


def buy_position(
    state: dict,
    *,
    trade_date: str,
    ticker: str,
    name: str,
    price: float,
    signal_date: str,
    signal_close: float,
    reason: str,
) -> dict:
    if state.get("position") is not None:
        raise ValueError("Simulation account already has a position.")
    cash = float(state["cash"])
    shares = math.floor(cash / (float(price) * (1 + BUY_RATE)))
    if shares <= 0:
        state["pending_entry"] = None
        state["transactions"].append(
            {
                "trade_date": trade_date,
                "action": "buy_blocked_insufficient_cash",
                "ticker": str(ticker).zfill(4),
                "name": name,
                "execution_price": float(price),
                "shares": 0,
                "cash_after": cash,
                "reason": reason,
            }
        )
        return state
    gross = shares * float(price)
    cost = gross * BUY_RATE
    total = gross + cost
    state["cash"] = cash - total
    state["position"] = {
        "ticker": str(ticker).zfill(4),
        "name": name,
        "signal_date": signal_date,
        "signal_close": float(signal_close),
        "execution_date": trade_date,
        "entry_close": float(price),
        "shares": int(shares),
        "buy_fee": float(cost),
        "position_cost": float(total),
        "status": "holding",
        "daily_marks": {},
        "pending_exit": None,
        "simulation_position": True,
    }
    state["pending_entry"] = None
    state["transactions"].append(
        {
            "trade_date": trade_date,
            "action": "buy",
            "ticker": str(ticker).zfill(4),
            "name": name,
            "execution_price": float(price),
            "shares": int(shares),
            "gross_amount": float(gross),
            "transaction_cost": float(cost),
            "net_cash_flow": float(-total),
            "cash_after": float(state["cash"]),
            "signal_date": signal_date,
            "signal_close": float(signal_close),
            "reason": reason,
        }
    )
    return state


def sell_position(
    state: dict,
    *,
    trade_date: str,
    price: float,
    reason: str,
) -> dict:
    position = state.get("position")
    if not position:
        raise ValueError("Simulation account has no position to sell.")
    shares = int(position["shares"])
    gross = shares * float(price)
    cost = gross * SELL_RATE
    proceeds = gross - cost
    realized_pnl = proceeds - float(position["position_cost"])
    realized_return = realized_pnl / float(position["position_cost"]) * 100
    state["cash"] = float(state["cash"]) + proceeds
    state["transactions"].append(
        {
            "trade_date": trade_date,
            "action": "sell",
            "ticker": position["ticker"],
            "name": position["name"],
            "execution_price": float(price),
            "shares": shares,
            "gross_amount": float(gross),
            "transaction_cost": float(cost),
            "net_cash_flow": float(proceeds),
            "cash_after": float(state["cash"]),
            "realized_pnl": float(realized_pnl),
            "realized_return_pct": float(realized_return),
            "reason": reason,
        }
    )
    state["position"] = None
    return state
