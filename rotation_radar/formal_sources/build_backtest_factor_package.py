from __future__ import annotations

import argparse

from .backtest_factor_package import build_backtest_factor_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build BACKTEST_LAB 2024-2026 factor input package manifest.")
    parser.add_argument("--package-dir", default="data/formal_sources/backtest_factor_2024_2026")
    parser.add_argument("--readiness-output")
    parser.add_argument("--gap-output")
    parser.add_argument("--manifest-output")
    args = parser.parse_args()

    readiness = build_backtest_factor_package(
        package_dir=args.package_dir,
        readiness_output=args.readiness_output,
        gap_output=args.gap_output,
        manifest_output=args.manifest_output,
    )
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    for factor_id, status in readiness["factor_status"].items():
        print(f"{factor_id}: status={status['status']} fresh_coverage_ratio={status['fresh_coverage_ratio']}")


if __name__ == "__main__":
    main()
