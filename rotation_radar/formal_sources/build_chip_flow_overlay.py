from __future__ import annotations

import argparse

from .chip_flow_overlay import build_chip_flow_overlay_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chip-flow overlay package for BACKTEST_LAB.")
    parser.add_argument(
        "--output-dir",
        default="data/formal_sources/chip_flow_overlay_2021_2023",
    )
    parser.add_argument("--start-date", default="2021-12-01")
    parser.add_argument("--end-date", default="2023-12-29")
    parser.add_argument("--trading-day-count", type=int, default=507)
    args = parser.parse_args()

    readiness = build_chip_flow_overlay_package(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        trading_day_count=args.trading_day_count,
    )
    print(f"Saved {args.output_dir}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"symbol_count={readiness['symbol_count']}")
    print(f"trading_day_count={readiness['trading_day_count']}")
    print(f"missing_symbol_date_count={readiness['missing_symbol_date_count']}")
    print(f"blocking_issues={len(readiness['blocking_issues'])}")


if __name__ == "__main__":
    main()
