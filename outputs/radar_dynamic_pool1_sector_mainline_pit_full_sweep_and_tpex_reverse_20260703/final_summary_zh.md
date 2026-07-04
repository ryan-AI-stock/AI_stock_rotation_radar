# Dynamic Pool1 sector/mainline PIT full sweep + TPEx reverse

## 結論
- 狀態：`completed_partial_twse_monthly_anchor_ready_tpex_blocked`
- TWSE by-industry monthly-anchor sweep：`true`
- TWSE-only：`true`
- TPEx included：`false`
- mainline/theme ready：`false`
- TPEx sector membership route：`blocked`
- sector membership PIT：`partial_ready`
- sector breadth daily：`not ready`
- ready_for_core_rerun：`true`
- ready_for_strategy_replay：`false`
- future_data_violation_count：`0`

## TWSE 結果
- 來源：TWSE official `MI_INDEX?date={yyyymmdd}&type={industry_code}`
- 範圍：2015-01 到 latest liquidity anchor month，monthly last TWSE trading day。
- accepted rows：126394
- formal_exact=false；這是 monthly-anchor sector membership candidate，不是 full daily exact membership。

## TPEx reverse
- `daily-sector.html` / `constituents.html` 反解到 action `statistics/idx`。
- 表單欄位：`type=3` 為產業分類股價指數，`type=4` 為股價指數採樣股票一覽表，`date` 為年份格式。
- bounded probes 已落 `tpex_sector_route_probe_attempts.csv`；本棒未取得可 accepted 的 all-stock historical sector membership rows。

## 仍缺
- TPEx historical/date-aware sector membership route。
- date-aware mainline/theme taxonomy；TWSE official industry 不等於 Dynamic Pool1 主線/題材。
- sector breadth daily 需等 cross-market PIT membership ready 後才能派生。
