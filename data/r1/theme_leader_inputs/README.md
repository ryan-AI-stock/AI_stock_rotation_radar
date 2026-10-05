# R1 v0.3 題材評分輸入

正式輸入檔為 `latest.json`，只接受訊號日當時可取得且可追溯的資料。每列至少包含：

- `ticker`、`company`、`as_of_date`
- 季度 Top3 五構面：`bottleneck_directness`、`industry_technology_position`、`ai_revenue_realization`、`financial_earnings_quality`、`market_representation`
- 優先持有值五構面：`structural_leader`、`revenue_earnings_growth`、`self_historical_valuation`、`price_risk_safety`、`demand_order_catalyst`
- 各構面的 `source_url`、`source_date`、`available_at`、`source_family`、`evidence_note`

所有分數範圍為 0～100。資料不足填 `null`，不得填 0、不得用目前資訊回填歷史、不得因缺一項而重配其他權重。
