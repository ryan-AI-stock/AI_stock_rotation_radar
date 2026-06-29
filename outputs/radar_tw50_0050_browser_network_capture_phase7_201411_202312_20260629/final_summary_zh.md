# 0050 歷史成分股來源 Phase 7：browser network capture

## 結論

本批完成 Chrome DevTools Protocol live browser network capture 與 exact replay attempts。

- Accepted historical rows: 0
- Parsed holdings sample rows: 189
- SITCA captured requests: 54
- SITCA captured POST requests: 4
- Yuanta captured relevant requests: 50
- Yuanta captured api bridge/trans requests: 28
- Exact replay attempts: 40

目前仍未取得 2014Q4、2016Q1、2021Q4、2023Q4 任一段可 accepted 的 0050 歷史成分股清單。

## SITCA Live Capture

Browser capture observed 4 SITCA POST request(s), but semantic filtering found 0 target holdings-table rows.
詳情見 `sitca_network_requests.csv`；headers 已遮罩 cookie。

## Yuanta Live Capture

Browser capture observed 28 Yuanta api/bridge or api/trans request(s).
Exact replay attempts were generated from captured/common parameters and target dates.

## Period Status

| period | target_date | replay_attempts | parsed_sample_rows | accepted_rows | status |
|---|---:|---:|---:|---:|---|
| 2014Q4 | 2014-12-31 | 10 | 35 | 0 | missing_accepted_rows |
| 2016Q1 | 2016-03-31 | 10 | 35 | 0 | missing_accepted_rows |
| 2021Q4 | 2021-12-31 | 10 | 35 | 0 | missing_accepted_rows |
| 2023Q4 | 2023-12-31 | 10 | 35 | 0 | missing_accepted_rows |

## 下一個可程式化來源

1. 改用 non-headless Chrome + persisted profile 再 capture 一次，確認 SITCA 是否拒絕 headless 或需要真實 UI event path。
2. 針對 SITCA `IN2421.aspx` 背後 static/download endpoint、站內檔案索引或 alternate ASP.NET handler 做 bounded discovery。
3. 針對元大 Nuxt `getBaseUrl/getCommonParameters` 與 DeviceId/common params 做 deeper trace；若 API 只提供 current/near-current，保留 endpoint contract sample，不列 historical accepted。
4. TWSE/Taiwan Index constituents 仍只能作 proxy，除非 source decision 能明確連到 0050 ETF holdings。

## Guardrails

- `formal_exact=false`
- `current_snapshot_used_as_historical=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- raw browser responses are retained under `raw_sources/` and excluded from git
