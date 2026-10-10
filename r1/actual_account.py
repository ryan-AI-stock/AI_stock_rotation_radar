from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from r1.config import R1Config


def build_actual_account(*, date: str, config_path: str | Path,
                         market_path: str | Path, cash: float | None = None) -> dict[str, Any]:
    """Value confirmed shares even when the broker cash balance is not reconciled."""
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    closes = {str(row["ticker"]).zfill(4): row.get("raw_close") for row in market.get("rows", [])}
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
    cash_ready = isinstance(cash, (int, float))
    nav = equity_market_value + float(cash) if cash_ready and not gaps else None
    return {
        "date": date, "positions": positions, "equity_market_value": equity_market_value,
        "cash": cash, "nav": nav,
        "status": "READY" if nav is not None else "CASH_RECONCILIATION_REQUIRED" if not gaps else "PRICE_DATA_MISSING",
        "gaps": gaps + ([] if cash_ready else [{"field": "cash", "reason": "USER_CONFIRMED_CASH_NOT_AVAILABLE"}]),
        "source": "r1_config_confirmed_shares_plus_official_raw_close",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 actual-account market value.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--cash", type=float)
    parser.add_argument("--output", default="data/r1/actual_account_state.json")
    args = parser.parse_args()
    payload = build_actual_account(date=args.date, config_path=args.config, market_path=args.market, cash=args.cash)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if payload["status"] == "PRICE_DATA_MISSING":
        raise SystemExit(75)
    print(output)


if __name__ == "__main__":
    main()
