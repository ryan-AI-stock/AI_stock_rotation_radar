from __future__ import annotations

import argparse

from .chip_flow_overlay import validate_chip_flow_overlay_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate chip-flow overlay package readiness.")
    parser.add_argument(
        "--output-dir",
        default="data/formal_sources/chip_flow_overlay_2021_2023",
    )
    args = parser.parse_args()

    readiness = validate_chip_flow_overlay_package(output_dir=args.output_dir)
    print(f"Validated {args.output_dir}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"symbol_count={readiness['symbol_count']}")
    print(f"trading_day_count={readiness['trading_day_count']}")
    print(f"future_data_violation_count={readiness['future_data_violation_count']}")


if __name__ == "__main__":
    main()
