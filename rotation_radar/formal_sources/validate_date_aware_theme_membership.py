from __future__ import annotations

import argparse

from .date_aware_theme_membership import ensure_membership_file, validate_date_aware_theme_membership


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate date-aware theme membership readiness for formal radar replay.")
    parser.add_argument("--membership-file", required=True)
    parser.add_argument("--formal-universe", required=True)
    parser.add_argument("--theme-map", default="data/theme_map.csv")
    parser.add_argument("--theme", help="Limit readiness validation to one theme.")
    parser.add_argument("--target-symbols", help="Comma-separated symbols to validate within the selected scope.")
    parser.add_argument("--gap-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target_symbols = _parse_target_symbols(args.target_symbols)

    ensure_membership_file(args.membership_file)
    readiness = validate_date_aware_theme_membership(
        membership_file=args.membership_file,
        formal_universe_path=args.formal_universe,
        theme_map_path=args.theme_map,
        gap_report_path=args.gap_report,
        output_path=args.output,
        theme=args.theme,
        target_symbols=target_symbols,
    )
    print(f"Saved {args.output}")
    print(f"Saved {args.gap_report}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"coverage_ratio={readiness['coverage_ratio']}")
    print(f"date_aware_row_count={readiness['date_aware_row_count']}")
    print(f"static_only_count={readiness['static_only_count']}")


def _parse_target_symbols(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


if __name__ == "__main__":
    main()
