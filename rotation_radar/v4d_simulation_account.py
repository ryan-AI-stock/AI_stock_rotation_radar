from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path


INITIAL_CAPITAL = 7_000_000.0
BUY_RATE = 0.000855 + 0.001
SELL_RATE = 0.000855 + 0.003 + 0.001
WITHDRAWAL_AMOUNT = 75_000.0
WITHDRAWAL_START_DATE = date(2026, 9, 9)

DEFAULT_STATE = {
    "schema_version": 1,
    "account_type": "formal_v4d_forward_simulation",
    "initial_capital": INITIAL_CAPITAL,
    "cash": INITIAL_CAPITAL,
    "transactions": [],
    "position": None,
    "pending_entry": None,
    "withdrawal_schedule": {
        "amount": WITHDRAWAL_AMOUNT,
        "start_date": WITHDRAWAL_START_DATE.isoformat(),
        "processed_scheduled_dates": [],
    },
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
    schedule = state.setdefault("withdrawal_schedule", {})
    schedule.setdefault("amount", WITHDRAWAL_AMOUNT)
    schedule.setdefault("start_date", WITHDRAWAL_START_DATE.isoformat())
    schedule.setdefault("processed_scheduled_dates", [])
    return state


def second_wednesday(year: int, month: int) -> date:
    """Return the Wednesday preceding the monthly third-Wednesday settlement."""
    first = date(year, month, 1)
    first_wednesday_offset = (2 - first.weekday()) % 7
    return date(year, month, 1 + first_wednesday_offset + 7)


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _due_dates_through(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    dates: list[date] = []
    while cursor <= end:
        due = second_wednesday(cursor.year, cursor.month)
        if start <= due <= end:
            dates.append(due)
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return dates


def next_withdrawal_date(state: dict, as_of_date: str | date) -> date | None:
    """Find the next unprocessed second-Wednesday withdrawal date."""
    schedule = state.get("withdrawal_schedule") or {}
    start = _as_date(schedule.get("start_date", WITHDRAWAL_START_DATE.isoformat()))
    as_of = _as_date(as_of_date)
    processed = set(schedule.get("processed_scheduled_dates") or [])
    if as_of < start:
        return start
    for due in _due_dates_through(start, date(as_of.year + 1, 12, 31)):
        if due.isoformat() not in processed and due >= start:
            return due
    return None


def withdrawal_preview(state: dict, *, as_of_date: str | date, close: float | None) -> dict:
    """Build the next withdrawal estimate without mutating account state."""
    due = next_withdrawal_date(state, as_of_date)
    amount = float((state.get("withdrawal_schedule") or {}).get("amount", WITHDRAWAL_AMOUNT))
    position = state.get("position") or {}
    shares = int(position.get("shares") or 0)
    price = float(close) if close is not None else None
    planned_shares = 0
    gross = 0.0
    fee_tax = 0.0
    net = 0.0
    mode = "cash_withdrawal" if not position else "planned_stock_sale"
    if position and price and price > 0:
        planned_shares = min(shares, max(1, round(amount / price)))
        gross = planned_shares * price
        fee_tax = gross * SELL_RATE
        net = gross - fee_tax
    elif not position:
        net = min(float(state.get("cash") or 0), amount)
    return {
        "next_scheduled_date": due.isoformat() if due else None,
        "estimated_execution_date": due.isoformat() if due else None,
        "status": mode if due else "not_scheduled",
        "planned_shares": planned_shares,
        "estimated_gross_amount": gross,
        "estimated_fee_tax": fee_tax,
        "estimated_net_withdrawal": net,
        "target_amount": amount,
    }


def execute_due_withdrawal(
    state: dict,
    *,
    trade_date: str | date,
    close: float | None,
) -> dict | None:
    """Execute one due monthly withdrawal on an actual official trading-day mark.

    The caller supplies an official close only when a position is held. A report
    that is not produced on a market-closed day cannot create a transaction; a
    later trading-day call records the original scheduled date as deferred.
    """
    trade_day = _as_date(trade_date)
    schedule = state.setdefault("withdrawal_schedule", {})
    start = _as_date(schedule.setdefault("start_date", WITHDRAWAL_START_DATE.isoformat()))
    amount = float(schedule.setdefault("amount", WITHDRAWAL_AMOUNT))
    processed = schedule.setdefault("processed_scheduled_dates", [])
    due_dates = [due for due in _due_dates_through(start, trade_day) if due.isoformat() not in processed]
    if not due_dates:
        return None
    due = due_dates[0]
    deferred = due != trade_day
    position = state.get("position")
    event = {
        "trade_date": trade_day.isoformat(),
        "scheduled_withdrawal_date": due.isoformat(),
        "withdrawal_deferred_from_closed_date": deferred,
        "target_withdrawal_amount": amount,
    }
    if position:
        if close is None or float(close) <= 0:
            raise ValueError("Official held-close is required to execute a stock withdrawal.")
        original_shares = int(position["shares"])
        shares = min(original_shares, max(1, round(amount / float(close))))
        gross = shares * float(close)
        cost = gross * SELL_RATE
        proceeds = gross - cost
        original_cost = float(position["position_cost"])
        allocated_cost = original_cost * shares / original_shares
        position["shares"] = original_shares - shares
        position["position_cost"] = original_cost - allocated_cost
        position["buy_fee"] = float(position.get("buy_fee", 0.0)) * position["shares"] / original_shares
        state["cash"] = float(state["cash"]) + proceeds - proceeds
        event.update(
            {
                "action": "monthly_withdrawal_stock_sale",
                "ticker": position["ticker"],
                "name": position["name"],
                "execution_price": float(close),
                "shares": shares,
                "gross_amount": gross,
                "transaction_cost": cost,
                "net_cash_flow": 0.0,
                "withdrawal_amount": proceeds,
                "realized_pnl": proceeds - allocated_cost,
                "realized_return_pct": (proceeds - allocated_cost) / allocated_cost * 100 if allocated_cost else None,
                "cash_after": float(state["cash"]),
                "reason": "每月提領：第二個星期三，整股賣出後提領淨額",
            }
        )
        if position["shares"] == 0:
            state["position"] = None
    else:
        cash = float(state.get("cash") or 0)
        withdrawn = min(cash, amount)
        state["cash"] = cash - withdrawn
        event.update(
            {
                "action": "monthly_withdrawal_cash" if withdrawn else "monthly_withdrawal_unfunded_cash",
                "shares": 0,
                "gross_amount": withdrawn,
                "transaction_cost": 0.0,
                "withdrawal_amount": withdrawn,
                "net_cash_flow": -withdrawn,
                "cash_after": float(state["cash"]),
                "reason": "每月提領：空手時由現金提領" if withdrawn else "每月提領：空手且現金不足",
            }
        )
    state["transactions"].append(event)
    processed.append(due.isoformat())
    return event


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
