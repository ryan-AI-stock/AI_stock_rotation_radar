# Normalized Data Consolidation Plan

## Scope
This audit scanned `outputs/` only and did not delete, move, or compress files.

## Current Size
- Packages scanned: 35
- Files scanned: 10721
- Total estimated size: 5800.28 MB
- Protected backtest/source-candidate packages: 11 packages, 5376.002 MB

## Consolidation Recommendation
1. Create a shared normalized data area outside ad-hoc task outputs, for example `data/normalized_candidates/`.
2. Move only after a separate approved migration task:
   - 0050 PCF daily/monthly candidate rows.
   - Full-market TWSE/TPEx liquidity rows.
   - Pool1B repaired price cache including `6488.TWO`.
   - MOPS monthly revenue and quarterly fundamentals full-universe rows.
   - TPEx/TWSE listing/status/transition ledgers.
   - Market-cap source-candidate shards.
3. Keep every package `manifest.json`, `readiness_for_core.json`, `future_data_violation_audit.csv`, `source_manifest*`, and final summaries tracked in their original output package.
4. Raw PDFs/HTML/JSON/browser artifacts should be compressed or archived only after a checksum manifest exists. This audit does not authorize deletion.
5. Failed route attempts should retain summary/manifest/attempt CSVs. Bulky raw artifacts from failed routes are archive candidates, not immediate deletion candidates.

## Protected Data
Do not remove without a separate approval and verified backup:
- 0050 PIT / PCF full-range candidate.
- 2015-latest TWSE/TPEx liquidity and price data.
- Pool1B price repair, including `6488.TWO`.
- MOPS monthly revenue and quarterly fundamentals full-universe candidates.
- Listing/status metadata and transition ledgers.
- Source manifests, readiness ledgers, and future-data audits.

## Execution Boundary
- `delete_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
