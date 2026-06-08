from __future__ import annotations

import argparse

from .date_aware_theme_membership_full import validate_full_date_aware_membership


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate full date-aware theme membership readiness.")
    parser.add_argument("--membership", default="data/formal_sources/date_aware_theme_membership_full_2022_2023.csv")
    parser.add_argument("--gap-report", default="data/formal_sources/date_aware_theme_membership_full_2022_2023_gap.csv")
    parser.add_argument("--readiness", default="data/formal_sources/date_aware_theme_membership_full_2022_2023_readiness.json")
    args = parser.parse_args()

    readiness = validate_full_date_aware_membership(
        membership_path=args.membership,
        gap_path=args.gap_report,
        readiness_path=args.readiness,
    )
    print(f"Validated {args.membership}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"coverage_ratio={readiness['coverage_ratio']}")


if __name__ == "__main__":
    main()
