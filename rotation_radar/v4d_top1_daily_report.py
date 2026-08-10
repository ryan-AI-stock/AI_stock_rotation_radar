from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from .base_cycle_daily_report import (
    ReportDataNotReady,
    load_official_prices_and_turnover,
)
from .disposition_gate import DispositionSourceNotReady, load_disposition_gate
from .schedule_gate import fetch_twse_calendar, is_trading_day
from .v4d_actual_trade import load_actual_trade_state


REPORT_TITLE = "最新版個股模型 V4-D｜Top1 每日追蹤"
MODEL_NAME = (
    "全市場硬篩選＋基期Top1｜TD1～5 -5%／5TD -10%／累積 -10%／"
    "TD14未達 +5%；曾達 +7%但未達 +10%時，回落至 +1%退出／"
    "曾達 +10%者改由高點回落10%管理／"
    "TD22未曾達 +10%且當下未達 +8%退出／TD55起當下未達 +20%退出｜"
    "處置Top1空手且不遞補"
)
BUY_RATE = 0.001425 + 0.001
SELL_RATE = 0.001425 + 0.003 + 0.001
POSITION_STREAM_MESSAGE = "模型尚未正式買入，此訊息流空。"
MEDIAN_ROUTE_COUNT = 64
MEDIAN_ROUTE_FINAL_CAPITAL = 1_251_832_131.3663318
MEDIAN_ROUTE_CAGR = 0.5758699206870523
TRADING_DAYS_PER_YEAR = 252
MEDIAN_ROUTE_DAILY_RATE = (1 + MEDIAN_ROUTE_CAGR) ** (
    1 / TRADING_DAYS_PER_YEAR
) - 1
TAIEX_MONTHLY_URL = (
    "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST"
    "?date={month}01&response=json"
)
MA120_EVENT_LOOKBACK_MONTHS = 9
MA120_EVENT_EXPIRY_TD = 40


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the private V4-D Top1 position tracking report."
    )
    parser.add_argument("--date", required=True, help="Taiwan trading date, YYYY-MM-DD")
    parser.add_argument("--source-repo", default=".")
    parser.add_argument("--state", default="data/formal_v4d_top1_state.json")
    parser.add_argument(
        "--position-state", default="data/formal_v4d_actual_trade_state.json"
    )
    parser.add_argument("--output", default="reports/formal_v4d_top1_daily.html")
    parser.add_argument("--tracking-output", default="reports/formal_v4d_top1_daily.csv")
    parser.add_argument("--source-cache", default="data/current_base_cycle_source_cache")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--pending-seed",
        action="store_true",
        help="Render the pre-execution seed without fetching a new market close.",
    )
    args = parser.parse_args()
    if args.pending_seed:
        payload = build_pending_seed_report(
            state_path=Path(args.state),
            position_state_path=Path(args.position_state),
            output_path=Path(args.output),
            tracking_output=Path(args.tracking_output),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    try:
        payload = build_daily_report(
            report_date=args.date,
            source_repo=Path(args.source_repo),
            state_path=Path(args.state),
            position_state_path=Path(args.position_state),
            output_path=Path(args.output),
            tracking_output=Path(args.tracking_output),
            source_cache=Path(args.source_cache),
            offline=args.offline,
        )
    except ReportDataNotReady as exc:
        print(f"report_data_not_ready: {exc}")
        raise SystemExit(75) from exc
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def load_state(path: Path) -> dict:
    state = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "ticker",
        "name",
        "signal_date",
        "signal_close",
        "execution_date",
        "status",
        "daily_marks",
    }
    missing = sorted(required - set(state))
    if missing:
        raise RuntimeError(f"V4-D state missing required fields: {missing}")
    return state


def _roc_date(value: str) -> pd.Timestamp:
    year, month, day = (int(part) for part in value.split("/"))
    return pd.Timestamp(year=year + 1911, month=month, day=day)


def _taiex_months(target: pd.Timestamp) -> list[str]:
    start = target.to_period("M") - (MA120_EVENT_LOOKBACK_MONTHS - 1)
    return [
        str(period).replace("-", "")
        for period in pd.period_range(start, target.to_period("M"), freq="M")
    ]


def _taiex_payload_last_date(payload: dict) -> pd.Timestamp | None:
    dates: list[pd.Timestamp] = []
    for item in payload.get("data", []):
        if not item:
            continue
        try:
            dates.append(_roc_date(str(item[0])))
        except (TypeError, ValueError):
            continue
    return max(dates) if dates else None


