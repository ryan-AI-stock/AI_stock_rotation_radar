from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


YUANTA_0050_HOLDINGS_URL = "https://www.yuantaetfs.com/product/detail/0050/ratio"

STOCK_NAMES = {
    "1303": "南亞",
    "2303": "聯電",
    "2308": "台達電",
    "2317": "鴻海",
    "2327": "國巨*",
    "2330": "台積電",
    "2344": "華邦電",
    "2345": "智邦",
    "2357": "華碩",
    "2360": "致茂",
    "2382": "廣達",
    "2383": "台光電",
    "2408": "南亞科",
    "2412": "中華電",
    "2454": "聯發科",
    "2881": "富邦金",
    "2882": "國泰金",
    "2883": "凱基金",
    "2884": "玉山金",
    "2885": "元大金",
    "2886": "兆豐金",
    "2887": "台新新光金",
    "2890": "永豐金",
    "2891": "中信金",
    "3017": "奇鋐",
    "3037": "欣興",
    "3231": "緯創",
    "3711": "日月光投控",
    "4958": "臻鼎-KY",
    "6669": "緯穎",
}

OLD_AI_7 = ("2330", "2454", "2382", "2317", "6669", "3231", "2308")

# Official Yuanta 0050 PCF Top30 at the last accepted P2 membership date.
# The daily report displays the source date so a stale pool cannot be hidden.
YUANTA_0050_TOP30 = (
    "2330",
    "2454",
    "2308",
    "2317",
    "3711",
    "2303",
    "2327",
    "2383",
    "3037",
    "2891",
    "2345",
    "2881",
    "2382",
    "2882",
    "2360",
    "2887",
    "1303",
    "3017",
    "2885",
    "2344",
    "2886",
    "2412",
    "2408",
    "2884",
    "2890",
    "6669",
    "2357",
    "2883",
    "3231",
    "4958",
)


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
    StrategySpec(
        strategy_id="yuanta_0050_top30_s08_cd3",
        pool_label="0050前30大",
        mode_label="MA7＋10日正斜率買入／MA10＋20日負斜率賣出／CD3",
        symbols=YUANTA_0050_TOP30,
        entry_ma=7,
        entry_slope=10,
        exit_ma=10,
        exit_slope=20,
        cooldown=3,
        pool_source_date="2026-06-30",
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
) -> list[dict[str, object]]:
    state_file = Path(state_path)
    state = _read_state(state_file)
    checkpoints: list[dict[str, object]] = []
    for spec in STRATEGIES:
        item_state = dict(state.get(spec.strategy_id, {}))
        checkpoint, updated = _evaluate_strategy(
            spec,
            price_history,
            report_date=report_date,
            next_execution_date=next_execution_date,
            state=item_state,
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
) -> tuple[dict[str, object], dict[str, object]]:
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
    eligible = [
        dict(metrics, ticker=symbol, name=STOCK_NAMES.get(symbol, symbol))
        for symbol, metrics in evaluations.items()
        if metrics.get("entry_signal") and symbol != last_sold
    ]
    eligible.sort(
        key=lambda row: (
            -float(row.get("normalized_entry_slope", 0) or 0),
            float(row.get("distance_above_entry_ma", 0) or 0),
            str(row["ticker"]),
        )
    )

    today_action = "hold" if held else "stay_flat"
    action_reason = "持股尚未出現完整賣出訊號" if held else "目前沒有符合條件的候選"
    signal_ticker = held
    if not pending:
        if held:
            held_metrics = evaluations.get(held, {})
            trading_days_since_buy = _trading_days_since(dates, buy_date, report_date)
            cooldown_unlocked = trading_days_since_buy > spec.cooldown
            if held_metrics.get("exit_signal") and cooldown_unlocked:
                pending = {
                    "role": "sell",
                    "ticker": held,
                    "decision_date": report_date,
                    "execution_date": next_execution_date,
                }
                today_action = "sell_next_day"
                action_reason = "收盤低於退出均線，且退出斜率為負"
            elif held_metrics.get("exit_signal"):
                today_action = "cooldown_hold"
                action_reason = f"賣出訊號成立，但買入後CD{spec.cooldown}尚未解鎖"
        elif eligible:
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

    focus_metrics = evaluations.get(signal_ticker, {}) if signal_ticker else {}
    checkpoint = {
        "strategy_id": spec.strategy_id,
        "pool_label": spec.pool_label,
        "mode_label": spec.mode_label,
        "pool_source_date": spec.pool_source_date,
        "pool_source_url": YUANTA_0050_HOLDINGS_URL if "top30" in spec.strategy_id else "",
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
        "buy_date": buy_date,
        "trading_days_since_buy": _trading_days_since(dates, buy_date, report_date),
        "data_ready_count": sum(bool(value.get("ready")) for value in evaluations.values()),
        "pool_size": len(spec.symbols),
        "price_basis": "official raw close operational snapshot",
    }
    updated = {
        "last_processed_date": report_date,
        "held_ticker": held,
        "buy_date": buy_date,
        "last_sold_ticker": last_sold,
        "pending_action": pending,
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


def _read_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
