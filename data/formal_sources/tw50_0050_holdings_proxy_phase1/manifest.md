# TW50/0050 Holdings Proxy Phase 1 Manifest

Task ID: `TASK-RADAR-TW50-0050-HOLDINGS-PROXY-PHASE1-001`

Status: `Phase 1 source inventory / partial`

Files:

- `phase1_source_inventory.md`
- `yuanta_0050_holdings_source_inventory.csv`
- `yuanta_0050_holdings_proxy_schema.csv`
- `yuanta_0050_holdings_proxy_readiness.json`
- `core_contract_recommendation.md`

Verification performed:

- Downloaded current Yuanta 0050 monthly report PDF from official Yuanta URL.
- Downloaded current Yuanta domestic fund quarterly holdings PDF from official
  Yuanta URL.
- Confirmed local PDF text extraction is not available in this repo session
  (`pypdf` missing, `pdftotext` not found), so parsing is intentionally marked
  blocked rather than accepted.

This package is not formal-ready and must not be used as exact TW50 official
point-in-time constituent history.
