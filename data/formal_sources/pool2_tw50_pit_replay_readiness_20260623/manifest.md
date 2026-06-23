# Pool2 TW50/0050 PIT Replay Readiness

Status: `blocked_waiting_user_files`
Exact TW50 official constituents ready: `False`
Yuanta 0050 holdings proxy ready: `False`
Future data violation count: `0`

## Coverage Summary

| period | start | end | checked_dates | ready_dates | gap_dates | coverage_ratio | minimum_active_count | min_active_count | max_active_count | first_ready_date | last_ready_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | 2022-01-03 | 2022-12-30 | 260 | 0 | 260 | 0.0 | 45 | 0 | 0 |  |  |
| 2023 | 2023-01-03 | 2023-12-29 | 259 | 0 | 259 | 0.0 | 45 | 0 | 0 |  |  |
| 2024_now | 2024-01-02 | 2026-06-12 | 639 | 255 | 384 | 0.39906103 | 45 | 0 | 50 | 2025-06-23 | 2026-06-12 |

## Blocking Issues

- exact_tw50_constituents_ready=false: Core coverage remains below 95% for at least one period.
- yuanta_0050_holdings_proxy_ready=false: missing manual PDFs yuanta_0050_monthly_202201.pdf, yuanta_domestic_holdings_2022Q1.pdf, yuanta_0050_monthly_202206.pdf, yuanta_domestic_holdings_2022Q2.pdf, yuanta_0050_monthly_202212.pdf
- proxy_specific_readiness_ready=false: accepted holdings proxy rows=0.

## Required Manual Sources

- Priority 1: `yuanta_0050_monthly_202201.pdf`
- Priority 1: `yuanta_domestic_holdings_2022Q1.pdf`
- Place files under `data/formal_sources/tw50_0050_holdings_manual_ledger_intake/manual_pdfs/`.

## Core Boundary

- `0050_holdings_proxy_rows.csv` is a proxy-specific interface and currently has zero accepted rows.
- `tw50_constituents_pit_candidate.csv` is schema-only because no exact official PIT rows were acquired.
- Core must not treat Yuanta holdings proxy rows as exact official TW50 constituents.

## Next Commands

```powershell
python -m rotation_radar.formal_sources.build_tw50_holdings_manual_intake
python -m rotation_radar.formal_sources.build_pool2_tw50_readiness --core-coverage-dir C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\pool2_tw50_pit_replay_coverage_20260623 --output-dir data\formal_sources\pool2_tw50_pit_replay_readiness_20260623
```
