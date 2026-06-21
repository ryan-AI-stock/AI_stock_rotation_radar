# Core Handoff: Manual Ledger Proxy Readiness

Phase 3 provides a manual ledger workflow, not formal historical data completion.

Core may implement a proxy-specific readiness reader for:

- `manual_ledger_template.csv`
- future reviewed ledger rows
- source acquisition checklist status

Core must require:

- `is_proxy=true`
- `source_mode=yuanta_0050_holdings_proxy`
- `exact_tw50_official_constituents=false`
- `review_status=accepted`
- no future-data violation

Core must not:

- feed these rows into exact TW50 constituent validator
- silently convert proxy rows into official constituents
- run final three-pool diagnosis on partial/manual rows without explicit
  readiness status and limitation text

Suggested readiness statuses:

- `manual_ledger_design_ready`: schema/SOP/checklist are ready, but data rows are
  not ready.
- `manual_ledger_partial`: some reviewed rows exist, coverage insufficient.
- `manual_ledger_proxy_ready`: enough accepted proxy rows exist for a
  proxy-specific replay, still not exact TW50.
- `blocked_license_or_source`: source cannot be used or license is unresolved.

Exact TW50 readiness should remain blocked unless a true official PIT source is
provided.
