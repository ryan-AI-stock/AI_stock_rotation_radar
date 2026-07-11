# P3 exact primary80 full-feature source-scope repair

- Exact membership：12320 rows / 154 snapshots / 701 tickers。
- Exact actual coverage：2023-07-14~2026-06-29。
- 2023-07-11~2023-07-13 無 exact primary80 snapshot；2026-06-29 後不得 carry-forward 宣稱 exact PIT。
- Core 原 no-path proof 與指定 exact contract 不一致：12 檔中有 11 檔、87 個 exact primary80 snapshot rows；保留 blocker並回 Core reconciliation。
- corporate-action 目前是 event inventory，沒有逐 ticker no-event completeness proof，不包裝為完整 official adjusted。
- blocked ticker/date rows：6583。
- future_data_violation_count=0。
- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。
