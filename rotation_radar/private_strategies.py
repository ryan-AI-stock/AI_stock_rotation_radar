from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .schedule_gate import is_trading_day


STOCK_NAMES = {
    "00631L": "元大台灣50正2",
    "1101": "台泥",
    "1216": "統一",
    "1301": "台塑",
    "1303": "南亞",
    "1326": "台化",
    "1590": "亞德客-KY",
    "2002": "中鋼",
    "2207": "和泰車",
    "2303": "聯電",
    "2308": "台達電",
    "2317": "鴻海",
    "2327": "國巨*",
    "2330": "台積電",
    "2344": "華邦電",
    "2345": "智邦",
    "2357": "華碩",
    "2360": "致茂",
    "2379": "瑞昱",
    "2382": "廣達",
    "2383": "台光電",
    "2395": "研華",
    "2408": "南亞科",
    "2412": "中華電",
    "2454": "聯發科",
    "2603": "長榮",
    "2615": "萬海",
    "2880": "華南金",
    "2881": "富邦金",
    "2882": "國泰金",
    "2883": "凱基金",
    "2884": "玉山金",
    "2885": "元大金",
    "2886": "兆豐金",
    "2887": "台新新光金",
    "2890": "永豐金",
    "2891": "中信金",
    "2892": "第一金",
    "2912": "統一超",
    "3008": "大立光",
    "3017": "奇鋐",
    "3034": "聯詠",
    "3037": "欣興",
    "3045": "台灣大",
    "3231": "緯創",
    "3661": "世芯-KY",
    "3711": "日月光投控",
    "4904": "遠傳",
    "4958": "臻鼎-KY",
    "5880": "合庫金",
    "6505": "台塑化",
    "6669": "緯穎",
    "7769": "鴻勁",
    "8046": "南電",
}

OLD_AI_7 = ("2330", "2454", "2382", "2317", "6669", "3231", "2308")

PRIVATE_STRATEGY_ACTIVATION_DATE = "2026-07-20"
PRIVATE_STRATEGY_HISTORY_WEEKDAYS = 30
PRIVATE_STRATEGY_STATE_VERSION = "2026-07-21-signal-cooldown-v3"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    pool_label: str
    mode_label: str
    symbols: tuple[str, ...]
    entry_ma: int
    entry_slope: int
    exit_ma: int
    exit_slope: int
    cooldown: int
    pool_source_date: str


STRATEGIES = (
    StrategySpec(
        strategy_id="00631l_ma4_s7_cd7",
        pool_label="0050正二",
        mode_label="MA4＋7日正斜率買入／MA10＋20日負斜率賣出／CD7",
        symbols=("00631L",),
        entry_ma=4,
        entry_slope=7,
        exit_ma=10,
        exit_slope=20,
        cooldown=7,
        pool_source_date="固定標的",
    ),
    StrategySpec(
        strategy_id="old_ai_7_s10_cd10",
        pool_label="老AI固定7檔",
        mode_label="MA10＋20日正斜率買入／MA20＋20日負斜率賣出／CD10",
        symbols=OLD_AI_7,
        entry_ma=10,
        entry_slope=20,
        exit_ma=20,
        exit_slope=20,
        cooldown=10,
        pool_source_date="固定名單",
    ),
)


def required_private_strategy_symbols() -> set[str]:
    return {symbol for spec in STRATEGIES for symbol in spec.symbols}


def build_private_strategy_checkpoints(
    price_history: dict[str, list[dict[str, float | str]]],
    *,
    report_date: str,
    next_execution_date: str,
    state_path: str | Path,
    open_dates: set[date] | None = None,
    closed_dates: set[date] | None = None,
) -> list[dict[str, object]]:
    state_file = Path(state_path)
    loaded_state = _read_state(state_file)
    state = {
        spec.strategy_id: dict(loaded_state.get(spec.strategy_id, {}))
        for spec in STRATEGIES
    }
    checkpoints: list[dict[str, object]] = []
    for spec in STRATEGIES:
        item_state = dict(state.get(spec.strategy_id, {}))
        checkpoint, updated = _evaluate_strategy(
            spec,
            price_history,
            report_date=report_date,
            next_execution_date=next_execution_date,
            state=item_state,
            open_dates=set(open_dates or set()),
            closed_dates=set(closed_dates or set()),
            calendar_ready=closed_dates is not None,
        )
        state[spec.strategy_id] = updated
        checkpoints.append(checkpoint)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return checkpoints


