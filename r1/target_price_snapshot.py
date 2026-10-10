from __future__ import annotations

import argparse

from r1.target_price_consensus import write_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize weekly PIT target-price consensus.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--evidence", default="data/r1/target_prices/evidence.csv")
    parser.add_argument("--output", default="data/r1/target_prices/latest.json")
    args = parser.parse_args()
    payload = write_snapshot(
        date=args.date, market_path=args.market, config_path=args.config,
        evidence_path=args.evidence, output_path=args.output,
    )
    print(f"{args.output}: {payload['ready_ticker_count']}/{payload['requested_ticker_count']} READY")


if __name__ == "__main__":
    main()
