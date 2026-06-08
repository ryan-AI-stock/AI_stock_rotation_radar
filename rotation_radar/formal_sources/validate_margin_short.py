from __future__ import annotations

import argparse

from .margin_short import validate_margin_short_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate TWSE MI_MARGN margin/short data for the 9-asset overlay pool.")
    parser.add_argument(
        "--input",
        default="data/formal_sources/chip_flow_overlay_2021_2023/margin_short_daily_2021_2023.csv",
    )
    parser.add_argument(
        "--gap-report",
        default="data/formal_sources/chip_flow_overlay_2021_2023/margin_short_daily_2021_2023_gap.csv",
    )
    parser.add_argument(
        "--readiness-output",
        default="data/formal_sources/chip_flow_overlay_2021_2023/margin_short_daily_2021_2023_readiness.json",
    )
    parser.add_argument(
        "--trading-dates-source",
        default="data/formal_sources/official_turnover_20211201_20231231.csv",
    )
    parser.add_argument("--start-date", default="2021-12-01")
    parser.add_argument("--end-date", default="2023-12-29")
    args = parser.parse_args()

    readiness = validate_margin_short_dataset(
        input_path=args.input,
        gap_report_path=args.gap_report,
        readiness_output_path=args.readiness_output,
        trading_dates_source=args.trading_dates_source,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"Validated {args.input}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"coverage_ratio={readiness['coverage_ratio']}")
    print(f"stock_coverage_ratio={readiness['stock_coverage_ratio']}")


if __name__ == "__main__":
    main()