def _evaluate_strategy(
    spec: StrategySpec,
    price_history: dict[str, list[dict[str, float | str]]],
    *,
    report_date: str,
    next_execution_date: str,
    state: dict[str, object],
    open_dates: set[date],
    closed_dates: set[date],
    calendar_ready: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    if state.get("state_version") != PRIVATE_STRATEGY_STATE_VERSION:
        state = {}
    rows_by_symbol = {
        symbol: [
            row
            for row in price_history.get(symbol, [])
            if str(row.get("date", "")) <= report_date and float(row.get("close", 0) or 0) > 0
        ]
        for symbol in spec.symbols
    }
    dates = sorted(
        {
            str(row["date"])
            for rows in rows_by_symbol.values()
            for row in rows
            if str(row.get("date", "")) <= report_date
        }
    )
    last_processed = str(state.get("last_processed_date", "") or "")
    pending = dict(state.get("pending_action", {}) or {})
    held = str(state.get("held_ticker", "") or "")
    buy_date = str(state.get("buy_date", "") or "")
    last_sold = str(state.get("last_sold_ticker", "") or "")
    last_signal_date = str(state.get("last_signal_date", "") or "")
    last_signal_role = str(state.get("last_signal_role", "") or "")
    cooldown_next_tradable_date = str(state.get("cooldown_next_tradable_date", "") or "")
    activation_date = str(state.get("activation_date", PRIVATE_STRATEGY_ACTIVATION_DATE))

    for day in [value for value in dates if value > last_processed]:
        if pending and str(pending.get("execution_date", "")) == day:
            if pending.get("role") == "buy" and not held:
                held = str(pending.get("ticker", ""))
                buy_date = day
            elif pending.get("role") == "sell" and held == str(pending.get("ticker", "")):
                last_sold = held
                held = ""
                buy_date = ""
            pending = {}
        last_processed = day

    evaluations = {
        symbol: _signal_metrics(rows, spec)
        for symbol, rows in rows_by_symbol.items()
    }
    cooldown_locked = bool(
        cooldown_next_tradable_date and report_date < cooldown_next_tradable_date
    )
    ranked_ready = [
        dict(metrics, ticker=symbol, name=STOCK_NAMES.get(symbol, symbol))
        for symbol, metrics in evaluations.items()
        if metrics.get("ready") and (symbol != last_sold or not cooldown_locked)
    ]
    ranked_ready.sort(
        key=lambda row: (
            -float(row.get("normalized_entry_slope", 0) or 0),
            float(row.get("distance_above_entry_ma", 0) or 0),
            str(row["ticker"]),
        )
    )
    eligible = [
        row
        for row in ranked_ready
        if row.get("entry_signal")
    ]

    today_action = "hold" if held else "stay_flat"
    action_reason = "持股尚未出現完整賣出訊號" if held else "目前沒有符合條件的候選"
    signal_ticker = held
    if not signal_ticker and ranked_ready:
        signal_ticker = str(ranked_ready[0]["ticker"])
    if report_date < activation_date:
        today_action = "stay_flat"
        action_reason = f"新模型於 {activation_date} 起開始判斷，目前維持空手"
        signal_ticker = str(ranked_ready[0]["ticker"]) if ranked_ready else ""
    elif not pending:
        if held:
            held_metrics = evaluations.get(held, {})
            trading_days_since_buy = _trading_days_since(dates, buy_date, report_date)
            if held_metrics.get("exit_signal") and not cooldown_locked and calendar_ready:
                pending = {
                    "role": "sell",
                    "ticker": held,
                    "decision_date": report_date,
                    "execution_date": next_execution_date,
                }
                today_action = "sell_next_day"
                action_reason = "收盤低於退出均線，且退出斜率為負"
                last_signal_date = report_date
                last_signal_role = "sell"
                cooldown_next_tradable_date = _cooldown_next_tradable_date(
                    report_date,
                    spec.cooldown,
                    open_dates,
                    closed_dates,
                )
            elif held_metrics.get("exit_signal"):
                today_action = "cooldown_hold"
                action_reason = f"賣出條件成立，但前次交易訊號的CD{spec.cooldown}尚未解鎖"
        elif eligible and cooldown_locked:
            target = eligible[0]
            signal_ticker = str(target["ticker"])
            today_action = "cooldown_wait"
            action_reason = f"買入條件成立，但前次交易訊號的CD{spec.cooldown}尚未解鎖"
        elif eligible and calendar_ready:
            target = eligible[0]
            signal_ticker = str(target["ticker"])
            pending = {
                "role": "buy",
                "ticker": signal_ticker,
                "decision_date": report_date,
                "execution_date": next_execution_date,
            }
            today_action = "buy_next_day"
            action_reason = "候選池中標準化斜率最強，且收盤站上進場均線"
            last_signal_date = report_date
            last_signal_role = "buy"
            cooldown_next_tradable_date = _cooldown_next_tradable_date(
                report_date,
                spec.cooldown,
                open_dates,
                closed_dates,
            )
        elif eligible:
            target = eligible[0]
            signal_ticker = str(target["ticker"])
            today_action = "blocked_calendar"
            action_reason = "買入條件成立，但官方交易日曆不足，禁止建立交易訊號"

    cooldown_locked = bool(
        cooldown_next_tradable_date and report_date < cooldown_next_tradable_date
    )
    focus_metrics = evaluations.get(signal_ticker, {}) if signal_ticker else {}
    checkpoint = {
        "strategy_id": spec.strategy_id,
        "pool_label": spec.pool_label,
        "mode_label": spec.mode_label,
        "pool_source_date": spec.pool_source_date,
        "pool_source_url": "",
        "report_date": report_date,
        "next_execution_date": next_execution_date,
        "today_action": today_action,
        "action_reason": action_reason,
        "held_ticker": held,
        "held_name": STOCK_NAMES.get(held, held) if held else "",
        "signal_ticker": signal_ticker,
        "signal_name": STOCK_NAMES.get(signal_ticker, signal_ticker) if signal_ticker else "",
        "candidate_count": len(eligible),
        "top_candidates": eligible[:5],
        "focus_metrics": focus_metrics,
        "cooldown": spec.cooldown,
        "cooldown_start_signal_date": last_signal_date,
        "cooldown_start_signal_role": last_signal_role,
        "cooldown_next_tradable_date": cooldown_next_tradable_date,
        "cooldown_remaining_trading_days": _remaining_cooldown_days(
            report_date,
            cooldown_next_tradable_date,
            open_dates,
            closed_dates,
        ) if calendar_ready else None,
        "cooldown_status": (
            "locked" if cooldown_locked else "unlocked" if last_signal_date else "not_started"
        ),
        "cooldown_calendar_ready": calendar_ready,
        "buy_date": buy_date,
        "trading_days_since_buy": _trading_days_since(dates, buy_date, report_date),
        "data_ready_count": sum(bool(value.get("ready")) for value in evaluations.values()),
        "pool_size": len(spec.symbols),
        "price_basis": "official raw close operational snapshot",
        "activation_date": activation_date,
        "signal_data_date": str(focus_metrics.get("date", "") or ""),
    }
    updated = {
        "last_processed_date": report_date,
        "held_ticker": held,
        "buy_date": buy_date,
        "last_sold_ticker": last_sold,
        "pending_action": pending,
        "activation_date": activation_date,
        "state_version": PRIVATE_STRATEGY_STATE_VERSION,
        "last_signal_date": last_signal_date,
        "last_signal_role": last_signal_role,
        "cooldown_next_tradable_date": cooldown_next_tradable_date,
    }
    return checkpoint, updated


def _signal_metrics(rows: list[dict[str, float | str]], spec: StrategySpec) -> dict[str, object]:
    ordered = sorted(rows, key=lambda row: str(row.get("date", "")))
    required = max(spec.entry_ma, spec.entry_slope, spec.exit_ma, spec.exit_slope)
    if len(ordered) < required:
        return {"ready": False, "observation_count": len(ordered)}
    closes = [float(row["close"]) for row in ordered]
    close = closes[-1]
    entry_ma = sum(closes[-spec.entry_ma :]) / spec.entry_ma
    exit_ma = sum(closes[-spec.exit_ma :]) / spec.exit_ma
    entry_base = closes[-spec.entry_slope]
    exit_base = closes[-spec.exit_slope]
    entry_slope = close - entry_base
    exit_slope = close - exit_base
    return {
        "ready": True,
        "date": str(ordered[-1]["date"]),
        "close": close,
        "entry_ma": entry_ma,
        "entry_slope": entry_slope,
        "entry_slope_pct": entry_slope / entry_base * 100 if entry_base else 0.0,
        "normalized_entry_slope": entry_slope / entry_base if entry_base else 0.0,
        "distance_above_entry_ma": close / entry_ma - 1 if entry_ma else 0.0,
        "exit_ma": exit_ma,
        "exit_slope": exit_slope,
        "exit_slope_pct": exit_slope / exit_base * 100 if exit_base else 0.0,
        "entry_signal": close > entry_ma and entry_slope > 0,
        "exit_signal": close < exit_ma and exit_slope < 0,
        "observation_count": len(ordered),
    }


def _trading_days_since(dates: list[str], buy_date: str, report_date: str) -> int:
    if not buy_date or buy_date not in dates:
        return 0
    return sum(buy_date < value <= report_date for value in dates)


def _cooldown_next_tradable_date(
    signal_date: str,
    cooldown: int,
    open_dates: set[date],
    closed_dates: set[date],
) -> str:
    signal_day = date.fromisoformat(signal_date)
    sessions: list[date] = []
    candidate = signal_day + timedelta(days=1)
    for _ in range(370):
        if is_trading_day(candidate, open_dates, closed_dates):
            sessions.append(candidate)
            if len(sessions) == cooldown + 1:
                return candidate.isoformat()
        candidate += timedelta(days=1)
    return ""


def _remaining_cooldown_days(
    report_date: str,
    next_tradable_date: str,
    open_dates: set[date],
    closed_dates: set[date],
) -> int:
    if not next_tradable_date or report_date >= next_tradable_date:
        return 0
    current = date.fromisoformat(report_date) + timedelta(days=1)
    boundary = date.fromisoformat(next_tradable_date)
    remaining = 0
    while current < boundary:
        if is_trading_day(current, open_dates, closed_dates):
            remaining += 1
        current += timedelta(days=1)
    return remaining


def _read_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
