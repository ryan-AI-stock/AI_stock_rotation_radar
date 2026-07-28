from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from html import escape
from pathlib import Path

import pandas as pd

from .base_cycle_daily_report import (
    ReportDataNotReady,
    load_official_prices_and_turnover,
)
from .schedule_gate import fetch_twse_calendar, is_trading_day


REPORT_TITLE = "最新版個股模型 V4-D｜Top1 每日追蹤"
MODEL_NAME = (
    "全市場硬篩選＋基期Top1｜TD1～5 -5%／5TD -10%／累積 -10%／"
    "TD14未達 +5%；曾達 +10%者改由高點回落10%管理／"
    "TD22未曾達 +10%且當下未達 +8%退出"
)
BUY_RATE = 0.001425 + 0.001
SELL_RATE = 0.001425 + 0.003 + 0.001
POSITION_STREAM_PAUSED = True
POSITION_STREAM_MESSAGE = "模型尚未正式買入，此訊息流空。"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the private V4-D Top1 position tracking report."
    )
    parser.add_argument("--date", required=True, help="Taiwan trading date, YYYY-MM-DD")
    parser.add_argument("--source-repo", default=".")
    parser.add_argument("--state", default="data/formal_v4d_top1_state.json")
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
    for index, (_day, item) in enumerate(ordered):
        close = float(item["close"])
        net = close / float(entry) * (1 - SELL_RATE) / (1 + BUY_RATE) - 1
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
    return None


def tracking_rows(state: dict) -> list[dict]:
    rows = []
    for day, item in sorted(state.get("daily_marks", {}).items()):
        rows.append(
            {
                "date": day,
                "ticker": state["ticker"],
                "name": state["name"],
                "d_index": item.get("d_index"),
                "model_td": item.get("model_td"),
                "close": item["close"],
                "daily_return_pct": item.get("daily_return_pct"),
                "cumulative_return_pct": item.get("cumulative_return_pct"),
                "after_cost_return_pct": item.get("after_cost_return_pct"),
                "peak_after_cost_return_pct": item.get(
                    "peak_after_cost_return_pct"
                ),
                "rolling_5td_return_pct": item.get("rolling_5td_return_pct"),
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
    days = _trading_dates_from(start, 22, closed_dates=closed_dates)
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
            "stage": "第四道｜發動檢查",
            "range": f"{days[13]:%m/%d}",
            "day": "TD14",
            "rule": "after-cost 未達 +5%",
            "action": "未曾達+10%則下一交易日賣出",
        },
        {
            "stage": "第五道｜獲利保護",
            "range": f"{days[13]:%m/%d} 起每日",
            "day": "TD14起",
            "rule": "曾達+10%後，自高點回落10%",
            "action": "收盤成立，下一交易日賣出",
        },
        {
            "stage": "第六道｜最終檢查",
            "range": f"{days[21]:%m/%d}",
            "day": "TD22",
            "rule": "從未達+10%，且當下未達+8%",
            "action": "收盤成立，下一交易日賣出",
        },
    ]


def build_daily_report(
    *,
    report_date: str,
    source_repo: Path,
    state_path: Path,
    output_path: Path,
    tracking_output: Path,
    source_cache: Path,
    offline: bool = False,
) -> dict:
    target = pd.Timestamp(report_date)
    state = load_state(state_path)
    require_current_top1_signal(state, target)
    current = pd.DataFrame(
        [
            {
                "ticker": str(state["ticker"]).zfill(4),
                "name": state["name"],
                "market": state.get("market", "TWSE"),
            }
        ]
    )
    official, _ = load_official_prices_and_turnover(
        source_repo=source_repo,
        target=target,
        current=current,
        source_cache=source_cache,
        offline=offline,
    )
    official["ticker"] = official["ticker"].astype(str).str.zfill(4)
    official["date"] = pd.to_datetime(official["date"])
    ticker_rows = official[
        official["ticker"].eq(str(state["ticker"]).zfill(4))
        & official["date"].le(target)
    ].dropna(subset=["close"]).sort_values("date")
    if ticker_rows.empty:
        raise ReportDataNotReady(f"No official close available for {state['ticker']}")
    latest = ticker_rows.iloc[-1]
    if latest["date"] < target and not offline:
        raise ReportDataNotReady(
            f"Target-date official close is not ready for {state['ticker']}"
        )
    prior = ticker_rows[ticker_rows["date"].lt(latest["date"])]
    prior_close = float(prior.iloc[-1]["close"]) if not prior.empty else None
    actual = pd.Timestamp(latest["date"])
    if not POSITION_STREAM_PAUSED:
        state = update_state(
            state,
            mark_date=actual.strftime("%Y-%m-%d"),
            close=float(latest["close"]),
            prior_close=prior_close,
            closed_dates=fetch_twse_calendar()[1],
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    rows = tracking_rows(state)
    tracking_output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(tracking_output, index=False, encoding="utf-8-sig")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_html(actual, state, rows, closed_dates=fetch_twse_calendar()[1]),
        encoding="utf-8",
    )
    return {
        "status": "complete",
        "requested_report_date": report_date,
        "actual_report_date": actual.strftime("%Y-%m-%d"),
        "model": "V4-D",
        "top1_ticker": state["ticker"],
        "top1_name": state["name"],
        "signal_date": state["signal_date"],
        "execution_date": state["execution_date"],
        "position_status": state["status"],
        "tracking_row_count": len(rows),
        "future_data_violation_count": 0,
    }


