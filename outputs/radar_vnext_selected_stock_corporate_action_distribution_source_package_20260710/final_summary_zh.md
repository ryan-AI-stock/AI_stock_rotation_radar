# TASK-RADAR-DATA-VNEXT-SELECTED-STOCK-CORPORATE-ACTION-DISTRIBUTION-SOURCE-PACKAGE-001

## 結論

已建立 reconstructed R6 + Daily F 實際 selected/held 普通股的官方 corporate-action / distribution source package。

- selected ordinary-stock tickers: 32
- official t187ap39/40 route rows: 4
- corporate-action/distribution candidate rows: 114
- cash distribution candidate rows: 105
- adjustment factor source candidate rows: 3
- dividend_year_roc range: 107~110
- future_data_violation_count: 0

## Readiness

- ready_for_core_source_absorption_review=true
- ready_for_core_selected_stock_total_return_ledger=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false

## 邊界

Radar/Data 只做官方 source package，沒有計算 adjusted close，也沒有假設現金股利自動再投入。

t187ap39/40 可提供部分股利分派/決議候選；本次 fetched rows 的股利年度 coverage 仍有限，且仍缺 exact historical ex-date、payment date / market_available timestamp，以及減資、分割、合併、換股等完整 official route。因此這包可交 Core 做 source absorption/review，不可直接視為 formal same-basis total-return ledger ready。

## 下一棒

交 Core/Data：`TASK-BACKTEST-CORE-VNEXT-SELECTED-STOCK-TOTAL-RETURN-AND-CORPORATE-ACTION-LEDGER-001`。

Core 下一步應判斷：
- 如何把 cash distribution ledger 放入持股現金流。
- 如何處理配股 / price-share factor。
- 是否需要另開 exact ex-date / capital-change official route unlock。
