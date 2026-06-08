from __future__ import annotations

import argparse

from .institutional_flows import build_institutional_flows_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TWSE T86 institutional flows for the 9-asset overlay pool.")
    parser.add_argument(
        "--output",
        default="data/formal_sources/chip_flow_overlay_2021_2023/institutional_flows_daily_2021_2023.csv",
    )
    parser.add_argument(
        "--gap-report",
        default="data/formal_sources/chip_flow_overlay_2021_2023/institutional_flows_daily_2021_2023_gap.csv",
    )
    parser.add_argument(
        "--readiness-output",
        default="data/formal_sources/chip_flow_overlay_2021_2023/institutional_flows_daily_2021_2023_readiness.json",
    )
    parser.add_argument(
        "--trading-dates-source",
        default="data/formal_sources/official_turnover_20211201_20231231.csv",
    )
    parser.add_argument("--start-date", default="2021-12-01")
    parser.add_argument("--end-date", default="2023-12-29")
    parser.add_argument(
        "--raw-cache-dir",
        default="data/formal_sources/chip_flow_overlay_2021_2023/raw_twse_t86_cache",
    )
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--progress-every", type=int, default=50)
    args = parser.parse_args()

    result = build_institutional_flows_dataset(
        output_path=args.output,
        gap_report_path=args.gap_report,
        readiness_output_path=args.readiness_output,
        trading_dates_source=args.trading_dates_source,
        start_date=args.start_date,
        end_date=args.end_date,
        raw_cache_dir=args.raw_cache_dir,
        force_fetch=args.force_fetch,
        sleep_seconds=args.sleep_seconds,
        retry_attempts=args.retry_attempts,
        retry_sleep_seconds=args.retry_sleep_seconds,
        progress_every=args.progress_every,
    )
    print(f"Saved {result.output_path}")
    print(f"Saved {result.gap_report_path}")
    print(f"Saved {result.readiness_path}")
    print(f"ready={result.readiness['ready']}")
    print(f"source_mode={result.readiness['source_mode']}")
    print(f"coverage_ratio={result.readiness['coverage_ratio']}")
    print(f"stock_coverage_ratio={result.readiness['stock_coverage_ratio']}")
    print(f"future_data_violation_count={result.readiness['future_data_violation_count']}")


if __name__ == "__main__":
    main()
