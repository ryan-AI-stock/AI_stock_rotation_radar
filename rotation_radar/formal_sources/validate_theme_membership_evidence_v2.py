from __future__ import annotations

import argparse

from .theme_membership_evidence_v2 import validate_theme_membership_evidence_v2


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate date-aware theme membership v2 evidence queue.")
    parser.add_argument("--queue", default="data/formal_sources/theme_membership_evidence_queue_v2.csv")
    parser.add_argument("--ledger", default="data/formal_sources/theme_membership_evidence_v2.csv")
    parser.add_argument("--readiness", default="data/formal_sources/date_aware_theme_membership_v2_readiness.json")
    parser.add_argument(
        "--formal-top3-readiness",
        default="data/history_replay/formal_top3_capital_flow_2022_2023/top3_capital_flow_readiness.json",
    )
    args = parser.parse_args()

    readiness = validate_theme_membership_evidence_v2(
        queue_path=args.queue,
        ledger_path=args.ledger,
        readiness_path=args.readiness,
        formal_top3_readiness_path=args.formal_top3_readiness,
    )
    print(f"Validated {args.queue}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"formal_top3_status={readiness['formal_top3_status']}")


if __name__ == "__main__":
    main()
