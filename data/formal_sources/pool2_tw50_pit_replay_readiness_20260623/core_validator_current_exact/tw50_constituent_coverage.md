# TW50 / 0050 成分股歷史覆蓋檢查

- readiness_status: `partial_blocked`
- source_path: `C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\data\tw50_constituents.csv`
- source_row_count: `50`
- source_effective_range: `2025-06-23` ~ `2025-06-23`

## 覆蓋摘要

| period | start | end | checked_dates | ready_dates | gap_dates | coverage_ratio | minimum_active_count | min_active_count | max_active_count | first_ready_date | last_ready_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | 2022-01-03 | 2022-12-30 | 260 | 0 | 260 | 0.0 | 45 | 0 | 0 |  |  |
| 2023 | 2023-01-03 | 2023-12-29 | 259 | 0 | 259 | 0.0 | 45 | 0 | 0 |  |  |
| 2024_2026 | 2024-01-02 | 2026-06-18 | 643 | 259 | 384 | 0.40279938 | 45 | 0 | 50 | 2025-06-23 | 2026-06-18 |

## 前 30 筆缺口

| period | signal_date | gap_reason | active_count |
| --- | --- | --- | --- |
| 2022 | 2022-01-03 | No TW50 constituents active on 2022-01-03 | 0 |
| 2022 | 2022-01-04 | No TW50 constituents active on 2022-01-04 | 0 |
| 2022 | 2022-01-05 | No TW50 constituents active on 2022-01-05 | 0 |
| 2022 | 2022-01-06 | No TW50 constituents active on 2022-01-06 | 0 |
| 2022 | 2022-01-07 | No TW50 constituents active on 2022-01-07 | 0 |
| 2022 | 2022-01-10 | No TW50 constituents active on 2022-01-10 | 0 |
| 2022 | 2022-01-11 | No TW50 constituents active on 2022-01-11 | 0 |
| 2022 | 2022-01-12 | No TW50 constituents active on 2022-01-12 | 0 |
| 2022 | 2022-01-13 | No TW50 constituents active on 2022-01-13 | 0 |
| 2022 | 2022-01-14 | No TW50 constituents active on 2022-01-14 | 0 |
| 2022 | 2022-01-17 | No TW50 constituents active on 2022-01-17 | 0 |
| 2022 | 2022-01-18 | No TW50 constituents active on 2022-01-18 | 0 |
| 2022 | 2022-01-19 | No TW50 constituents active on 2022-01-19 | 0 |
| 2022 | 2022-01-20 | No TW50 constituents active on 2022-01-20 | 0 |
| 2022 | 2022-01-21 | No TW50 constituents active on 2022-01-21 | 0 |
| 2022 | 2022-01-24 | No TW50 constituents active on 2022-01-24 | 0 |
| 2022 | 2022-01-25 | No TW50 constituents active on 2022-01-25 | 0 |
| 2022 | 2022-01-26 | No TW50 constituents active on 2022-01-26 | 0 |
| 2022 | 2022-01-27 | No TW50 constituents active on 2022-01-27 | 0 |
| 2022 | 2022-01-28 | No TW50 constituents active on 2022-01-28 | 0 |
| 2022 | 2022-01-31 | No TW50 constituents active on 2022-01-31 | 0 |
| 2022 | 2022-02-01 | No TW50 constituents active on 2022-02-01 | 0 |
| 2022 | 2022-02-02 | No TW50 constituents active on 2022-02-02 | 0 |
| 2022 | 2022-02-03 | No TW50 constituents active on 2022-02-03 | 0 |
| 2022 | 2022-02-04 | No TW50 constituents active on 2022-02-04 | 0 |
| 2022 | 2022-02-07 | No TW50 constituents active on 2022-02-07 | 0 |
| 2022 | 2022-02-08 | No TW50 constituents active on 2022-02-08 | 0 |
| 2022 | 2022-02-09 | No TW50 constituents active on 2022-02-09 | 0 |
| 2022 | 2022-02-10 | No TW50 constituents active on 2022-02-10 | 0 |
| 2022 | 2022-02-11 | No TW50 constituents active on 2022-02-11 | 0 |

使用邊界：本檢查只驗證 point-in-time 0050 成分股資料是否足以支撐池2歷史 replay；不使用現代成分股硬回推歷史，不改正式模型。