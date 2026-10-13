from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from r1.config import R1Config


def build_actual_account(*, date: str, config_path: str | Path,
                         market_path: str | Path, cash: float | None = None,
                         broker_snapshot_path: str | Path | None = None,
                         supplemental_positions_path: str | Path | None = None,
                         supplemental_market_path: str | Path | None = None) -> dict[str, Any]:
    """Value confirmed shares even when the broker cash balance is not reconciled."""
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    closes = {str(row["ticker"]).zfill(4): row.get("raw_close") for row in market.get("rows", [])}
    if supplemental_market_path and Path(supplemental_market_path).exists():
        supplemental_market = json.loads(Path(supplemental_market_path).read_text(encoding="utf-8"))
        for row in supplemental_market.get("rows", []):
            ticker = str(row.get("ticker", "")).upper()
            ticker = "00631L" if ticker in {"00631", "00631L"} else ticker.zfill(4)
            closes[ticker] = row.get("raw_close")
    positions, gaps = [], []
    equity_market_value = 0.0
    for security in config.securities:
        if security.shares <= 0:
            continue
        close = closes.get(security.ticker)
        if not isinstance(close, (int, float)):
            gaps.append({"ticker": security.ticker, "reason": "EXACT_OFFICIAL_CLOSE_MISSING"})
            market_value = None
        else:
            market_value = float(close) * security.shares
            equity_market_value += market_value
        positions.append({
            "ticker": security.ticker, "company": security.company, "shares": security.shares,
            "raw_close": close, "market_value": market_value,
        })
    if supplemental_positions_path and Path(supplemental_positions_path).exists():
        supplemental = json.loads(Path(supplemental_positions_path).read_text(encoding="utf-8"))
        if str(supplemental.get("as_of_date", "")) <= date:
            configured = {row["ticker"] for row in positions}
            for item in supplemental.get("positions", []):
                ticker = str(item.get("ticker", "")).upper()
                if ticker in configured:
                    raise ValueError(f"supplemental actual position duplicates configured holding: {ticker}")
                shares = item.get("shares")
                close = closes.get(ticker)
                if not isinstance(shares, (int, float)) or shares <= 0:
                    raise ValueError(f"invalid supplemental actual shares: {ticker}")
                if not isinstance(close, (int, float)):
                    gaps.append({"ticker": ticker, "reason": "EXACT_OFFICIAL_CLOSE_MISSING"})
                    market_value = None
                else:
                    market_value = float(close) * float(shares)
                    equity_market_value += market_value
                positions.append({
                    "ticker": ticker, "company": item.get("company", ticker), "shares": shares,
                    "raw_close": close, "market_value": market_value,
                    "average_cost": item.get("average_cost"), "source": supplemental.get("source"),
                })
    visible_positions_market_value = equity_market_value
    broker_snapshot = None
    if broker_snapshot_path and Path(broker_snapshot_path).exists():
        candidate = json.loads(Path(broker_snapshot_path).read_text(encoding="utf-8"))
        if candidate.get("as_of_date") == date:
            broker_snapshot = candidate
            reported = candidate.get("owner_equity_market_value", candidate.get("reported_equity_market_value"))
            if isinstance(reported, (int, float)):
                equity_market_value = float(reported)
    holding_detail_gap = bool(broker_snapshot and broker_snapshot.get("status") != "READY")
    cash_ready = isinstance(cash, (int, float))
    nav = equity_market_value + float(cash) if cash_ready and not gaps else None
    return {
        "date": date, "positions": positions, "equity_market_value": equity_market_value,
        "visible_positions_market_value": visible_positions_market_value,
        "cash": cash, "nav": nav,
        "status": "HOLDING_DETAIL_RECONCILIATION_REQUIRED" if holding_detail_gap else
                  "READY" if nav is not None else "CASH_RECONCILIATION_REQUIRED" if not gaps else "PRICE_DATA_MISSING",
        "gaps": gaps
                + ([] if cash_ready else [{"field": "cash", "reason": "USER_CONFIRMED_CASH_NOT_AVAILABLE"}])
                + ([{"field": "holdings", "reason": "BROKER_TOTAL_EXCEEDS_VISIBLE_POSITION_DETAILS",
                     "amount": broker_snapshot.get("unidentified_market_value_gap")}] if holding_detail_gap else []),
        "source": "r1_config_confirmed_shares_plus_official_raw_close",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 actual-account market value.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--cash", type=float)
    parser.add_argument("--cash-ledger", default="data/r1/actual_cash_flows.json")
    parser.add_argument("--broker-snapshot", default="data/r1/actual_holdings_snapshot_20261008.json")
    parser.add_argument("--supplemental-positions", default="data/r1/actual_supplemental_positions.json")
    parser.add_argument("--supplemental-market", default="data/r1/benchmark_market_latest.json")
    parser.add_argument("--output", default="data/r1/actual_account_state.json")
    args = parser.parse_args()
    cash = args.cash
    cash_ledger = Path(args.cash_ledger)
    if cash is None and cash_ledger.exists():
        ledger = json.loads(cash_ledger.read_text(encoding="utf-8"))
        if str(ledger.get("as_of_date", "")) <= args.date:
            confirmed_cash = ledger.get("confirmed_cash")
            if isinstance(confirmed_cash, (int, float)):
                cash = float(confirmed_cash)
    payload = build_actual_account(date=args.date, config_path=args.config, market_path=args.market, cash=cash,
                                   broker_snapshot_path=args.broker_snapshot,
                                   supplemental_positions_path=args.supplemental_positions,
                                   supplemental_market_path=args.supplemental_market)
    if cash_ledger.exists() and isinstance(payload.get("nav"), (int, float)):
        ledger = json.loads(cash_ledger.read_text(encoding="utf-8"))
        exclusions = ledger.get("comparison_scope_exclusions", {})
        excluded_equity = 0.0
        positions = {row["ticker"]: row for row in payload.get("positions", [])}
        for exclusion in exclusions.get("positions", []):
            row = positions.get(str(exclusion.get("ticker", "")).zfill(4))
            shares = exclusion.get("shares")
            close = row.get("raw_close") if row else None
            if isinstance(shares, (int, float)) and isinstance(close, (int, float)):
                excluded_equity += float(shares) * float(close)
        excluded_cash_income = sum(
            float(row["amount"]) for row in exclusions.get("cash_income", [])
            if str(row.get("date", "")) <= args.date and isinstance(row.get("amount"), (int, float))
        )
        payload["comparison_excluded_equity"] = excluded_equity
        payload["comparison_excluded_cash_income"] = excluded_cash_income
        payload["comparison_equity_market_value"] = payload["equity_market_value"] - excluded_equity
        payload["comparison_cash"] = float(payload["cash"]) - excluded_cash_income
        payload["comparison_nav"] = payload["nav"] - excluded_equity - excluded_cash_income
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if payload["status"] == "PRICE_DATA_MISSING":
        raise SystemExit(75)
    print(output)


if __name__ == "__main__":
    main()
