from __future__ import annotations

import argparse
import json
from pathlib import Path


HORIZONS = (5, 20, 60, 130)


def materialize(*, as_of_date: str, weekly_root: str | Path,
                daily_source_root: str | Path) -> dict:
    """Build a reproducible research outcome ledger without mutating snapshots."""
    prices: dict[str, dict[str, float]] = {}
    for path in sorted(Path(daily_source_root).glob("????-??-??.json")):
        if path.stem > as_of_date:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("date") != path.stem:
            continue
        for row in payload.get("price_rows", []):
            ticker = str(row.get("ticker", "")).zfill(4)
            close = row.get("close")
            if ticker and close not in {None, ""}:
                prices.setdefault(ticker, {})[path.stem] = float(close)

    rows = []
    for path in sorted(Path(weekly_root).glob("weekly_snapshot_????-??-??.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        snapshot_date = str(snapshot.get("date", ""))[:10]
        if not snapshot_date or snapshot_date > as_of_date:
            continue
        for item in snapshot.get("rows", []):
            ticker = str(item.get("ticker", "")).zfill(4)
            signal_close = item.get("raw_close")
            future_dates = sorted(day for day in prices.get(ticker, {}) if day > snapshot_date)
            for horizon in HORIZONS:
                if signal_close in {None, 0}:
                    status, exit_date, exit_close, forward_return = "SIGNAL_PRICE_MISSING", None, None, None
                elif len(future_dates) < horizon:
                    status, exit_date, exit_close, forward_return = "PENDING", None, None, None
                else:
                    exit_date = future_dates[horizon - 1]
                    exit_close = prices[ticker][exit_date]
                    forward_return = exit_close / float(signal_close) - 1
                    status = "READY"
                rows.append({
                    "snapshot_date": snapshot_date,
                    "ticker": ticker,
                    "horizon_td": horizon,
                    "signal_close": signal_close,
                    "exit_date": exit_date,
                    "exit_close": exit_close,
                    "forward_return": forward_return,
                    "status": status,
                })
    return {
        "model": "R1",
        "as_of_date": as_of_date,
        "horizon_semantics": "exact Nth later Taiwan trading observation, close-to-close, research only",
        "rows": rows,
        "ready_count": sum(row["status"] == "READY" for row in rows),
        "pending_count": sum(row["status"] == "PENDING" for row in rows),
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 forward research outcomes.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--weekly-root", default="data/r1/weekly")
    parser.add_argument("--daily-source-root", default="data/r1/daily_sources")
    parser.add_argument("--output", default="data/r1/forward_outcomes.json")
    args = parser.parse_args()
    payload = materialize(
        as_of_date=args.date,
        weekly_root=args.weekly_root,
        daily_source_root=args.daily_source_root,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
