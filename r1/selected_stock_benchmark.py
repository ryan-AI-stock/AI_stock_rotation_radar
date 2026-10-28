from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BASELINE_DATE = "2026-10-28"
EXCLUDED_TICKERS = {"2330", "00631", "00631L"}


def _load(path: str | Path, default: dict[str, Any]) -> dict[str, Any]:
    file = Path(path)
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else default


def build_selected_stock_comparison(*, date: str, actual_account: dict[str, Any],
                                    benchmark_market: dict[str, Any], state: dict[str, Any] | None = None,
                                    cash_ledger: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare the live selected-stock scope with a same-flow fractional 00631L benchmark."""
    if date < BASELINE_DATE:
        return {"date": date, "status": "NOT_STARTED", "baseline_date": BASELINE_DATE}, state or {}
    positions = [row for row in actual_account.get("positions", [])
                 if str(row.get("ticker", "")).upper() not in EXCLUDED_TICKERS]
    gaps = [str(row.get("ticker")) for row in positions if not isinstance(row.get("market_value"), (int, float))]
    actual_value = None if gaps else sum(float(row["market_value"]) for row in positions)
    close = next((row.get("raw_close") for row in benchmark_market.get("rows", [])
                  if str(row.get("ticker", "")).upper() in {"00631", "00631L"}), None)
    if actual_value is None or not isinstance(close, (int, float)) or close <= 0:
        return {"date": date, "status": "DATA_NOT_READY", "baseline_date": BASELINE_DATE,
                "actual_value": actual_value, "benchmark_close": close,
                "gaps": gaps or ["00631L_EXACT_OFFICIAL_CLOSE_MISSING"]}, state or {}
    state = dict(state or {})
    if not state:
        if date != BASELINE_DATE:
            raise ValueError(f"selected-stock benchmark baseline must be initialized on {BASELINE_DATE}")
        state = {"version": "r1-selected-stock-vs-00631l-v1", "baseline_date": BASELINE_DATE,
                 "baseline_actual_value": actual_value, "baseline_00631l_close": float(close),
                 "benchmark_units": actual_value / float(close), "applied_flow_ids": [],
                 "excluded_tickers": ["2330", "00631L"], "unit_policy": "fractional_units_allowed"}
    applied = set(state.get("applied_flow_ids", []))
    applied_flows: list[dict[str, Any]] = []
    for flow in (cash_ledger or {}).get("selected_stock_benchmark_flows", []):
        flow_id, flow_date, amount = str(flow.get("id", "")), str(flow.get("date", "")), flow.get("amount")
        if not flow_id or flow_id in applied or not (BASELINE_DATE < flow_date <= date):
            continue
        if not isinstance(amount, (int, float)):
            raise ValueError(f"invalid selected-stock benchmark flow amount: {flow_id}")
        flow_close = flow.get("official_00631l_close")
        if flow_date == date and not isinstance(flow_close, (int, float)):
            flow_close = close
        if not isinstance(flow_close, (int, float)) or flow_close <= 0:
            raise ValueError(f"selected-stock benchmark flow lacks exact 00631L close: {flow_id}")
        state["benchmark_units"] = float(state["benchmark_units"]) + float(amount) / float(flow_close)
        applied.add(flow_id)
        applied_flows.append({"id": flow_id, "date": flow_date, "amount": float(amount),
                              "official_00631l_close": float(flow_close)})
    state["applied_flow_ids"], state["last_date"] = sorted(applied), date
    benchmark_value = float(state["benchmark_units"]) * float(close)
    baseline = float(state["baseline_actual_value"])
    payload = {"date": date, "status": "READY", "baseline_date": state["baseline_date"],
               "baseline_actual_value": baseline,
               "excluded_tickers": state["excluded_tickers"], "actual_value": actual_value,
               "benchmark_value": benchmark_value, "benchmark_close": float(close),
               "benchmark_units": float(state["benchmark_units"]),
               "difference_actual_minus_benchmark": actual_value - benchmark_value,
               "actual_return_pct": actual_value / baseline - 1,
               "benchmark_return_pct": benchmark_value / baseline - 1,
               "position_count": len(positions), "applied_flows": applied_flows,
               "source_note": "實際持股動態更新；排除台積電與0050正二；同額0050正二允許零股小數"}
    return payload, state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--actual-account", default="data/r1/actual_account_state.json")
    parser.add_argument("--benchmark-market", default="data/r1/benchmark_market_latest.json")
    parser.add_argument("--cash-ledger", default="data/r1/actual_cash_flows.json")
    parser.add_argument("--state", default="data/r1/selected_stock_benchmark_state.json")
    parser.add_argument("--output", default="data/r1/selected_stock_benchmark_latest.json")
    parser.add_argument("--history", default="data/r1/selected_stock_benchmark_history.jsonl")
    args = parser.parse_args()
    state_file = Path(args.state)
    payload, state = build_selected_stock_comparison(
        date=args.date, actual_account=_load(args.actual_account, {}),
        benchmark_market=_load(args.benchmark_market, {"rows": []}), state=_load(state_file, {}),
        cash_ledger=_load(args.cash_ledger, {}))
    if payload.get("status") == "NOT_STARTED":
        return
    if payload.get("status") != "READY":
        raise SystemExit(75)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = Path(args.history)
    existing = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()] if history.exists() else []
    by_date = {str(row["date"]): row for row in existing}
    by_date[args.date] = payload
    history.write_text("".join(json.dumps(by_date[key], ensure_ascii=False) + "\n" for key in sorted(by_date)), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
