# R1法人資料採購／試用驗收規格

用途：補足R1正式核心52檔的法人EPS共識、12個月目標價及4W／12W歷史修正。取得資料不會自動改變交易決策，必須先通過PIT與欄位驗證。

## 優先洽詢順序

1. TEJ台股預估值及券商預測資料庫：官方已明確提供API試用與資料匯出能力，先驗證資料表是否含歷史PIT法人預估及逐家目標價。
2. CMoney法人決策支援系統／獵報：台股介面較貼近需求，但購買前必須先證明可以匯出歷史PIT資料，不能只提供目前畫面值。
3. LSEG I/B/E/S或FactSet PIT Estimates。
4. Bloomberg僅在既有終端授權可合法匯出時考慮。

## 官方申請入口與已確認能力

- TEJ API試用與說明：https://www.tejwin.com/insight/tej-rest-api-%E4%BD%BF%E7%94%A8%E6%89%8B%E5%86%8A/
  - 官方確認可申請API KEY、以API取得資料並輸出整理；試用資料範圍有限，仍須向業務確認預估值與券商目標價資料表權限。
- TEJ服務方式：https://www.tejwin.com/service-provide-method/
  - 官方確認API可供個股研究、量化策略與機器學習使用。
- LSEG I/B/E/S：https://www.lseg.com/en/data-analytics/financial-data/company-data/ibes-estimates
  - 官方列出CSV、JSON、Python、SQL、Excel、API與FTP等交付方式，並有全球法人預估歷史。
- FactSet PIT Consensus：https://insight.factset.com/resources/at-a-glance-factset-estimates-point-in-time-consensus
  - 官方說明為每日更新、十年以上歷史的PIT共識資料。
- CMoney公開頁面目前只確認可使用預估盈餘與自訂分析，尚未確認歷史PIT匯出與授權；未取得書面答覆前不列為已通過來源。

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

指定7檔：`6282、2492、3357、6230、3338、3532、6182`。

## 可直接寄給供應商的詢問文字

> 我需要台灣上市櫃股票的法人EPS預估與12個月目標價，用於個人研究模型。請確認是否能以CSV、Excel或API提供「每一歷史日期當時可見」的point-in-time資料，而非只提供目前最新值。EPS需包含年度、平均／中位／高低值、分析師家數、預估發布日與平台可得日；目標價需保留個別機構名稱、12M目標價、發布日與平台可得日。請先提供6282、2492、3357、6230、3338、3532、6182，自2026-08-05至今的試用樣本，並說明個人使用、定期匯入、保存歷史快照及衍生計算的授權範圍。若試用不含該資料表，也請提供正式方案名稱與報價。

## 收到樣本後的本機驗收

1. 將EPS檔整理成 `data/r1/consensus/provider_import_template.csv` 欄位。
2. 將目標價檔整理成 `data/r1/target_prices/provider_import_template.csv` 欄位。
3. 先執行 `python -m r1.provider_consensus_import` 與 `python -m r1.provider_target_price_import`，產出accepted／rejected與future-data violation。
4. 再執行 `python -m r1.provider_bundle_promote`；預設只預覽，不寫正式資料。
5. 只有`status=READY`、`future_data_violation_count=0`且coverage符合報價承諾，才考慮購買與`--apply`。

## 邊界

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
