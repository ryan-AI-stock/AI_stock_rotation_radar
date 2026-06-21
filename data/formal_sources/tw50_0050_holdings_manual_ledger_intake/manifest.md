# TW50/0050 Manual PDF Intake Manifest

Status: `blocked_waiting_user_files`

Files:

- `manual_pdf_intake_status.csv`
- `manual_pdf_intake_readiness.json`
- `manual_pdfs/README.md`
- `manual_pdfs/.gitignore`

This intake checker only verifies whether expected historical Yuanta PDF files exist locally.
It does not parse holdings rows, write the manual ledger, or mark any source as formal-ready.

Data boundary:

- `source_mode=yuanta_0050_holdings_proxy`
- `is_proxy=true`
- `exact_tw50_official_constituents=false`

Next action: Acquire priority-1 PDFs before parser/manual review can begin.
