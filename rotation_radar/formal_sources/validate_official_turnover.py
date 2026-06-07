from __future__ import annotations

import argparse

from .official_turnover import validate_official_turnover


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate official turnover coverage for formal radar replay.")
    parser.add_argument("--turnover-file", required=True)
    parser.add_argument("--formal-universe", required=True)
    parser.add_argument("--market-universe", default="data/market_universe.generated.csv")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gap-report")
    args = parser.parse_args()

    readiness = validate_official_turnover(
        turnover_file=args.turnover_file,
        formal_universe_path=args.formal_universe,
        market_universe_path=args.market_universe,
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=args.output,
        gap_report_path=args.gap_report,
    )
    print(f"Saved {args.output}")
    if args.gap_report:
        print(f"Saved {args.gap_report}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"coverage_ratio={readiness['coverage_ratio']}")


if __name__ == "__main__":
    main()
