from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

import pandas as pd

from .base_cycle_daily_report import (
    ReportDataNotReady,
    load_official_prices_and_turnover,
)


REPORT_TITLE = "最新版個股模型 V4-D｜Top1 每日追蹤"
MODEL_NAME = (
    "全市場硬篩選＋基期Top1｜TD1～5 -5%／5TD -10%／累積 -10%／"
    "TD14未達 +5%；曾達 +10%者改由高點回落10%管理／"
    "TD22未曾達 +10%且當下未達 +8%退出"
)


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


def update_state(
    state: dict,
    *,
    mark_date: str,
    close: float,
    prior_close: float | None,
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
            "cumulative_return_pct": (
                (float(close) / float(state["entry_close"]) - 1) * 100
                if state.get("entry_close") not in (None, 0)
                else None
            ),
        }
    state["last_report_date"] = mark_date
    return state


def tracking_rows(state: dict) -> list[dict]:
    rows = []
    for day, item in sorted(state.get("daily_marks", {}).items()):
        rows.append(
            {
                "date": day,
                "ticker": state["ticker"],
                "name": state["name"],
                "close": item["close"],
                "daily_return_pct": item.get("daily_return_pct"),
                "cumulative_return_pct": item.get("cumulative_return_pct"),
            }
        )
    return rows


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
    state = update_state(
        state,
        mark_date=actual.strftime("%Y-%m-%d"),
        close=float(latest["close"]),
        prior_close=prior_close,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = tracking_rows(state)
    tracking_output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(tracking_output, index=False, encoding="utf-8-sig")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(actual, state, rows), encoding="utf-8")
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


def render_html(actual: pd.Timestamp, state: dict, rows: list[dict]) -> str:
    status = "持有中" if state["status"] == "holding" else "等待執行日收盤"
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
        f"{float(latest['cumulative_return_pct']):+.2f}%"
        if latest and latest.get("cumulative_return_pct") is not None
        else "尚未開始"
    )
    history = "".join(
        "<tr>"
        f"<td>{escape(item['date'])}</td>"
        f"<td>{float(item['close']):,.2f}</td>"
        f"<td class=\"{_return_class(item.get('daily_return_pct'))}\">{_pct(item.get('daily_return_pct'))}</td>"
        f"<td class=\"{_return_class(item.get('cumulative_return_pct'))}\">{_pct(item.get('cumulative_return_pct'))}</td>"
        "</tr>"
        for item in rows
    ) or '<tr><td colspan="4" class="empty">2026-07-27 收盤後建立第一筆正式交易紀錄。</td></tr>'
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>
@page{{size:A4;margin:12mm}}*{{box-sizing:border-box}}body{{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;color:#1c2730;margin:0;background:#fff}}header{{background:#102e39;color:#fff;padding:24px 28px;border-bottom:6px solid #d7a12b}}h1{{font-size:26px;margin:0 0 8px}}header p{{margin:4px 0;color:#d7e5e8;font-size:12px}}section{{margin:18px 0 24px;break-inside:avoid}}h2{{font-size:19px;margin:0 0 10px;padding-left:10px;border-left:5px solid #d7a12b}}.note{{font-size:12px;color:#64727b;margin:0 0 10px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.card{{border:1px solid #d7e0e2;border-top:4px solid #19766c;padding:12px;background:#f8faf9}}.label{{font-size:11px;color:#68767c}}.value{{font-size:19px;font-weight:700;margin-top:4px}}table{{width:100%;border-collapse:collapse;font-size:12px}}th{{background:#edf2f3;color:#28434c;text-align:left;padding:9px 8px;border-bottom:2px solid #9aabb0}}td{{padding:9px 8px;border-bottom:1px solid #dce3e5}}tbody tr:nth-child(even){{background:#f8faf9}}.up{{color:#b22d2d;font-weight:700}}.down{{color:#087e69;font-weight:700}}.flat{{color:#48575e;font-weight:700}}.empty{{text-align:center;color:#758188;padding:20px}}footer{{font-size:10px;color:#7b858a;border-top:1px solid #d6dddf;padding-top:8px}}</style></head><body>
<header><h1>{REPORT_TITLE}</h1><p>最新官方收盤資料日：{actual:%Y-%m-%d}</p><p>{escape(MODEL_NAME)}</p></header>
<section><h2>第一部分｜模型與部位摘要</h2><div class="cards"><div class="card"><div class="label">目前狀態</div><div class="value">{status}</div></div><div class="card"><div class="label">執行基準價</div><div class="value">{entry_close}</div></div><div class="card"><div class="label">交易後累積漲跌</div><div class="value">{latest_return}</div></div></div><p class="note">訊號使用收盤資料，下一個台股交易日執行；未取得執行日官方收盤前不計算交易績效。</p></section>
<section><h2>第二部分｜正式模型唯一 Top1</h2><table><thead><tr><th>股票</th><th>訊號日</th><th>訊號日收盤</th><th>執行日</th><th>最新收盤</th></tr></thead><tbody><tr><td><b>{escape(state['ticker'])} {escape(state['name'])}</b></td><td>{escape(state['signal_date'])}</td><td>{float(state['signal_close']):,.2f}</td><td>{escape(state['execution_date'])}</td><td>{latest_close}</td></tr></tbody></table></section>
<section><h2>第三部分｜順德交易後每日漲跌追蹤</h2><p class="note">單日漲跌以上一個台股交易日收盤計算；累積漲跌以2026-07-27正式執行收盤為基準。週末與休市日不列入。</p><table><thead><tr><th>交易日</th><th>收盤</th><th>單日漲跌</th><th>交易後累積漲跌</th></tr></thead><tbody>{history}</tbody></table></section>
<footer>私人研究報告。Top1 為 V4-D 凍結規則在 2026-07-24 收盤後的結果；報告只追蹤唯一正式部位，不再列 Top10、Top3 或舊版 V_BASE 名單。</footer></body></html>"""


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value):+.2f}%"


def _return_class(value: float | None) -> str:
    if value is None or abs(float(value)) < 1e-12:
        return "flat"
    return "up" if float(value) > 0 else "down"


if __name__ == "__main__":
    main()