def build_pending_seed_report(
    *,
    state_path: Path,
    output_path: Path,
    tracking_output: Path,
) -> dict:
    state = load_state(state_path)
    rows = tracking_rows(state)
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
        render_html(pd.Timestamp(state["signal_date"]), state, rows),
        encoding="utf-8",
    )
    return {
        "status": "complete_pending_execution_close",
        "actual_report_date": state["signal_date"],
        "model": "V4-D",
        "top1_ticker": state["ticker"],
        "top1_name": state["name"],
        "execution_date": state["execution_date"],
        "position_status": state["status"],
        "tracking_row_count": len(rows),
        "future_data_violation_count": 0,
    }


def render_html(
    actual: pd.Timestamp,
    state: dict,
    rows: list[dict],
    *,
    closed_dates: set[date] | None = None,
) -> str:
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
    latest = rows[-1] if rows else None
    latest_close = (
        f"{float(latest['close']):,.2f}" if latest else f"{float(state['signal_close']):,.2f}"
    )
    latest_return = (
        f"{float(latest['after_cost_return_pct']):+.2f}%"
        if latest and latest.get("after_cost_return_pct") is not None
        else "尚未開始"
    )
    next_action = f"{state['execution_date']} 執行買入並計為TD1"
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
        f"<td class=\"{_return_class(item.get('daily_return_pct'))}\">{_pct(item.get('daily_return_pct'))}</td>"
        f"<td class=\"{_return_class(item.get('after_cost_return_pct'))}\">{_pct(item.get('after_cost_return_pct'))}</td>"
        f"<td>{_daily_gate_text(item, state)}</td>"
        "</tr>"
        for item in rows
    ) or (
        '<tr><td colspan="6" class="empty">'
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
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>
@page{{size:A4;margin:12mm}}*{{box-sizing:border-box}}body{{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;color:#1c2730;margin:0;background:#fff}}header{{background:#102e39;color:#fff;padding:24px 28px;border-bottom:6px solid #d7a12b}}h1{{font-size:26px;margin:0 0 8px}}header p{{margin:4px 0;color:#d7e5e8;font-size:12px}}section{{margin:18px 0 24px;break-inside:avoid}}h2{{font-size:19px;margin:0 0 10px;padding-left:10px;border-left:5px solid #d7a12b}}.note{{font-size:12px;color:#64727b;margin:0 0 10px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.card{{border:1px solid #d7e0e2;border-top:4px solid #19766c;padding:12px;background:#f8faf9}}.card.action{{border-top-color:#d7a12b}}.label{{font-size:11px;color:#68767c}}.value{{font-size:17px;font-weight:700;margin-top:4px}}table{{width:100%;border-collapse:collapse;font-size:11px}}th{{background:#edf2f3;color:#28434c;text-align:left;padding:8px 7px;border-bottom:2px solid #9aabb0}}td{{padding:8px 7px;border-bottom:1px solid #dce3e5;vertical-align:top}}td small{{display:block;color:#738087;margin-top:2px}}tbody tr:nth-child(even){{background:#f8faf9}}.up{{color:#b22d2d;font-weight:700}}.down{{color:#087e69;font-weight:700}}.flat{{color:#48575e;font-weight:700}}.empty{{text-align:center;color:#758188;padding:20px}}.plan{{break-before:page}}.plan td:first-child{{width:24%}}.plan td:nth-child(2){{white-space:nowrap}}footer{{font-size:10px;color:#7b858a;border-top:1px solid #d6dddf;padding-top:8px}}</style></head><body>
<header><h1>{REPORT_TITLE}</h1><p>最新官方收盤資料日：{actual:%Y-%m-%d}</p><p>{escape(MODEL_NAME)}</p></header>
<section><h2>第一部分｜今天只看這四件事</h2><div class="card"><div class="value">{escape(POSITION_STREAM_MESSAGE)}</div></div></section>
<section><h2>第二部分｜正式模型唯一 Top1</h2><table><thead><tr><th>股票</th><th>訊號日</th><th>訊號日收盤</th><th>執行日</th><th>最新收盤</th></tr></thead><tbody><tr><td><b>{escape(state['ticker'])} {escape(state['name'])}</b></td><td>{escape(state['signal_date'])}</td><td>{float(state['signal_close']):,.2f}</td><td>{escape(state['execution_date'])}</td><td>{latest_close}</td></tr></tbody></table></section>
<section><h2>第三部分｜每日持倉紀錄</h2><div class="card"><div class="value">{escape(POSITION_STREAM_MESSAGE)}</div></div></section>
<section class="plan"><h2>第四部分｜V4-D完整監控計畫</h2><div class="card"><div class="value">{escape(POSITION_STREAM_MESSAGE)}</div></div></section>
<footer>私人研究報告。Top1 為 V4-D 凍結規則在 {escape(state['signal_date'])} 收盤後的結果；報告只追蹤唯一正式部位，不再列 Top10、Top3 或舊版 V_BASE 名單。</footer></body></html>"""


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
