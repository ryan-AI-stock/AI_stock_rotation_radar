from __future__ import annotations

import argparse

from .date_aware_theme_membership_full import build_full_date_aware_membership


def main() -> None:
    parser = argparse.ArgumentParser(description="Build full date-aware theme membership package for formal top3 replay.")
    parser.add_argument("--output", default="data/formal_sources/date_aware_theme_membership_full_2022_2023.csv")
    parser.add_argument("--gap-report", default="data/formal_sources/date_aware_theme_membership_full_2022_2023_gap.csv")
    parser.add_argument("--readiness", default="data/formal_sources/date_aware_theme_membership_full_2022_2023_readiness.json")
    parser.add_argument("--start-date", default="2022-01-03")
    parser.add_argument("--end-date", default="2023-12-29")
    args = parser.parse_args()

    readiness = build_full_date_aware_membership(
        output_path=args.output,
        gap_path=args.gap_report,
        readiness_path=args.readiness,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"Saved {args.output}")
    print(f"Saved {args.gap_report}")
    print(f"Saved {args.readiness}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"coverage_ratio={readiness['coverage_ratio']}")
    print(f"gap_symbol_count={readiness['gap_symbol_count']}")


if __name__ == "__main__":
    main()
