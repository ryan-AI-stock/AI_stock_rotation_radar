from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from rotation_radar.base_cycle_daily_report import load_official_prices_and_turnover


TICKERS = {"00631": "元大台灣50正2", "2308": "台達電", "2317": "鴻海"}


def build_snapshot(*, date: str, source_repo: str | Path = ".",
                   source_cache: str | Path = "data/current_base_cycle_source_cache") -> dict:
    target = pd.Timestamp(date)
    official, _ = load_official_prices_and_turnover(
        source_repo=Path(source_repo), target=target,
        current=pd.DataFrame(columns=["ticker", "name", "market"]),
        source_cache=Path(source_cache), offline=False,
    )
    def normalize(value: object) -> str:
        token = str(value).replace(".0", "").upper()
        if token in {"00631L", "00631"} or token.lstrip("0") in {"631", "631L"}:
            return "00631"
        return token.zfill(4)

    official["ticker"] = official.ticker.map(normalize)
    official["date"] = pd.to_datetime(official.date)
    rows, gaps = [], []
    for ticker, company in TICKERS.items():
        exact = official[(official.ticker == ticker) & (official.date == target)]
        if exact.empty:
            gaps.append({"ticker": ticker, "status": "DATA_MISSING"})
            continue
        rows.append({"date": date, "ticker": ticker, "company": company,
                     "raw_close": float(exact.iloc[-1].close), "source": "official_raw_close"})
    return {"date": date, "rows": rows, "gaps": gaps,
            "requested_ticker_count": len(TICKERS), "actual_ticker_count": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize exact-date prices for R1 comparison benchmarks.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="data/r1/benchmark_market_latest.json")
    args = parser.parse_args()
    payload = build_snapshot(date=args.date)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if payload["actual_ticker_count"] != payload["requested_ticker_count"]:
        raise SystemExit(75)
    print(output)


if __name__ == "__main__":
    main()
