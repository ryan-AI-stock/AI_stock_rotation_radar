# TWSE historical issued shares / direct market cap route

## 結論
- 狀態：`completed_partial_quarterly_capital_stock_route_unlocked_direct_market_cap_blocked`
- MOPS `ajax_t163sb05` 資產負債表 route 已解鎖，可取得 TWSE period-specific quarterly `capital_stock` sample rows。
- accepted quarterly capital stock sample rows：`720`
- accepted periods：`2015Q4, 2024Q4, 2026Q1`
- direct TWSE per-stock historical market cap：仍 blocked。
- daily TWSE issued shares：仍 blocked。
- free-float market cap：仍 blocked。

## 邊界
- `formal_exact=false`
- `twse_market_cap_route_unlocked=false`
- `twse_issued_shares_route_unlocked=false`
- `twse_quarterly_capital_stock_route_unlocked=true`
- `twse_sample_ready=true`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`

## 已試路線
- TWSE `MI_INDEX`：2015/2024/2026 sample 可取交易資料，但無 per-stock issued shares / market cap。
- TWSE OpenAPI swagger：找到 current snapshot `t187ap03_L`、top20 foreign holding share routes、quarterly financial statement routes；未找到 historical per-stock direct market cap endpoint。
- MOPS `t187ap03_L` / `t51sb01`：current snapshot only，已列 rejected，不回推 2015。
- MOPS `ajax_t163sb05`：period-specific balance sheet route 成功，提供 quarterly `capital_stock` candidate，但不是 daily issued shares。

## 下一個可程式化來源
- 搜尋/反解 TWSE 或 MOPS capital-change effective-date announcement routes。
- 用 `ajax_t163sb05` full quarter sweep + TWSE daily close 建 diagnostic total market cap proxy，但需 Core 判斷是否接受 quarterly capital_stock carry-forward policy。
- 查 Taiwan Index / TWSE index weight archive 是否提供 historical constituent market value / free-float factor。
