# P1/P2 primary80 價格來源緊急本機重用稽核

## 結論

- 新增網路下載已停止；cache/checkpoint 全部保留，沒有刪除。
- MA/斜率不需要重新下載全段日價。既有本機 raw 或 trusted comparator 已覆蓋 P1 96.5855%、P2 97.5200% 的分析 key。
- 既有 adjusted series 可直接覆蓋 P1 93.3983%、P2 96.6797%。
- C 類目前仍是 broad planning calendar 的潛在 official raw gap，不是已 materialize 的實際交易 execution leg。必須先由 Core 算完 MA/斜率與 action，再取實際 action dates 交集；不得直接依 C 表恢復下載。
- P1 既有 63 檔問題主要是 adjusted factor、corporate-action 或舊碼來源治理，不是整段每日 raw close 都不存在。

## 停止點

- 中斷點：P2 official raw 1125/1138 routes。
- 中斷 cache：1,169 files / 5,328,292 bytes。
- 中斷下載未混入 pre-existing reuse verdict。
- 中斷前已產生 P2 trusted adjusted delta；official raw delta 尚未 finalize。
- 現在沒有 matching network runner。

## A-E 分類

- A：已有 raw close，可算未調整 MA/斜率。
- B：已有 raw + adjusted series/factor，可重建 research-grade adjusted close。
- C：trusted source 顯示該 key 有交易，但本機未命中 official raw；仍須先與實際 action leg 交集。
- D：raw 已有，只缺 adjusted factor/event；不是每日收盤價缺口。
- E：無 exact trade evidence，需依上市前、停牌、休市或 official no-row 分類，不可直接稱 source gap。

## 為何先前沒有命中

- Core source path registry 未納入後續 Radar selected-price、all80、rank1 packages。
- date/close 欄位存在 schema 差異，需要統一 date/trade_date/price_date 與 close/official_raw_close 等欄位。
- 舊 bulk cache 有 query date 與實際 response market date 混淆風險。
- P3 初版 watchlist scope 與 exact primary80 supplemental package 分離。
- 上市前、停牌與 official no-row 被混入一般 calendar gap。

## 下一步

- 網路維持 disabled。
- Strategy Center 若要續作，應先交 Core 修 local path/schema/calendar ingestion，利用 A/B 計算 MA/斜率與 action ledger。
- Core 只應把 action ledger 中仍缺 official raw 的 exact execution legs 交回 Radar。未做這一步前，不得恢復下載。
- future_data_violation_count=0。

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false
