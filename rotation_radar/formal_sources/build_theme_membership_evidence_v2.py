from __future__ import annotations

import argparse

from .theme_membership_evidence_v2 import build_theme_membership_evidence_v2


def main() -> None:
    parser = argparse.ArgumentParser(description="Build date-aware theme membership v2 evidence queue.")
    parser.add_argument("--gap", default="data/formal_sources/date_aware_theme_membership_full_2022_2023_gap.csv")
    parser.add_argument("--queue", default="data/formal_sources/theme_membership_evidence_queue_v2.csv")
    parser.add_argument("--ledger", default="data/formal_sources/theme_membership_evidence_v2.csv")
    parser.add_argument("--readiness", default="data/formal_sources/date_aware_theme_membership_v2_readiness.json")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--sample-size", type=int, default=5)
    args = parser.parse_args()

    readiness = build_theme_membership_evidence_v2(
        gap_path=args.gap,
        queue_path=args.queue,
        ledger_path=args.ledger,
        readiness_path=args.readiness,
        batch_size=args.batch_size,
        sample_size=args.sample_size,
    )
    print(f"Built {args.queue}")
    print(f"ready={readiness['ready']}")
    print(f"source_mode={readiness['source_mode']}")
    print(f"queued_symbol_count={readiness['queued_symbol_count']}")
    print(f"sample_evidence_row_count={readiness['sample_evidence_row_count']}")


if __name__ == "__main__":
    main()
