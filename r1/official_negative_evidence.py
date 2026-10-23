from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def build_official_negative_evidence(*, as_of_date: str, monthly_revenue: dict[str, Any],
                                     financial_quality: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    monthly_rows = {str(row.get("ticker", "")).zfill(4): row
                    for row in monthly_revenue.get("rows", [])}
    financial_rows = {str(row.get("ticker", "")).zfill(4): row
                      for row in financial_quality.get("rows", [])}
    tickers = sorted(set(monthly_rows) | set(financial_rows))
    for ticker in tickers:
        monthly = monthly_rows.get(ticker, {})
        observations = sorted(
            monthly.get("observations") or [], key=lambda row: row.get("revenue_year_month", ""),
        )[-3:]
        if len(observations) == 3 and all(row.get("yoy") is not None for row in observations):
            values = [float(row["yoy"]) for row in observations]
            if sum(values) / 3.0 < 0 and values[-1] < 0:
                latest = observations[-1]
                events.append({
                    "ticker": ticker,
                    "event_type": "MONTHLY_REVENUE_CONTRACTION",
                    "available_at": latest["available_date"],
                    "source_url": latest["source_url"],
                    "source_family": "MOPS_MONTHLY_REVENUE",
                    "facts": {"three_month_average_yoy": round(sum(values) / 3.0, 8),
                              "latest_yoy": values[-1]},
                })
        financial = financial_rows.get(ticker, {})
        metrics = financial.get("metrics") or {}
        source_url = financial.get("source_url")
        if financial.get("status") == "READY" and source_url:
            revenue_yoy = metrics.get("revenue_yoy_pct")
            eps_yoy = metrics.get("eps_yoy_pct")
            if revenue_yoy is not None and eps_yoy is not None \
                    and float(revenue_yoy) < 0 and float(eps_yoy) < 0:
                events.append({
                    "ticker": ticker,
                    "event_type": "FINANCIAL_EARNINGS_CONTRACTION",
                    "available_at": financial_quality.get("as_of_date", as_of_date),
                    "source_url": source_url,
                    "source_family": "MOPS_FINANCIAL_STATEMENTS",
                    "facts": {"revenue_yoy_pct": revenue_yoy, "eps_yoy_pct": eps_yoy},
                })
            gross_change = metrics.get("gross_margin_change_pp")
            operating_change = metrics.get("operating_margin_change_pp")
            operating_cash_flow = metrics.get("operating_cash_flow")
            if all(value is not None for value in (gross_change, operating_change, operating_cash_flow)) \
                    and float(gross_change) < 0 and float(operating_change) < 0 \
                    and float(operating_cash_flow) < 0:
                events.append({
                    "ticker": ticker,
                    "event_type": "FINANCIAL_CASH_MARGIN_STRESS",
                    "available_at": financial_quality.get("as_of_date", as_of_date),
                    "source_url": source_url,
                    "source_family": "MOPS_FINANCIAL_STATEMENTS",
                    "facts": {"gross_margin_change_pp": gross_change,
                              "operating_margin_change_pp": operating_change,
                              "operating_cash_flow": operating_cash_flow},
                })
    return {
        "model": "R1",
        "version": "r1-official-negative-evidence-v0.1",
        "date": as_of_date,
        "status": "diagnostic_gate_only",
        "rows": events,
        "covered_ticker_count": len(tickers),
        "event_ticker_count": len({row["ticker"] for row in events}),
        "event_count": len(events),
        "future_data_violation_count": sum(row["available_at"] > as_of_date for row in events),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic official R1 negative evidence.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--monthly-revenue", default="data/r1/monthly_revenue/latest.json")
    parser.add_argument("--financial-quality", default="data/r1/financial_quality_latest.json")
    parser.add_argument("--output", default="data/r1/official_negative_evidence.json")
    args = parser.parse_args()
    payload = build_official_negative_evidence(
        as_of_date=args.date,
        monthly_revenue=json.loads(Path(args.monthly_revenue).read_text(encoding="utf-8")),
        financial_quality=json.loads(Path(args.financial_quality).read_text(encoding="utf-8")),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "events": payload["event_count"],
                      "tickers": payload["event_ticker_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
