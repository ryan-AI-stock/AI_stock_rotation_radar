# 0050 PCF/Daily full-range PIT candidate sweep

## 結論

依 Core contract 完成 Yuanta PCF/Daily full-range sweep：`2014-11` 到 `2023-12`。

- Covered months: 110/110
- Missing months: 0
- Validated daily rows: 112200
- Rejected rows: 1874
- Row-count anomaly days: 0
- Quarantined days: 0

本輸出是 full-range PIT candidate ledger，不是 formal exact PIT；`formal_exact=false`，`source_type=source_backed_manual_candidate`。

## Monthly Coverage

| metric | value |
|---|---:|
| total months | 110 |
| covered months | 110 |
| missing months | 0 |
| source request attempts | 4118 |

## Core Handoff

- `validated_daily_pcf_candidate.csv` is ready for Core monthly-anchor compression.
- Monthly anchor rule: each month uses the last accepted `holdings_date` in `monthly_coverage_summary.csv`.
- 51/52-row days are kept with `row_count_anomaly=true`; outside 49-52 are quarantined.
- Weight fields come from Yuanta `FundWeights.StockWeights`; if blank, membership only.

## Guardrails

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `formal_exact=false`
- Taiwan Index/TWSE proxy rows are not included.
- current/rolling/date-mismatched payloads are rejected.
