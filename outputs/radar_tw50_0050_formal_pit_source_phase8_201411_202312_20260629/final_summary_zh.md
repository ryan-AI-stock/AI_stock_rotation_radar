# 0050 歷史成分股來源 Phase 8：formal PIT source continuation

## 結論

本批沒有收束，新增 Phase 8 實際 source attempts：non-headless/persisted Chrome SITCA UI path、SITCA static/download handler discovery、元大舊站/API alternative route、Taiwan Index/TWSE index proxy route。

- Accepted historical rows: 4301
- Parsed holdings sample rows: 6305
- Source probe attempts: 211
- Browser capture attempts: 65
- Index proxy candidate rows: 320

本批已找到四個 target periods 的 target-month PCF/Daily rows，屬於 `source_backed_manual_candidate`，仍需 Core 複核是否可作為 0050 historical PIT normalizer 的正式輸入。

## Period Status

| period | target_date | source probes | browser attempts | proxy rows | parsed sample rows | accepted rows | status |
|---|---:|---:|---:|---:|---:|---:|---|
| 2014Q4 | 2014-12-31 | 58 | 26 | 80 | 1627 | 1151 | accepted_rows_found |
| 2016Q1 | 2016-03-31 | 58 | 26 | 80 | 1526 | 1100 | accepted_rows_found |
| 2021Q4 | 2021-12-31 | 58 | 26 | 80 | 1576 | 1050 | accepted_rows_found |
| 2023Q4 | 2023-12-31 | 58 | 26 | 80 | 1576 | 1000 | accepted_rows_found |

## Source Decisions

- `accepted_historical_rows.csv` only accepts target-period 0050 PCF/Daily rows with date match and ticker/name present.
- `index_constituents_proxy_candidates.csv` is kept separate; Taiwan Index/TWSE rows are not treated as 0050 ETF holdings.
- target-month 元大 PCF/Daily rows are accepted as source-backed manual candidates; current/rolling/date-mismatched 元大 API rows remain parser samples only.
- SITCA non-headless or POST responses without holdings context are not accepted.

## 下一個可程式化來源

1. Expand the Yuanta PCF/Daily month sweep from the four sample periods to the full 2014/11～2023/12 range, with checkpointed monthly/daily batches and duplicate filtering.
2. Ask Core to define the normalizer contract for PCF/Daily rows: whether PCF basket rows can be used as 0050 holdings PIT, how to handle 51/52-row days, and whether weight fields are adequate.
3. Continue SITCA alternate handler/static file discovery only as a secondary corroborating source.
4. Keep Taiwan Index official review PDFs / FTSE TWSE review notices as `index_constituents_proxy_candidate` only; do not merge them into accepted 0050 holdings rows without Core/Research decision.

## Guardrails

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `formal_exact=false` unless future source proves exact target-date holdings
- `current_snapshot_used_as_historical=false`
- raw responses are retained under `raw_sources/` and excluded from git
