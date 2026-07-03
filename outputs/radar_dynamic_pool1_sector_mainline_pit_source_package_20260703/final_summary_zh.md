# Dynamic Pool1 sector/mainline PIT source package

## 結論
- 狀態：`completed_partial_twse_sector_route_unlocked`
- `sector_membership_pit_ready=false`
- `sector_breadth_pit_daily_ready=false`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 本棒新增
- 解出並驗證 TWSE official `MI_INDEX?date={yyyymmdd}&type={industry_code}` 每日分產業收盤行情路線。
- bounded sample 覆蓋 2015-01-05、2020-01-02、2026-07-02，測試 31 個 TWSE industry type code。
- accepted sector membership sample rows：2696。
- 每筆 accepted row 都有 `source_date`、`effective_date`、`as_of_date`，且都等於該 TWSE 交易日；`accepted_for_formal=false`，因本棒不是 full sweep。

## 不能放行的部分
- TPEx `dailyQuotes` 有 date-aware trading rows，但 schema 無產業/類股欄位，不能產生 TPEx sector membership。
- TPEx guessed sector/constituents pages 回 404；menu candidates 只列 route inventory，未產生 accepted rows。
- MOPS/t51sb01 與 repo current/static sector/theme maps 只能 proxy 或 blocker，不可回推 2015。
- TWSE industry sector 不等於 Dynamic Pool1 的 mainline/theme taxonomy；mainline/theme PIT 仍需 MOPS 年報、公開說明書、法說或 dated theme evidence ledger。

## 下一步
1. Radar/Data：把 TWSE `MI_INDEX` by-industry route 擴成 2015-latest full daily或 monthly anchor membership sweep。
2. Radar/Data：reverse TPEx menu candidates / Industry Chain Information Platform，看是否有 historical industry membership endpoint。
3. Research/Core：決定 TWSE official industry sector 是否可作 Dynamic Pool1 sector breadth proxy candidate，並定義 mainline/theme 與 official industry 的分層。
