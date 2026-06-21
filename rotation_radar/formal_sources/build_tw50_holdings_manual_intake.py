from __future__ import annotations

import argparse

from .tw50_holdings_manual_intake import build_tw50_holdings_manual_intake


def main() -> None:
    parser = argparse.ArgumentParser(description="Check manually acquired Yuanta 0050 holdings proxy PDFs.")
    parser.add_argument(
        "--checklist",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_phase3/source_acquisition_checklist.csv",
    )
    parser.add_argument(
        "--pdf-dir",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdfs",
    )
    parser.add_argument(
        "--output-dir",
        default="data/formal_sources/tw50_0050_holdings_manual_ledger_intake",
    )
    args = parser.parse_args()

    readiness = build_tw50_holdings_manual_intake(
        checklist_path=args.checklist,
        pdf_dir=args.pdf_dir,
        output_dir=args.output_dir,
    )
    print(f"status={readiness['status']}")
    print(f"ready={readiness['ready']}")
    print(f"pdfs_found={readiness['pdfs_found']}")
    print(f"valid_pdf_header_count={readiness['valid_pdf_header_count']}")
    print(f"historical_snapshot_rows={readiness['historical_snapshot_rows']}")


if __name__ == "__main__":
    main()