def load_taiex_history(
    *,
    target: pd.Timestamp,
    source_cache: Path,
    offline: bool,
) -> pd.DataFrame:
    cache = source_cache / "taiex_monthly"
    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for month in _taiex_months(target):
        path = cache / f"{month}.json"
        payload = None
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_last_date = _taiex_payload_last_date(payload)
            if (
                not offline
                and month == target.strftime("%Y%m")
                and (cached_last_date is None or cached_last_date < target)
            ):
                payload = None
        if payload is None and offline:
            raise ReportDataNotReady(f"TAIEX monthly cache missing: {month}")
        if payload is None:
            request = Request(
                TAIEX_MONTHLY_URL.format(month=month),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise ReportDataNotReady(
                    f"TAIEX monthly source unavailable: {month}"
                ) from exc
            if payload.get("stat") != "OK":
                raise ReportDataNotReady(
                    f"TAIEX monthly source not ready: {month}"
                )
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        for item in payload.get("data", []):
            if len(item) < 5:
                continue
            rows.append(
                {
                    "date": _roc_date(str(item[0])),
                    "close": float(str(item[4]).replace(",", "")),
                }
            )
    frame = (
        pd.DataFrame(rows)
        .drop_duplicates("date", keep="last")
        .sort_values("date")
    )
    frame = frame.loc[frame["date"].le(target)].reset_index(drop=True)
    if len(frame) < 140 or frame.empty or frame.iloc[-1]["date"] < target:
        raise ReportDataNotReady(
            "TAIEX history is incomplete for MA60/MA120 monitoring"
        )
    return frame


def evaluate_ma120_market_monitor(history: pd.DataFrame) -> dict:
    frame = history[["date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.dropna().drop_duplicates("date", keep="last").sort_values("date")
    frame["ma60"] = frame["close"].rolling(60, min_periods=60).mean()
    frame["ma120"] = frame["close"].rolling(120, min_periods=120).mean()
    frame["close_vs_ma120"] = frame["close"] / frame["ma120"] - 1
    frame["prior20_max_vs_ma120"] = (
        frame["close_vs_ma120"].shift(1).rolling(20, min_periods=20).max()
    )
    frame["near_ma120"] = (
        frame["close_vs_ma120"].between(0.0, 0.02, inclusive="both")
        & frame["prior20_max_vs_ma120"].ge(0.04)
    )
    frame["cross_above_ma60"] = frame["close"].gt(frame["ma60"]) & frame[
        "close"
    ].shift(1).le(frame["ma60"].shift(1))

    active: dict | None = None
    prior_near = False
    last_event_status = "idle"
    last_event_date: pd.Timestamp | None = None
    for index, row in frame.iterrows():
        near = bool(row["near_ma120"]) if pd.notna(row["near_ma120"]) else False
        if active is None and near and not prior_near:
            active = {
                "touch_index": int(index),
                "touch_date": pd.Timestamp(row["date"]),
                "latest_low": float(row["close"]),
                "latest_low_index": int(index),
                "preliminary_date": None,
            }
            last_event_status = "monitoring"
            last_event_date = pd.Timestamp(row["date"])

        if active is not None:
            age = int(index) - int(active["touch_index"])
            close = float(row["close"])
            if age > 0 and close < float(row["ma120"]):
                last_event_status = "invalidated"
                last_event_date = pd.Timestamp(row["date"])
                active = None
            elif age > MA120_EVENT_EXPIRY_TD:
                last_event_status = "expired"
                last_event_date = pd.Timestamp(row["date"])
                active = None
            else:
                if close < float(active["latest_low"]):
                    active["latest_low"] = close
                    active["latest_low_index"] = int(index)
                    active["preliminary_date"] = None
                days_since_low = int(index) - int(active["latest_low_index"])
                if (
                    active["preliminary_date"] is None
                    and days_since_low >= 3
                    and close >= float(row["ma120"])
                ):
                    active["preliminary_date"] = pd.Timestamp(row["date"])
                    last_event_status = "preliminary_stabilized"
                    last_event_date = pd.Timestamp(row["date"])
                if (
                    active["preliminary_date"] is not None
                    and bool(row["cross_above_ma60"])
                ):
                    last_event_status = "ma60_confirmed"
                    last_event_date = pd.Timestamp(row["date"])
                    active = None
        prior_near = near

    latest = frame.iloc[-1]
    if active is not None:
        days_without_new_low = len(frame) - 1 - int(active["latest_low_index"])
        state = (
            "preliminary_stabilized"
            if active["preliminary_date"] is not None
            else "monitoring"
        )
        touch_date = pd.Timestamp(active["touch_date"]).date().isoformat()
    else:
        days_without_new_low = 0
        latest_date = pd.Timestamp(latest["date"])
        state = (
            last_event_status
            if last_event_date is not None and last_event_date == latest_date
            else "idle"
        )
        touch_date = (
            last_event_date.date().isoformat()
            if last_event_date is not None
            else ""
        )
    labels = {
        "idle": "近期未發生跌至半年線附近走勢",
        "monitoring": "半年線附近監測中，尚未止穩",
        "preliminary_stabilized": "3TD未再破底，等待站回季線",
        "ma60_confirmed": "已完成止穩並站回季線",
        "invalidated": "收盤跌破半年線，本次支撐監測失效",
        "expired": "監測逾40TD未確認，本次事件結束",
    }
    return {
        "date": pd.Timestamp(latest["date"]).date().isoformat(),
        "state": state,
        "state_label": labels[state],
        "close": float(latest["close"]),
        "ma60": float(latest["ma60"]),
        "ma120": float(latest["ma120"]),
        "close_vs_ma120_pct": float(latest["close_vs_ma120"] * 100),
        "prior20_max_vs_ma120_pct": float(
            latest["prior20_max_vs_ma120"] * 100
        ),
        "near_ma120_pass": bool(latest["near_ma120"]),
        "days_without_new_low": int(days_without_new_low),
        "ma60_reclaimed": bool(latest["close"] > latest["ma60"]),
        "touch_date": touch_date,
        "research_refresh_trigger": state == "ma60_confirmed",
    }


def research_refresh_decision(monitor: dict, state: dict) -> str:
    if not monitor.get("research_refresh_trigger"):
        return "尚未觸發研究版刷新"
    holding_ticker = str(state.get("holding_ticker") or "")
    new_top1 = str(state.get("ticker") or "")
    if not holding_ticker:
        return "目前空手；下一交易日仍依正式V4-D Top1處理"
    peaks = [
        float(item["peak_after_cost_return_pct"])
        for item in state.get("daily_marks", {}).values()
        if item.get("peak_after_cost_return_pct") is not None
    ]
    peak = max(peaks) if peaks else float("-inf")
    if peak >= 10:
        return "持股曾達+10%；保留強股，不研究強制換股"
    if holding_ticker == new_top1:
        return "新Top1與持股相同；不換股"
    if not new_top1:
        return "沒有合格Top1；不為刷新而賣出"
    return f"研究版符合刷新條件：{holding_ticker} → {new_top1}"


def require_current_top1_signal(state: dict, target: pd.Timestamp) -> None:
    signal_date = pd.Timestamp(state["signal_date"])
    if signal_date != target:
        raise ReportDataNotReady(
            "V4-D formal Top1 signal is stale: "
            f"signal_date={signal_date:%Y-%m-%d}, "
            f"report_date={target:%Y-%m-%d}"
        )


def update_state(
    state: dict,
    *,
    mark_date: str,
    close: float,
    prior_close: float | None,
    closed_dates: set[date] | None = None,
) -> dict:
    state = json.loads(json.dumps(state))
    execution_date = pd.Timestamp(state["execution_date"])
    current_date = pd.Timestamp(mark_date)
    marks = state.setdefault("daily_marks", {})
    if current_date >= execution_date:
        if state.get("entry_close") is None:
            state["entry_close"] = float(close)
            state["status"] = "holding"
        marks[mark_date] = {
            "close": float(close),
            "daily_return_pct": (
                (float(close) / float(prior_close) - 1) * 100
                if prior_close not in (None, 0)
                else None
            ),
        }
        _refresh_holding_metrics(state)
        trigger = _current_exit_trigger(state)
        if trigger is not None and not state.get("pending_exit"):
            execution_day = _trading_dates_from(
                current_date.date(),
                1,
                closed_dates=closed_dates,
                exclude_start=True,
            )[0]
            state["pending_exit"] = {
                "decision_date": mark_date,
                "execution_date": execution_day.isoformat(),
                "reason": trigger,
            }
            state["status"] = "pending_sell"
    state["last_report_date"] = mark_date
    return state


def _refresh_holding_metrics(state: dict) -> None:
    entry = state.get("entry_close")
    if entry in (None, 0):
        return
    peak = None
    ordered = sorted(state.get("daily_marks", {}).items())
    actual_units = int(state.get("shares") or 0)
    actual_buy_fee = float(state.get("buy_fee") or 0)
    actual_cost_basis = float(
        state.get("position_cost") or (float(entry) * actual_units + actual_buy_fee)
    )
    for index, (_day, item) in enumerate(ordered):
        close = float(item["close"])
        net = (
            close * actual_units * (1 - SELL_RATE) / actual_cost_basis - 1
            if state.get("actual_position_confirmed") and actual_units > 0
            else close / float(entry) * (1 - SELL_RATE) / (1 + BUY_RATE) - 1
        )
        peak = net if peak is None else max(peak, net)
        item["d_index"] = index
        item["model_td"] = index + 1
        item["cumulative_return_pct"] = (close / float(entry) - 1) * 100
        item["after_cost_return_pct"] = net * 100
        item["peak_after_cost_return_pct"] = peak * 100
        item["trailing_drawdown_pct"] = (
            ((1 + net) / (1 + peak) - 1) * 100 if peak is not None else None
        )
        item["rolling_5td_return_pct"] = (
            (close / float(ordered[index - 4][1]["close"]) - 1) * 100
            if index >= 4
            else None
        )


def _current_exit_trigger(state: dict) -> str | None:
    ordered = sorted(state.get("daily_marks", {}).items())
    if not ordered:
        return None
    item = ordered[-1][1]
    elapsed = int(item["model_td"])
    net = float(item["after_cost_return_pct"])
    peak = float(item["peak_after_cost_return_pct"])
    rolling = item.get("rolling_5td_return_pct")
    trailing = item.get("trailing_drawdown_pct")
    if elapsed <= 5 and net <= -5:
        return "TD1～5 after-cost 虧損達5%"
    if rolling is not None and float(rolling) <= -10:
        return "任意5TD價格下跌達10%"
    if elapsed >= 6 and net <= -10:
        return "累積 after-cost 虧損達10%"
    if 7 <= peak < 10 and net <= 1:
        return "曾達+7%但未達+10%，其後回落至+1%"
    if elapsed == 14 and net < 5:
        if peak >= 10:
            if trailing is not None and float(trailing) <= -10:
                return "曾達+10%，其後由高點回落達10%"
        else:
            return "TD14 after-cost 未達+5%"
    if elapsed == 22 and peak < 10 and net < 8:
        return "TD22未曾達+10%，且當下未達+8%"
    if elapsed >= 14 and peak >= 10 and trailing is not None and float(trailing) <= -10:
        return "曾達+10%，其後由高點回落達10%"
    if elapsed >= 55 and net < 20:
        return "TD55起，當下after-cost未達+20%"
    return None


def tracking_rows(state: dict) -> list[dict]:
    rows = []
    for day, item in sorted(state.get("daily_marks", {}).items()):
        model_td = item.get("model_td")
        benchmark_elapsed_td = max(int(model_td or 1) - 1, 0)
        benchmark_cumulative_pct = (
            (1 + MEDIAN_ROUTE_DAILY_RATE) ** benchmark_elapsed_td - 1
        ) * 100
        actual_cumulative_pct = item.get("cumulative_return_pct")
        rows.append(
            {
                "date": day,
                "ticker": state["ticker"],
                "name": state["name"],
                "d_index": item.get("d_index"),
                "model_td": model_td,
                "close": item["close"],
                "daily_return_pct": item.get("daily_return_pct"),
                "cumulative_return_pct": actual_cumulative_pct,
                "after_cost_return_pct": item.get("after_cost_return_pct"),
                "peak_after_cost_return_pct": item.get(
                    "peak_after_cost_return_pct"
                ),
                "rolling_5td_return_pct": item.get("rolling_5td_return_pct"),
                "benchmark_elapsed_td": benchmark_elapsed_td,
                "benchmark_cumulative_pct": benchmark_cumulative_pct,
                "excess_vs_benchmark_pct": (
                    float(actual_cumulative_pct) - benchmark_cumulative_pct
                    if actual_cumulative_pct is not None
                    else None
                ),
            }
        )
    return rows


def _trading_dates_from(
    start: date,
    count: int,
    *,
    closed_dates: set[date] | None,
    exclude_start: bool = False,
) -> list[date]:
    closed = set(closed_dates or set())
    values = []
    current = start + timedelta(days=1) if exclude_start else start
    while len(values) < count:
        if is_trading_day(current, set(), closed):
            values.append(current)
        current += timedelta(days=1)
    return values


def gate_plan(state: dict, closed_dates: set[date] | None = None) -> list[dict]:
    start = pd.Timestamp(state["execution_date"]).date()
    days = _trading_dates_from(start, 55, closed_dates=closed_dates)
    return [
        {
            "stage": "第一道｜買錯即退",
            "range": f"{days[0]:%m/%d}～{days[4]:%m/%d}",
            "day": "TD1～TD5",
            "rule": "after-cost 虧損達 -5%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第二道｜急跌防守",
            "range": f"{days[4]:%m/%d} 起每日",
            "day": "第5筆收盤起",
            "rule": "任意5TD價格下跌達 -10%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第三道｜緩跌防守",
            "range": f"{days[5]:%m/%d} 起每日",
            "day": "TD6起",
            "rule": "累積 after-cost 虧損達 -10%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第四道｜獲利保全",
            "range": f"{days[0]:%m/%d} 起每日",
            "day": "持有期間",
            "rule": "曾達+7%但未達+10%，回落至+1%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第五道｜發動檢查",
            "range": f"{days[13]:%m/%d}",
            "day": "TD14",
            "rule": "after-cost 未達 +5%",
            "action": "未曾達+10%則下一交易日賣出",
        },
        {
            "stage": "第六道｜主升保護",
            "range": f"{days[13]:%m/%d} 起每日",
            "day": "TD14起",
            "rule": "曾達+10%後，自高點回落10%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第七道｜最終檢查",
            "range": f"{days[21]:%m/%d}",
            "day": "TD22",
            "rule": "從未達+10%，且當下未達+8%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第八道｜長抱成長檢查",
            "range": f"{days[54]:%m/%d} 起每日",
            "day": "TD55起",
            "rule": "當下after-cost未達+20%",
            "action": "收盤成立，下一交易日賣出",
        },
    ]


def build_daily_report(
    *,
    report_date: str,
    source_repo: Path,
    state_path: Path,
    position_state_path: Path,
    output_path: Path,
    tracking_output: Path,
    source_cache: Path,
    offline: bool = False,
) -> dict:
    target = pd.Timestamp(report_date)
    signal_state = load_state(state_path)
    require_current_top1_signal(signal_state, target)
    actual_trade_state = load_actual_trade_state(position_state_path)
    position_state = actual_trade_state.get("position")
    try:
        disposition_gate = load_disposition_gate(
            ticker=signal_state["ticker"],
            signal_date=pd.Timestamp(signal_state["signal_date"]).date(),
            execution_date=pd.Timestamp(signal_state["execution_date"]).date(),
            source_cache=source_cache,
            offline=offline,
        )
    except DispositionSourceNotReady as exc:
        raise ReportDataNotReady(str(exc)) from exc
    current_rows = [
        {
            "ticker": str(signal_state["ticker"]).zfill(4),
            "name": signal_state["name"],
            "market": signal_state.get("market", "TWSE"),
        }
    ]
    if position_state and str(position_state["ticker"]).zfill(4) != str(
        signal_state["ticker"]
    ).zfill(4):
        current_rows.append(
            {
                "ticker": str(position_state["ticker"]).zfill(4),
                "name": position_state["name"],
                "market": position_state.get("market", "TWSE"),
            }
        )
    current = pd.DataFrame(current_rows)
    official, _ = load_official_prices_and_turnover(
        source_repo=source_repo,
        target=target,
        current=current,
        source_cache=source_cache,
        offline=offline,
    )
    official["ticker"] = official["ticker"].astype(str).str.zfill(4)
    official["date"] = pd.to_datetime(official["date"])
    signal_rows = official[
        official["ticker"].eq(str(signal_state["ticker"]).zfill(4))
        & official["date"].le(target)
    ].dropna(subset=["close"]).sort_values("date")
    if signal_rows.empty:
        raise ReportDataNotReady(
            f"No official close available for {signal_state['ticker']}"
        )
    latest = signal_rows.iloc[-1]
    if latest["date"] < target and not offline:
        raise ReportDataNotReady(
            f"Target-date official close is not ready for {signal_state['ticker']}"
        )
    actual = pd.Timestamp(latest["date"])
    tracking_state = position_state or signal_state
    if position_state:
        position_rows = official[
            official["ticker"].eq(str(position_state["ticker"]).zfill(4))
            & official["date"].le(target)
        ].dropna(subset=["close"]).sort_values("date")
        if position_rows.empty or position_rows.iloc[-1]["date"] < target:
            raise ReportDataNotReady(
                f"Target-date official close is not ready for held {position_state['ticker']}"
            )
        position_latest = position_rows.iloc[-1]
        position_prior = position_rows[position_rows["date"].lt(position_latest["date"])]
        prior_close = (
            float(position_prior.iloc[-1]["close"])
            if not position_prior.empty
            else None
        )
        tracking_state = update_state(
            position_state,
            mark_date=actual.strftime("%Y-%m-%d"),
            close=float(position_latest["close"]),
            prior_close=prior_close,
            closed_dates=fetch_twse_calendar()[1],
        )
        actual_trade_state["position"] = tracking_state
        position_state_path.parent.mkdir(parents=True, exist_ok=True)
        position_state_path.write_text(
            json.dumps(actual_trade_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    rows = tracking_rows(tracking_state) if position_state else []
    taiex_history = load_taiex_history(
        target=actual,
        source_cache=source_cache,
        offline=offline,
    )
    market_monitor = evaluate_ma120_market_monitor(taiex_history)
    tracking_output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(tracking_output, index=False, encoding="utf-8-sig")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_html(
            actual,
            tracking_state,
            rows,
            closed_dates=fetch_twse_calendar()[1],
            market_monitor=market_monitor,
            disposition_gate=disposition_gate,
            signal_state=signal_state,
        ),
        encoding="utf-8",
    )
    return {
        "status": "complete",
        "requested_report_date": report_date,
        "actual_report_date": actual.strftime("%Y-%m-%d"),
        "model": "V4-D",
        "top1_ticker": signal_state["ticker"],
        "top1_name": signal_state["name"],
        "signal_date": signal_state["signal_date"],
        "execution_date": signal_state["execution_date"],
        "position_status": tracking_state["status"] if position_state else "cash",
        "trade_feasibility_status": disposition_gate["status"],
        "trade_feasibility_blocked": disposition_gate["blocked"],
        "ma120_market_state": market_monitor["state"],
        "ma120_market_state_label": market_monitor["state_label"],
        "tracking_row_count": len(rows),
        "future_data_violation_count": 0,
    }


def build_pending_seed_report(
    *,
    state_path: Path,
    position_state_path: Path,
    output_path: Path,
    tracking_output: Path,
) -> dict:
    signal_state = load_state(state_path)
    actual_trade_state = load_actual_trade_state(position_state_path)
    position_state = actual_trade_state.get("position")
    state = position_state or signal_state
    rows = tracking_rows(state) if position_state else []
    tracking_output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows,
        columns=[
            "date",
            "ticker",
            "name",
            "close",
            "daily_return_pct",
            "cumulative_return_pct",
            "after_cost_return_pct",
            "peak_after_cost_return_pct",
            "rolling_5td_return_pct",
        ],
    ).to_csv(tracking_output, index=False, encoding="utf-8-sig")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_html(
            pd.Timestamp(signal_state["signal_date"]),
            state,
            rows,
            signal_state=signal_state,
        ),
        encoding="utf-8",
    )
    return {
        "status": "complete_pending_execution_close",
        "actual_report_date": signal_state["signal_date"],
        "model": "V4-D",
        "top1_ticker": signal_state["ticker"],
        "top1_name": signal_state["name"],
        "execution_date": signal_state["execution_date"],
        "position_status": state["status"] if position_state else "cash",
        "tracking_row_count": len(rows),
        "future_data_violation_count": 0,
    }


def render_html(
    actual: pd.Timestamp,
    state: dict,
    rows: list[dict],
    *,
    closed_dates: set[date] | None = None,
    preview_assumed_holding: bool = False,
    market_monitor: dict | None = None,
    disposition_gate: dict | None = None,
    signal_state: dict | None = None,
) -> str:
    signal_state = signal_state or state
    status_map = {
        "holding": "持有中",
        "pending_sell": "已出現賣出訊號",
        "pending_execution_close": "等待執行日收盤",
    }
    status = status_map.get(state["status"], state["status"])
    entry_close = (
        f"{float(state['entry_close']):,.2f}"
        if state.get("entry_close") is not None
        else "尚未建立"
    )
    actual_shares = int(state.get("shares") or 0)
    remaining_cash = float(state.get("remaining_cash") or 0)
    latest = rows[-1] if rows else None
    latest_close = (
        f"{float(latest['close']):,.2f}" if latest else f"{float(state['signal_close']):,.2f}"
    )
    latest_return = (
        f"{float(latest['after_cost_return_pct']):+.2f}%"
        if latest and latest.get("after_cost_return_pct") is not None
        else "尚未開始"
    )
    benchmark_latest = (
        float(latest.get("benchmark_cumulative_pct") or 0) if latest else 0.0
    )
    actual_latest = (
        float(latest.get("cumulative_return_pct") or 0) if latest else 0.0
    )
    excess_latest = actual_latest - benchmark_latest
    stream_active = bool(rows) and bool(
        state.get("actual_position_confirmed") or preview_assumed_holding
    )
    next_action = f"{signal_state['execution_date']} 執行買入並計為TD1"
    if latest:
        next_action = "持續持有，下一交易日再檢查"
    if state.get("pending_exit"):
        pending = state["pending_exit"]
        next_action = (
            f"{pending['execution_date']} 賣出｜{pending['reason']}"
        )
    history = "".join(
        "<tr>"
        f"<td>{escape(item['date'])}</td>"
        f"<td><b>TD{item.get('model_td', '—')}</b></td>"
        f"<td>{float(item['close']):,.2f}</td>"
        f"<td class=\"{_return_class(item.get('daily_return_pct'))}\">{'建倉' if int(item.get('benchmark_elapsed_td') or 0) == 0 else _pct(item.get('daily_return_pct'))}</td>"
        f"<td class=\"{_return_class(item.get('cumulative_return_pct'))}\">{_pct(item.get('cumulative_return_pct'))}</td>"
        f"<td class=\"benchmark\">{_pct(item.get('benchmark_cumulative_pct'))}</td>"
        f"<td class=\"{_return_class(item.get('excess_vs_benchmark_pct'))}\">{_pct(item.get('excess_vs_benchmark_pct'))}</td>"
        f"<td>{_daily_gate_text(item, state)}</td>"
        "</tr>"
        for item in rows
    ) or (
        '<tr><td colspan="8" class="empty">'
        f"{escape(state['execution_date'])} 執行買入後，才建立TD1第一筆正式交易紀錄。"
        "</td></tr>"
    )
    plan_rows = "".join(
        "<tr>"
        f"<td><b>{escape(item['stage'])}</b><small>{escape(item['day'])}</small></td>"
        f"<td>{escape(item['range'])}</td>"
        f"<td>{escape(item['rule'])}</td>"
        f"<td>{escape(item['action'])}</td>"
        "</tr>"
        for item in gate_plan(state, closed_dates)
    )
    if not stream_active:
        overview = (
            f'<div class="paused">{escape(POSITION_STREAM_MESSAGE)}</div>'
        )
        history_section = (
            f'<div class="paused">{escape(POSITION_STREAM_MESSAGE)}</div>'
        )
        plan_section = (
            f'<div class="paused">{escape(POSITION_STREAM_MESSAGE)}</div>'
        )
        plan_block = ""
        footer_block = ""
    else:
        overview = f"""
<div class="hero-grid">
  <div class="holding-card">
    <div class="eyebrow">實際正式部位</div>
    <div class="holding-name">{escape(state['ticker'])} {escape(state['name'])}</div>
    <div class="holding-meta">訊號 {escape(state['signal_date'])}｜買入 {escape(state['execution_date'])}｜{_holding_label(latest)}</div>
    <div class="holding-meta">實際均價 {entry_close}｜持股 {actual_shares:,} 股｜剩餘現金 {remaining_cash:,.0f} 元</div>
    <div class="holding-price">最新收盤 <b>{latest_close}</b></div>
  </div>
  <div class="comparison-card">
    <div class="eyebrow">目前累積比較</div>
    <div class="comparison-row"><span>個股實際</span><b class="{_return_class(actual_latest)}">{actual_latest:+.2f}%</b></div>
    <div class="comparison-row"><span>中位數路徑</span><b class="benchmark">{benchmark_latest:+.2f}%</b></div>
    <div class="comparison-row emphasis"><span>相較中位數</span><b class="{_return_class(excess_latest)}">{excess_latest:+.2f} 個百分點</b></div>
  </div>
</div>"""
        history_section = f"""
<p class="note">買入日只建立0%比較基準；下一交易日開始，將個股收盤價累積漲跌與中位數年化線逐日比較。</p>
<table class="history"><thead><tr><th>日期</th><th>模型日</th><th>收盤</th><th>當日漲跌</th><th>個股累積</th><th>中位路徑累積</th><th>相差</th><th>V4-D狀態</th></tr></thead><tbody>{history}</tbody></table>"""
        plan_section = f"""
<div class="plan-head"><b>下一步：{escape(next_action)}</b><span>目前 after-cost：{latest_return}</span></div>
<table><thead><tr><th>檢查關卡</th><th>日期</th><th>判斷條件</th><th>成立後動作</th></tr></thead><tbody>{plan_rows}</tbody></table>"""
        plan_block = (
            '<section class="plan"><h2>第七部分｜V4-D完整監控計畫</h2>'
            f"{plan_section}</section>"
        )
        footer_block = (
            "<footer>私人研究報告。中位數年化線與半年線監測只作研究比較，"
            "不改變V4-D正式買賣訊號。Top1 為 V4-D 凍結規則在 "
            f"{escape(signal_state['signal_date'])} 收盤後的結果。</footer>"
        )
    benchmark_td5 = ((1 + MEDIAN_ROUTE_DAILY_RATE) ** 4 - 1) * 100
    benchmark_td14 = ((1 + MEDIAN_ROUTE_DAILY_RATE) ** 13 - 1) * 100
    benchmark_td22 = ((1 + MEDIAN_ROUTE_DAILY_RATE) ** 21 - 1) * 100
    if market_monitor is None:
        market_section = (
            '<div class="market-monitor neutral">'
            "<b>半年線監測資料尚未載入</b>"
            "<span>本區塊只作研究提示，不影響正式V4-D訊號。</span>"
            "</div>"
        )
    else:
        state_class = {
            "monitoring": "watch",
            "preliminary_stabilized": "watch",
            "ma60_confirmed": "confirmed",
            "invalidated": "invalid",
            "expired": "neutral",
            "idle": "neutral",
        }.get(market_monitor["state"], "neutral")
        refresh_state = dict(state)
        refresh_state["ticker"] = signal_state["ticker"]
        if state.get("actual_position_confirmed"):
            refresh_state["holding_ticker"] = state["ticker"]
        refresh_text = research_refresh_decision(market_monitor, refresh_state)
        market_section = f"""
<div class="market-monitor {state_class}">
  <div class="market-monitor-head"><div><span>目前狀態</span><b>{escape(market_monitor['state_label'])}</b></div><strong>{float(market_monitor['close']):,.2f}</strong></div>
  <div class="market-grid">
    <div><small>MA120</small><b>{float(market_monitor['ma120']):,.2f}</b><span>距半年線 {float(market_monitor['close_vs_ma120_pct']):+.2f}%</span></div>
    <div><small>前20TD高點證據</small><b>{float(market_monitor['prior20_max_vs_ma120_pct']):+.2f}%</b><span>門檻至少 +4%</span></div>
    <div><small>不再破底進度</small><b>{int(market_monitor['days_without_new_low'])} / 3 TD</b><span>新低出現即歸零</span></div>
    <div><small>MA60確認</small><b>{'已站回' if market_monitor['ma60_reclaimed'] else '尚未站回'}</b><span>MA60 {float(market_monitor['ma60']):,.2f}</span></div>
  </div>
  <div class="refresh-research"><b>未發動持股刷新研究：</b>{escape(refresh_text)}</div>
</div>
<p class="note">半年線事件與未發動持股刷新仍是challenger研究資訊；回測未通過前，不改變正式V4-D持股或交易指令。</p>"""
    gate = disposition_gate or {
        "blocked": False,
        "status": "not_checked",
        "message": "處置股交易可行性尚未查核。",
        "events": [],
    }
    gate_class = "invalid" if gate["blocked"] else "confirmed"
    event_text = ""
    if gate["events"]:
        event = gate["events"][0]
        event_text = (
            f"<span>官方處置期間：{escape(event['start_date'])}～"
            f"{escape(event['end_date'])}</span>"
        )
    trade_gate_section = f"""
<div class="market-monitor {gate_class}">
  <div class="market-monitor-head"><div><span>交易可行性</span><b>{escape(gate['message'])}</b></div><strong>{'空手' if gate['blocked'] else '可執行'}</strong></div>
  {event_text}
</div>"""
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>
@page{{size:A4;margin:11mm}}*{{box-sizing:border-box}}body{{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;color:#17262d;margin:0;background:#fff}}header{{background:#102e39;color:#fff;padding:22px 26px;border-bottom:6px solid #d7a12b}}h1{{font-size:25px;margin:0 0 7px;letter-spacing:0}}header p{{margin:4px 0;color:#d7e5e8;font-size:11px}}section{{margin:17px 0 22px;break-inside:avoid}}h2{{font-size:18px;margin:0 0 10px;padding-left:10px;border-left:5px solid #d7a12b}}.note{{font-size:11px;color:#64727b;margin:0 0 9px}}.paused{{border:1px solid #d7e0e2;border-top:4px solid #19766c;padding:18px;background:#f8faf9;font-size:16px;font-weight:700}}.hero-grid{{display:grid;grid-template-columns:1.12fr .88fr;gap:12px}}.holding-card,.comparison-card{{border:1px solid #d5e0e2;padding:16px;background:#f7faf9}}.holding-card{{border-top:5px solid #19766c}}.comparison-card{{border-top:5px solid #d7a12b}}.eyebrow{{font-size:11px;color:#66767d;font-weight:700}}.holding-name{{font-size:24px;font-weight:800;margin:5px 0}}.holding-meta{{font-size:11px;color:#66767d}}.holding-price{{margin-top:14px;font-size:13px}}.holding-price b{{font-size:22px;margin-left:5px}}.comparison-row{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #dce4e6;padding:7px 0;font-size:12px}}.comparison-row b{{font-size:17px}}.comparison-row.emphasis{{border-bottom:0;padding-top:10px}}.benchmark-panel{{border:1px solid #d8e1e3;background:#fbfaf5;padding:14px}}.benchmark-title{{display:flex;justify-content:space-between;align-items:flex-end}}.benchmark-title strong{{font-size:21px;color:#a36d00}}.benchmark-title span{{font-size:11px;color:#6e777b}}.benchmark-line{{height:6px;background:linear-gradient(90deg,#d7a12b,#f0ce72);margin:12px 0 10px;border-radius:3px}}.benchmark-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.benchmark-stat{{border-left:3px solid #d7a12b;padding-left:8px}}.benchmark-stat small{{display:block;color:#6f7b80;font-size:9px}}.benchmark-stat b{{font-size:14px}}.market-monitor{{border:1px solid #d6e0e2;border-top:5px solid #71808a;background:#f8faf9;padding:14px}}.market-monitor.watch{{border-top-color:#d7a12b;background:#fffbf1}}.market-monitor.confirmed{{border-top-color:#19766c;background:#f2faf7}}.market-monitor.invalid{{border-top-color:#b23a3a;background:#fff7f7}}.market-monitor-head{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:12px}}.market-monitor-head span{{display:block;font-size:10px;color:#6b777c}}.market-monitor-head b{{font-size:17px}}.market-monitor-head strong{{font-size:23px}}.market-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}.market-grid>div{{background:#fff;border:1px solid #dbe3e5;padding:9px}}.market-grid small,.market-grid span{{display:block;font-size:9px;color:#6c797f}}.market-grid b{{display:block;font-size:14px;margin:3px 0}}.refresh-research{{margin-top:10px;padding:9px 11px;background:#102e39;color:#fff;font-size:10px}}table{{width:100%;border-collapse:collapse;font-size:10px}}th{{background:#edf2f3;color:#28434c;text-align:left;padding:7px 6px;border-bottom:2px solid #9aabb0}}td{{padding:7px 6px;border-bottom:1px solid #dce3e5;vertical-align:top}}td small{{display:block;color:#738087;margin-top:2px}}tbody tr:nth-child(even){{background:#f8faf9}}.history th:nth-child(1),.history th:nth-child(2),.history th:nth-child(3){{white-space:nowrap}}.up{{color:#b22d2d;font-weight:700}}.down{{color:#087e69;font-weight:700}}.flat{{color:#48575e;font-weight:700}}.benchmark{{color:#a36d00;font-weight:700}}.empty{{text-align:center;color:#758188;padding:20px}}.plan{{break-before:page}}.plan-head{{display:flex;justify-content:space-between;padding:12px 14px;background:#102e39;color:#fff;margin-bottom:10px;font-size:11px}}.plan td:first-child{{width:24%}}.plan td:nth-child(2){{white-space:nowrap}}footer{{font-size:9px;color:#7b858a;border-top:1px solid #d6dddf;padding-top:8px;margin-top:16px}}</style></head><body>
<header><h1>{REPORT_TITLE}</h1><p>最新官方收盤資料日：{actual:%Y-%m-%d}</p><p>{escape(MODEL_NAME)}</p></header>
<section><h2>第一部分｜今日實際表現 vs 中位數年化線</h2>{overview}</section>
<section><h2>第二部分｜正式模型唯一 Top1</h2><table><thead><tr><th>股票</th><th>訊號日</th><th>訊號日收盤</th><th>執行日</th><th>最新收盤</th></tr></thead><tbody><tr><td><b>{escape(signal_state['ticker'])} {escape(signal_state['name'])}</b></td><td>{escape(signal_state['signal_date'])}</td><td>{float(signal_state['signal_close']):,.2f}</td><td>{escape(signal_state['execution_date'])}</td><td>{float(signal_state['signal_close']):,.2f}</td></tr></tbody></table></section>
<section><h2>第三部分｜處置股交易可行性</h2>{trade_gate_section}</section>
<section><h2>第四部分｜大盤半年線監測</h2>{market_section}</section>
<section><h2>第五部分｜64條歷史路徑的中位基準</h2>
<div class="benchmark-panel"><div class="benchmark-title"><div><span>期末剩餘資產中位數</span><br><strong>{MEDIAN_ROUTE_FINAL_CAPITAL / 100_000_000:.2f}億元</strong></div><div>年化複合成長率 <b>{MEDIAN_ROUTE_CAGR * 100:.2f}%</b><br>每交易日複合基準 <b>{MEDIAN_ROUTE_DAILY_RATE * 100:.2f}%</b></div></div><div class="benchmark-line"></div>
<div class="benchmark-stats"><div class="benchmark-stat"><small>買入日</small><b>0.00%</b></div><div class="benchmark-stat"><small>TD5參考</small><b>+{benchmark_td5:.2f}%</b></div><div class="benchmark-stat"><small>TD14參考</small><b>+{benchmark_td14:.2f}%</b></div><div class="benchmark-stat"><small>TD22參考</small><b>+{benchmark_td22:.2f}%</b></div></div></div>
<p class="note">基準來自64條不同進場日起始路徑；初始800萬元、每月提領7.5萬元，期末剩餘資產中位數12.52億元。年化線使用各路徑CAGR中位數57.59%換算，不包含已提領現金。</p></section>
<section><h2>第六部分｜每日路徑比較</h2>{history_section}</section>
{plan_block}
{footer_block}</body></html>"""


def _holding_label(latest: dict | None) -> str:
    if not latest:
        return "等待TD1"
    return f"TD{latest.get('model_td', '—')}"


def _daily_gate_text(item: dict, state: dict) -> str:
    pending = state.get("pending_exit")
    if pending and pending.get("decision_date") == item["date"]:
        return f"<b class=\"down\">觸發賣出</b><small>{escape(pending['reason'])}</small>"
    td = int(item.get("model_td") or 0)
    if td <= 5:
        return "通過<small>前5TD -5%未觸發</small>"
    if td < 14:
        return "續抱<small>監控5TD急跌與累積-10%</small>"
    if td == 14:
        return "TD14檢查完成"
    if td < 22:
        return "續抱<small>監控高點回落10%</small>"
    return "TD22檢查完成"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value):+.2f}%"


def _return_class(value: float | None) -> str:
    if value is None or abs(float(value)) < 1e-12:
        return "flat"
    return "up" if float(value) > 0 else "down"


if __name__ == "__main__":
    main()
