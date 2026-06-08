from __future__ import annotations

import argparse

from .top3_capital_flow import build_formal_top3_capital_flow_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build formal top3 capital-flow package for BACKTEST_LAB.")
    parser.add_argument(
        "--output-dir",
        default="data/history_replay/formal_top3_capital_flow_2022_2023",
    )
    parser.add_argument("--start-date", default="2022-01-03")
    parser.add_argument("--end-date", default="2023-12-29")
    args = parser.parse_args()

    readiness = build_formal_top3_capital_flow_package(
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"Saved {args.output_dir}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"trading_day_count={readiness['trading_day_count']}")
    print(f"blocking_issues={len(readiness['blocking_issues'])}")


if __name__ == "__main__":
    main()
