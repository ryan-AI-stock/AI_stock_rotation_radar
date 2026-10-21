# R1法人資料採購／試用驗收規格

用途：補足R1正式核心52檔的法人EPS共識、12個月目標價及4W／12W歷史修正。取得資料不會自動改變交易決策，必須先通過PIT與欄位驗證。

## 優先洽詢順序

1. CMoney法人決策支援系統／獵報。
2. TEJ台股預估值及券商預測資料庫。
3. LSEG I/B/E/S或FactSet PIT Estimates。
4. Bloomberg僅在既有終端授權可合法匯出時考慮。

## 必問問題

1. 能否匯出CSV、Excel或API，而不只是畫面查詢？
2. 能否取得指定歷史日期當時可見的PIT資料，而不只是目前最新值？
3. 是否保留券商／機構名稱、預估發布日與平台可得日？
4. EPS是否同時包含當年度、下一年度、平均／中位／高低值及分析師家數？
5. 目標價是否為12個月目標價，且可取得逐家機構數值？
6. 是否涵蓋R1正式52檔，特別是6282、2492、3357、6230、3338、3532、6182？
7. 授權是否允許個人模型定期匯入、保存歷史快照及衍生計算？

## EPS匯入必要欄位

`ticker, fiscal_year, mean_eps, median_eps, high_eps, low_eps, analyst_count, source_name, source_url, source_family, source_tier, published_at, available_at, retrieved_at, quality, status`

## 目標價匯入必要欄位

`ticker, institution, target_price, horizon, published_at, available_at, retrieved_at, source_url, source_family, source_tier, quality, status`

## 驗收門檻

- 股票代號必須位於R1核准宇宙。
- `published_at`與`available_at`不得晚於回測／評分日期。
- 不接受只有目前最新值、沒有歷史可得時間的資料充當PIT。
- 目標價必須是12M；90日內至少3家可識別機構才形成嚴格共識。
- 缺值維持NA，不補0、不推估券商名稱。
- 匯入後先輸出accepted／rejected／future-data violation，再由Ryan核准是否採用。

## 試用資料最小要求

先請供應商提供上述7檔、2026-08-05至今的CSV樣本。若樣本無法通過既有匯入器，就不建議購買。完整採購前先確認52檔coverage與歷史深度。

## 邊界

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
