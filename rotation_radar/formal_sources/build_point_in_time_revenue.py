from __future__ import annotations

import argparse

from .point_in_time_revenue import build_point_in_time_revenue_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MOPS point-in-time monthly revenue CSV for formal radar replay.")
    parser.add_argument("--formal-universe", required=True)
    parser.add_argument("--market-universe", default="data/market_universe.generated.csv")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gap-report", required=True)
    parser.add_argument("--readiness-output", required=True)
    parser.add_argument("--raw-cache-dir", default="data/formal_sources/raw_monthly_revenue_cache")
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    result = build_point_in_time_revenue_dataset(
        formal_universe_path=args.formal_universe,
        market_universe_path=args.market_universe,
        output_path=args.output,
        gap_report_path=args.gap_report,
        readiness_output_path=args.readiness_output,
        start_date=args.start_date,
        end_date=args.end_date,
        raw_cache_dir=args.raw_cache_dir,
        force_fetch=args.force_fetch,
        sleep_seconds=args.sleep_seconds,
        retry_attempts=args.retry_attempts,
        retry_sleep_seconds=args.retry_sleep_seconds,
        progress_every=args.progress_every,
    )
    print(f"Saved {result.revenue_path}")
    print(f"Saved {result.gap_report_path}")
    print(f"Saved {result.readiness_path}")
    print(f"ready={result.readiness['ready']}")
    print(f"source_mode={result.readiness['source_mode']}")
    print(f"coverage_ratio={result.readiness['coverage_ratio']}")
    print(f"future_data_violation_count={result.readiness['future_data_violation_count']}")


if __name__ == "__main__":
    main()
