# TW50 Constituents History Phase 0 Manifest

- task_id: `TASK-BACKTEST-DATA-TW50-CONSTITUENTS-HISTORY-001`
- project: `AI_stock_rotation_radar`
- status: `partial_blocked`
- created_at: `2026-06-21 Asia/Taipei`

## Outputs

- `source_feasibility_report.md`
- `tw50_constituents_source_candidates.csv`
- `tw50_constituents_source_pending.csv`
- `tw50_constituents_history_readiness.json`

## Validation

This package is intentionally not ready for Core replay. The schema-only source
pending CSV can be passed to the Core validator to confirm that the result
remains blocked until accepted rows exist.

Actual validator result:

- `readiness_status=blocked_no_historical_coverage`
- 2022 coverage 0.0
- 2023 coverage 0.0
- 2024_2026 coverage 0.0
- output: `data/formal_sources/tw50_constituents_history_phase0/validator_output`

Command used:

```powershell
$env:PYTHONPATH='src'
python -m backtest_lab.tw50_constituent_coverage --constituent-path C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\data\formal_sources\tw50_constituents_history_phase0\tw50_constituents_source_pending.csv --output-dir C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\data\formal_sources\tw50_constituents_history_phase0\validator_output
```

Core contract test:

```powershell
python -m unittest discover -s tests -p test_tw50_constituent_coverage.py -v
```

Result: 2 tests OK.

## Boundary

This package is a Phase 0 source feasibility checkpoint. It does not alter
Radar daily reporting or BACKTEST_LAB formal model behavior.
