from __future__ import annotations

import argparse
import json

from .pool2_tw50_readiness import build_pool2_tw50_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Pool2 TW50/0050 PIT replay readiness handoff package.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--core-coverage-dir", required=True)
    parser.add_argument(
        "--intake-readiness",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdf_intake_readiness.json",
    )
    parser.add_argument(
        "--phase3-checklist",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_phase3/source_acquisition_checklist.csv",
    )
    parser.add_argument(
        "--phase4-search-readiness",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_phase4_drive_local_search/phase4_drive_local_search_readiness.json",
    )
    args = parser.parse_args()

    readiness = build_pool2_tw50_readiness(
        output_dir=args.output_dir,
        core_coverage_dir=args.core_coverage_dir,
        intake_readiness_path=args.intake_readiness,
        phase3_checklist_path=args.phase3_checklist,
        phase4_search_readiness_path=args.phase4_search_readiness,
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
