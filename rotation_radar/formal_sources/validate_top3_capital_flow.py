from __future__ import annotations

import argparse

from .top3_capital_flow import validate_top3_capital_flow_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate formal top3 capital-flow package readiness.")
    parser.add_argument(
        "--output-dir",
        default="data/history_replay/formal_top3_capital_flow_2022_2023",
    )
    args = parser.parse_args()

    readiness = validate_top3_capital_flow_package(output_dir=args.output_dir)
    print(f"Validated {args.output_dir}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"trading_day_count={readiness['trading_day_count']}")


if __name__ == "__main__":
    main()
