# Pool2 TW50 Exact PIT Event Source Package

Generated: 2026-06-23 Asia/Taipei

## Scope

This package continues Core task TASK-BACKTEST-CORE-POOL2-PIT-REPLAY-COVERAGE-20260623 for exact TW50 point-in-time data readiness. It records official Taiwan Index technical notice candidates and official baseline-source search results.

## Result

- Status: `partial_blocked_download_rate_limited_and_missing_official_baseline`
- Formal ready: `false`
- Candidate Taiwan Index technical notices: 29
- Downloaded technical notice PDFs: 0
- Accepted event rows: 0
- Official baseline snapshot on/before first event: not found
- Future-data violation count: 0

## Why Not Ready

Core requires both accepted add/delete event rows and an official complete baseline snapshot dated no later than the first accepted event. Current FTSE/LSEG constituents/factsheet PDFs are downloadable, but they are current/late 2026 snapshots and cannot be used to reconstruct 2022/2023 history.

Taiwan Index technical notice metadata was found for 2022-2026 TW50-related notices, but PDF downloads from `backend.taiwanindex.com.tw` currently return HTTP 429 Too Many Requests, so the Core parser could not be run on actual notice PDFs.

## Files

- `technical_notice_source_manifest.csv`: 29 TW50 official technical notice candidates with download status.
- `baseline_source_search_audit.csv`: official baseline/source search audit.
- `official_current_snapshot_audit.csv`: FTSE/LSEG current snapshot download audit; not accepted as 2022 PIT baseline.
- `core_parser_output/`: Core-contract-shaped empty output and failed download list.
- `pool2_tw50_exact_pit_readiness.json`: machine-readable readiness result.

## Core Handoff

Core should not rerun formal Pool2 validator as ready from this package. The package is useful for validating source discovery and blockers only. Next Core-acceptable step is to obtain technical notice PDFs plus a dated official full baseline snapshot.
