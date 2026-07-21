from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .schedule_gate import fetch_official_market_session_state, fetch_twse_calendar, is_trading_day


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
MODE_ID = "0050_MA4_SLOPE7_ENTRY_MA10_SLOPE20_EXIT_CD7"
SIGNAL_TICKER = "0050"
EXECUTION_TICKER = "00631L"
COOLDOWN_TRADING_DAYS = 7
SESSION_SOURCE = "TWSE holiday calendar + TWSE/TPEx official after-trading session APIs"


def build_formal_signal_checkpoint(
    price_rows: list[dict[str, float | str]],
    *,
    report_date: str | date,
    state_path: str | Path,
    override_path: str | Path,
    checkpoint_path: str | Path,
    explicit_trade_override: dict[str, Any] | None = None,
    open_dates: set[date] | None = None,
    closed_dates: set[date] | None = None,
    session_status: str | None = None,
    session_status_by_date: dict[date, str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    report_day = _parse_date(report_date)
    timestamp = (generated_at or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    state_file = Path(state_path)
    override_file = Path(override_path)
    checkpoint_file = Path(checkpoint_path)

    state = _load_json(state_file, _empty_state())
    overrides = _load_json(override_file, {"actual_trades": []})
    trades = _merge_actual_trades(
        state.get("actual_trades", []),
        overrides.get("actual_trades", []),
        [explicit_trade_override] if explicit_trade_override else [],
    )
    position = _position_as_of(trades, report_day)
    latest_trade = _latest_trade_as_of(trades, report_day)

    calendar_source_ready = closed_dates is not None
    if open_dates is None or closed_dates is None:
        fetched_open, fetched_closed = fetch_twse_calendar()
        open_dates = fetched_open if open_dates is None else open_dates
        closed_dates = fetched_closed if closed_dates is None else closed_dates
        calendar_source_ready = fetched_closed is not None
    closed_dates = set(closed_dates or set())
    open_dates = set(open_dates or set())
    persisted_closed_dates = _state_closed_session_dates(state)
    closed_dates.update(persisted_closed_dates)

    observed_session_status = session_status or fetch_official_market_session_state(report_day)
    if observed_session_status == "closed":
        closed_dates.add(report_day)
    elif observed_session_status == "open":
        open_dates.add(report_day)

    price_session_dates = _price_session_dates(price_rows, report_day)
    derived_closed_dates, unresolved_session_dates = _reconcile_historical_sessions(
        latest_trade=latest_trade,
        report_day=report_day,
        price_session_dates=price_session_dates,
        open_dates=open_dates,
        closed_dates=closed_dates,
        session_status_by_date=session_status_by_date,
        report_session_status=observed_session_status,
    )
    calendar_ready = calendar_source_ready and not unresolved_session_dates

    metrics = _calculate_metrics(price_rows, report_day)
    signal = _classify_signal(metrics)
    model_execution_date = _next_trading_day(report_day, open_dates, closed_dates) if calendar_ready else None
    blocked_dates, next_tradable_date = _cooldown_dates(latest_trade, open_dates, closed_dates, calendar_ready)
    desired_action = _desired_action(signal, position["asset_type"])
    execution_is_blocked = model_execution_date in blocked_dates if model_execution_date else False
    model_action = _apply_execution_guards(
        desired_action,
        signal_status=metrics["status"],
        session_status=observed_session_status,
        calendar_ready=calendar_ready,
        execution_is_blocked=execution_is_blocked,
    )
    remaining_blocked_dates = [value for value in blocked_dates if value > report_day]

    checkpoint = {
        "schema_version": 2,
        "mode_id": MODE_ID,
        "mode_label": "MA4＋近7日上漲買入／MA10＋近20日下跌賣出／CD7",
        "signal_ticker": SIGNAL_TICKER,
        "execution_ticker": EXECUTION_TICKER,
        "report_date": report_day.isoformat(),
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "calculation_status": metrics["status"] if calendar_ready else "blocked_calendar_unavailable",
        "market_session_status": observed_session_status,
        "market_session_source": SESSION_SOURCE,
        "market_calendar_ready": calendar_ready,
        "derived_emergency_closed_dates": [value.isoformat() for value in sorted(derived_closed_dates)],
        "persisted_emergency_closed_dates": [value.isoformat() for value in sorted(persisted_closed_dates)],
        "unresolved_historical_session_dates": [value.isoformat() for value in sorted(unresolved_session_dates)],
        "historical_session_confirmation_status": "ready" if not unresolved_session_dates else "blocked_unknown_session",
        "close": metrics["close"],
        "ma4": metrics["ma4"],
        "ma10": metrics["ma10"],
        "close_6_trading_days_ago": metrics["close_6_trading_days_ago"],
        "close_19_trading_days_ago": metrics["close_19_trading_days_ago"],
        "slope_7d_observation_count": 7,
        "slope_20d_observation_count": 20,
        "slope_7d_value": metrics["slope_7d_value"],
        "slope_7d_pct": metrics["slope_7d_pct"],
        "slope_20d_value": metrics["slope_20d_value"],
        "slope_20d_pct": metrics["slope_20d_pct"],
        "entry_condition": metrics["entry_condition"],
        "exit_condition": metrics["exit_condition"],
        "today_signal": signal,
        "desired_next_day_action": desired_action,
        "model_next_day_execution_action": model_action,
        "model_next_day_execution_date": model_execution_date.isoformat() if model_execution_date else "",
        "model_next_day_execution_date_source": "official_trading_calendar_after_report_close",
        "actual_trade_date": latest_trade.get("trade_date", "") if latest_trade else "",
        "actual_trade_date_source": latest_trade.get("source", "") if latest_trade else "actual_trade_state_or_override_only",
        "actual_trade_action": latest_trade.get("action", "") if latest_trade else "",
        "actual_trade_average_price": latest_trade.get("average_price") if latest_trade else None,
        "actual_position": position,
        "cooldown_trading_days": COOLDOWN_TRADING_DAYS,
        "cooldown_start_trade_date": latest_trade.get("trade_date", "") if latest_trade else "",
        "blocked_trading_dates": [value.isoformat() for value in blocked_dates],
        "next_tradable_date": next_tradable_date.isoformat() if next_tradable_date else "",
        "remaining_blocked_trading_days": len(remaining_blocked_dates),
        "execution_blocked_by_cooldown": execution_is_blocked,
        "pending_signal": None,
        "signal_carry_forward_used": False,
        "average_price_used_for_model_signal": False,
        "future_data_violation_count": 0,
        "formal_model_changed": True,
        "trade_decision_changed": True,
        "active_in_trade_decision": True,
        "report_changed": True,
    }

    updated_state = _updated_state(state, trades, checkpoint, timestamp)
    _atomic_write_json(state_file, updated_state)
    _atomic_write_json(checkpoint_file, checkpoint)
    return checkpoint


def validate_formal_signal_checkpoint(checkpoint: dict[str, Any]) -> None:
    required = {
        "actual_trade_date",
        "actual_trade_date_source",
        "model_next_day_execution_date",
        "model_next_day_execution_date_source",
    }
    missing = sorted(required - checkpoint.keys())
    if missing:
        raise ValueError(f"Formal signal checkpoint missing date lineage fields: {missing}")
    if checkpoint["actual_trade_date_source"] not in {
        "actual_trade_state_or_override_only",
        "user_actual_trade_override",
        "workflow_dispatch_actual_trade_override",
    }:
        raise ValueError("actual_trade_date must come from actual trade state/override")
    if checkpoint["model_next_day_execution_date_source"] != "official_trading_calendar_after_report_close":
        raise ValueError("model_next_day_execution_date must come from the official trading calendar")


def _calculate_metrics(price_rows: list[dict[str, float | str]], report_day: date) -> dict[str, Any]:
    rows_by_date: dict[date, float] = {}
    for row in price_rows:
        try:
            row_date = _parse_date(str(row.get("date", "")))
            close = float(row.get("close", 0) or 0)
        except (TypeError, ValueError):
            continue
        if row_date <= report_day and close > 0:
            rows_by_date[row_date] = close
    ordered = sorted(rows_by_date.items())
    empty = {
        "status": "blocked_insufficient_0050_history",
        "close": None,
        "ma4": None,
        "ma10": None,
        "close_6_trading_days_ago": None,
        "close_19_trading_days_ago": None,
        "slope_7d_value": None,
        "slope_7d_pct": None,
        "slope_20d_value": None,
        "slope_20d_pct": None,
        "entry_condition": False,
        "exit_condition": False,
    }
    if not ordered or ordered[-1][0] != report_day:
        return {**empty, "status": "blocked_stale_0050_close"}
    if len(ordered) < 20:
        return empty

    closes = [item[1] for item in ordered]
    close = closes[-1]
    close_6 = closes[-7]
    close_19 = closes[-20]
    ma4 = sum(closes[-4:]) / 4
    ma10 = sum(closes[-10:]) / 10
    slope_7 = close - close_6
    slope_20 = close - close_19
    return {
        "status": "ready",
        "close": round(close, 4),
        "ma4": round(ma4, 4),
        "ma10": round(ma10, 4),
        "close_6_trading_days_ago": round(close_6, 4),
        "close_19_trading_days_ago": round(close_19, 4),
        "slope_7d_value": round(slope_7, 4),
        "slope_7d_pct": round(slope_7 / close_6 * 100, 4),
        "slope_20d_value": round(slope_20, 4),
        "slope_20d_pct": round(slope_20 / close_19 * 100, 4),
        "entry_condition": close > ma4 and close > close_6,
        "exit_condition": close < ma10 and close < close_19,
    }


def _price_session_dates(price_rows: list[dict[str, float | str]], report_day: date) -> set[date]:
    sessions: set[date] = set()
    for row in price_rows:
        try:
            row_date = _parse_date(str(row.get("date", "")))
            close = float(row.get("close", 0) or 0)
        except (TypeError, ValueError):
            continue
        if row_date <= report_day and close > 0:
            sessions.add(row_date)
    return sessions


def _reconcile_historical_sessions(
    *,
    latest_trade: dict[str, Any] | None,
    report_day: date,
    price_session_dates: set[date],
    open_dates: set[date],
    closed_dates: set[date],
    session_status_by_date: dict[date, str] | None,
    report_session_status: str,
) -> tuple[set[date], set[date]]:
    if not latest_trade:
        return set(), set()
    trade_day = _parse_date(latest_trade["trade_date"])
    if trade_day >= report_day:
        return set(), set()

    derived_closed: set[date] = set()
    unresolved: set[date] = set()
    status_overrides = session_status_by_date or {}
    candidate = trade_day + timedelta(days=1)
    while candidate <= report_day:
        if candidate.weekday() >= 5 or candidate in closed_dates:
            candidate += timedelta(days=1)
            continue
        if candidate in price_session_dates or candidate in open_dates:
            open_dates.add(candidate)
            candidate += timedelta(days=1)
            continue
        if candidate == report_day:
            status = report_session_status
        else:
            status = status_overrides.get(candidate) or fetch_official_market_session_state(candidate)
        if status == "closed":
            closed_dates.add(candidate)
            derived_closed.add(candidate)
        elif status == "open":
            open_dates.add(candidate)
        else:
            unresolved.add(candidate)
        candidate += timedelta(days=1)
    return derived_closed, unresolved


def _state_closed_session_dates(state: dict[str, Any]) -> set[date]:
    values = state.get("observed_emergency_closed_dates", [])
    parsed: set[date] = set()
    for value in values if isinstance(values, list) else []:
        try:
            parsed.add(_parse_date(str(value)))
        except ValueError:
            continue
    return parsed


def _classify_signal(metrics: dict[str, Any]) -> str:
    if metrics["status"] != "ready":
        return "blocked_source"
    if metrics["entry_condition"] and metrics["exit_condition"]:
        return "conflict_blocked"
    if metrics["entry_condition"]:
        return "entry"
    if metrics["exit_condition"]:
        return "exit"
    return "none"


def _desired_action(signal: str, position_type: str) -> str:
    if signal == "entry":
        return "hold_00631L" if position_type == "long_00631L" else "buy_00631L"
    if signal == "exit":
        return "sell_00631L" if position_type == "long_00631L" else "stay_flat"
    if signal == "none":
        return "hold_00631L" if position_type == "long_00631L" else "stay_flat"
    return "blocked_signal"


def _apply_execution_guards(
    desired_action: str,
    *,
    signal_status: str,
    session_status: str,
    calendar_ready: bool,
    execution_is_blocked: bool,
) -> str:
    if session_status == "closed":
        return "market_closed_no_signal"
    if signal_status != "ready":
        return "blocked_source"
    if not calendar_ready:
        return "blocked_calendar_unavailable"
    if desired_action in {"buy_00631L", "sell_00631L"} and execution_is_blocked:
        return f"cooldown_blocked_{desired_action}"
    return desired_action


def _cooldown_dates(
    latest_trade: dict[str, Any] | None,
    open_dates: set[date],
    closed_dates: set[date],
    calendar_ready: bool,
) -> tuple[list[date], date | None]:
    if not latest_trade or not calendar_ready:
        return [], None
    trade_day = _parse_date(latest_trade["trade_date"])
    sessions = _trading_days_after(trade_day, COOLDOWN_TRADING_DAYS + 1, open_dates, closed_dates)
    if len(sessions) < COOLDOWN_TRADING_DAYS + 1:
        return sessions[:COOLDOWN_TRADING_DAYS], None
    return sessions[:COOLDOWN_TRADING_DAYS], sessions[COOLDOWN_TRADING_DAYS]


def _next_trading_day(value: date, open_dates: set[date], closed_dates: set[date]) -> date | None:
    sessions = _trading_days_after(value, 1, open_dates, closed_dates)
    return sessions[0] if sessions else None


def _trading_days_after(
    value: date,
    count: int,
    open_dates: set[date],
    closed_dates: set[date],
) -> list[date]:
    sessions: list[date] = []
    candidate = value + timedelta(days=1)
    for _ in range(370):
        if is_trading_day(candidate, open_dates, closed_dates):
            sessions.append(candidate)
            if len(sessions) == count:
                return sessions
        candidate += timedelta(days=1)
    return sessions


def _merge_actual_trades(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            if not raw:
                continue
            trade = _normalize_trade(raw)
            key = (trade["trade_date"], trade["action"], trade["ticker"])
            deduped[key] = trade
    return sorted(deduped.values(), key=lambda item: (item["trade_date"], item["action"], item["ticker"]))


def _normalize_trade(raw: dict[str, Any]) -> dict[str, Any]:
    trade_date = _parse_date(str(raw.get("trade_date", ""))).isoformat()
    action = str(raw.get("action", "")).strip().lower()
    if action not in {"buy", "sell"}:
        raise ValueError(f"Unsupported actual trade action: {action}")
    ticker = str(raw.get("ticker") or EXECUTION_TICKER).strip()
    if ticker != EXECUTION_TICKER:
        raise ValueError(f"Actual trade ticker must be {EXECUTION_TICKER}: {ticker}")
    average_price = raw.get("average_price")
    if action == "buy":
        average_price = float(average_price)
        if average_price <= 0:
            raise ValueError("Buy override requires a positive average_price")
    else:
        average_price = None if average_price in {None, ""} else float(average_price)
    return {
        "trade_date": trade_date,
        "action": action,
        "ticker": ticker,
        "average_price": average_price,
        "source": str(raw.get("source") or "actual_trade_state_or_override_only"),
    }


def _position_as_of(trades: list[dict[str, Any]], report_day: date) -> dict[str, Any]:
    position = {"asset_type": "flat", "ticker": "", "average_price": None}
    for trade in trades:
        if _parse_date(trade["trade_date"]) > report_day:
            continue
        if trade["action"] == "buy":
            position = {
                "asset_type": "long_00631L",
                "ticker": EXECUTION_TICKER,
                "average_price": trade["average_price"],
            }
        else:
            position = {"asset_type": "flat", "ticker": "", "average_price": None}
    return position


def _latest_trade_as_of(trades: list[dict[str, Any]], report_day: date) -> dict[str, Any] | None:
    eligible = [trade for trade in trades if _parse_date(trade["trade_date"]) <= report_day]
    return eligible[-1] if eligible else None


def _updated_state(
    prior: dict[str, Any],
    trades: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    timestamp: datetime,
) -> dict[str, Any]:
    latest_trade_day = max((_parse_date(item["trade_date"]) for item in trades), default=None)
    current_position = _position_as_of(trades, latest_trade_day) if latest_trade_day else {
        "asset_type": "flat",
        "ticker": "",
        "average_price": None,
    }
    prior_report = str(prior.get("last_completed_report_date", ""))
    report_date = checkpoint["report_date"]
    use_checkpoint = not prior_report or report_date >= prior_report
    return {
        "schema_version": 2,
        "mode_id": MODE_ID,
        "signal_ticker": SIGNAL_TICKER,
        "execution_ticker": EXECUTION_TICKER,
        "cooldown_trading_days": COOLDOWN_TRADING_DAYS,
        "actual_trades": trades,
        "current_position": current_position,
        "last_completed_report_date": report_date if use_checkpoint else prior_report,
        "last_completed_signal": checkpoint["today_signal"] if use_checkpoint else prior.get("last_completed_signal"),
        "pending_signal": None,
        "signal_carry_forward_used": False,
        "observed_emergency_closed_dates": sorted(
            {
                *[str(value) for value in prior.get("observed_emergency_closed_dates", [])],
                *checkpoint["derived_emergency_closed_dates"],
            }
        ),
        "updated_at": timestamp.isoformat(timespec="seconds"),
        "formal_model_changed": True,
        "trade_decision_changed": True,
        "active_in_trade_decision": True,
        "report_changed": True,
    }


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode_id": MODE_ID,
        "actual_trades": [],
        "current_position": {"asset_type": "flat", "ticker": "", "average_price": None},
        "last_completed_report_date": "",
        "last_completed_signal": "",
        "pending_signal": None,
        "signal_carry_forward_used": False,
    }


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)
