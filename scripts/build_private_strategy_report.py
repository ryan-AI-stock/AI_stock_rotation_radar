from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import date
from pathlib import Path

import requests

from rotation_radar.models import Report
from rotation_radar.private_strategies import (
    build_private_strategy_checkpoints,
    required_private_strategy_symbols,
)
from rotation_radar.report import render_private_signal_report


TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="reports/private_strategy_daily.html")
    parser.add_argument("--state", default="data/private_strategy_state.json")
    parser.add_argument("--next-execution-date", required=True)
    args = parser.parse_args()

    report_date = date.fromisoformat(args.date)
    months = sorted(
        {
            report_date.replace(day=1),
            date(report_date.year, report_date.month - 1, 1)
            if report_date.month > 1
            else date(report_date.year - 1, 12, 1),
            date(report_date.year, report_date.month - 2, 1)
            if report_date.month > 2
            else date(report_date.year - 1, report_date.month + 10, 1),
        }
    )
    history = {
        symbol: _fetch_symbol(symbol, months, args.date)
        for symbol in sorted(required_private_strategy_symbols())
    }
    checkpoints = build_private_strategy_checkpoints(
        history,
        report_date=args.date,
        next_execution_date=args.next_execution_date,
        state_path=args.state,
    )
    report = Report(
        title="私人策略操作總覽",
        generated_at=args.date,
        market_view="私人策略",
        sector_results=[],
        stock_results=[],
        private_strategies=checkpoints,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_private_signal_report(report), encoding="utf-8")
    manifest = output.with_suffix(".json")
    manifest.write_text(
        json.dumps(
            {
                "report_date": args.date,
                "next_execution_date": args.next_execution_date,
                "source": "TWSE STOCK_DAY official raw close",
                "source_url": TWSE_STOCK_DAY_URL,
                "symbols": len(history),
                "rows": sum(len(rows) for rows in history.values()),
                "strategies": checkpoints,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output)
    print(manifest)


def _fetch_symbol(symbol: str, months: list[date], report_date: str) -> list[dict[str, float | str]]:
    rows: dict[str, dict[str, float | str]] = {}
    for month in months:
        query = urllib.parse.urlencode(
            {"date": month.strftime("%Y%m%d"), "stockNo": symbol, "response": "json"}
        )
        response = requests.get(
            f"{TWSE_STOCK_DAY_URL}?{query}",
            headers={"User-Agent": "AI_stock_rotation_radar/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("stat") != "OK":
            continue
        fields = list(payload.get("fields") or [])
        for values in payload.get("data") or []:
            raw = dict(zip(fields, values))
            day = _roc_date(str(raw.get("日期", "")))
            if not day or day > report_date:
                continue
            close = _number(raw.get("收盤價"))
            if close is None:
                continue
            rows[day] = {
                "date": day,
                "open": _number(raw.get("開盤價")) or close,
                "high": _number(raw.get("最高價")) or close,
                "low": _number(raw.get("最低價")) or close,
                "close": close,
            }
    ordered = [rows[key] for key in sorted(rows)]
    if len(ordered) < 20:
        raise RuntimeError(f"{symbol} has only {len(ordered)} official rows through {report_date}")
    return ordered


def _roc_date(value: str) -> str:
    try:
        year, month, day = (int(part) for part in value.split("/"))
    except (TypeError, ValueError):
        return ""
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def _number(value: object) -> float | None:
    raw = str(value or "").replace(",", "").strip()
    if raw in {"", "--", "-", "X"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


if __name__ == "__main__":
    main()
