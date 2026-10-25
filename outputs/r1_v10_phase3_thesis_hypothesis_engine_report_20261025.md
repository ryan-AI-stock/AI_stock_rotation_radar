# R1 v1.0 Phase 3 Thesis & Hypothesis Engine Report

- 完成日期：2026-10-25
- 狀態：`PHASE3_COMPLETE / RESEARCH_ONLY / SHADOW_MODE`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=false`

## 1. 新增模組

- `reasoning_schema.py`：Thesis、Causal Node／Edge、Hypothesis、Expectation、Disconfirmation、Reasoning Snapshot。
- `reasoning_engine.py`：版本更新、競爭解釋、反證、推翻條件與Expectation Gap。
- `reasoning_store.py`：append-only研究帳本。
- `reasoning_materializer.py`：將Phase 1 Evidence與Phase 2 Context轉成52檔影子研究紀錄。
- `reasoning_llm_boundary.py`：禁止LLM造Fact、來源、數值及交易指令。
- `reasoning_monitor.py`：研究用Reasoning Monitor，不進正式Dashboard。

實際產出：52份初版Thesis、260個Causal Node、208個Causal Edge、133個競爭Hypothesis、52筆Expectation Analysis、52次Disconfirmation Pass、52份Reasoning Snapshot。

## 2. Thesis版本機制

Thesis以`stock_id + thesis_type + version`保存，不覆蓋前版。初版使用11題材既有bottleneck thesis，並標記`LEGACY_PARTIAL / UNKNOWN`。

只有以下情況才產生新版本：

- 兩個以上獨立lineage支持同一結論：`STRENGTHENED`。
- 兩個以上獨立lineage反駁：`WEAKENED`。
- 關鍵官方反證觸發invalidation：`BROKEN`。
- 其餘：`UNCHANGED`。

單日價格、單篇媒體、同源轉載不能改變Thesis。

## 3. Causal Chain

每檔先建立五節點：

AI基礎設施需求 → 題材瓶頸／載體 → 公司營收或毛利兌現 → 獲利修正 → 估值與價格反映。

每個Node與Edge分別標記`CONFIRMED / INFERENCE / UNKNOWN / CONTRADICTED`。目前「AI需求→題材瓶頸」多數仍為INFERENCE；「公司兌現→EPS→估值」因資料不足維持UNKNOWN，沒有把整條鏈假裝成已確認。

## 4. Hypothesis Engine

每檔依Context產生2～4個競爭解釋，並保持Context與Hypothesis分離。目前支援：

- SYSTEMIC_SELL_OFF
- THEME_DERATING
- COMPANY_THESIS_DAMAGE
- FUNDAMENTAL_MISPRICING
- VALUATION_COMPRESSION
- TEMPORARY_EXECUTION_DELAY

全部初始狀態為`UNRESOLVED`，信心只使用LOW／MEDIUM／HIGH，不輸出假精確機率。

## 5. Counter Evidence與Falsification

每個Hypothesis保存支持、反駁、缺少證據、預期解決時間與可被推翻條件。反駁證據只追加、不刪除。一般反證使Hypothesis轉為`WEAKENING`並降低confidence；關鍵反證可轉為`REJECTED`。

同一Evidence ID不重複計算，同一`primary_lineage_id`的公司法說及媒體轉載只算一份獨立確認。

## 6. Expectation Analysis

支援`BETTER_THAN_EXPECTED / IN_LINE / WORSE_THAN_EXPECTED / UNKNOWN`。只有expected與actual同時具備可追溯來源才比較；目前多數缺完整PIT市場預期，因此保留UNKNOWN，不能把EPS成長直接當正向驚喜。

## 7. LLM Disconfirmation Pass

每個Leading Hypothesis都保存一次反確認檢查：

1. 衝突證據。
2. 更簡單替代解釋。
3. 是否把市場誤當公司。
4. 是否把相關當因果。
5. 是否忽略price-in。
6. Leading Hypothesis最可能錯在哪裡。

LLM只能整理可追溯Evidence ID，不能創造Fact、來源、數值、正式Thesis更新或交易指令。

## 8. 測試結果

- R1相關307項測試全部通過。
- Phase 3新增14項，完整涵蓋：Evidence去重、Counter降低confidence、關鍵反證Reject、Unknown、單日價格與單篇新聞不得Break Thesis、lineage獨立性、長期UNRESOLVED、Thesis版本、Reasoning append-only、LLM來源守門、PIT、Phase 1／2 lineage完整及禁止交易輸出。

## 9. 五個真實案例

以下均使用截至2026-10-22可得資料；只展示研究推理，不是交易建議。

### A. 南亞科：DRAM上漲是結構性供需或短期Cycle？

- Evidence：南亞科官方售價／AI UWIO資訊；TrendForce DRAM供需研究。
- Context：Market RISK_OFF；Memory題材COOLING；公司價格與題材共同下跌。
- Causal Chain：AI需求→記憶體需求為INFERENCE；產能排擠→傳統DRAM短缺為INFERENCE；ASP→毛利→EPS仍UNKNOWN。
- Hypotheses：SYSTEMIC_SELL_OFF、THEME_DERATING；另需觀察SUPPLY_SHORTAGE_STRENGTHENING與短期Cycle解釋。
- Counter：新增產能、合約價反轉、庫存回補停止、公司指引轉弱。
- Unknown：獨立客戶確認、持續合約價、EPS revision歷史。
- Confidence：LOW。
- Thesis Impact：UNKNOWN／UNCHANGED；尚不足以宣稱結構性短缺已確認。

### B. 聯亞：CPO Sell-off是錯殺或估值修正？

- Evidence：公司既有公開資料；10/22 CPO題材6檔全跌、等權-6.40%，聯亞-9.52%。
- Context：Market RISK_OFF；Theme SELL_OFF；Company UNDERPERFORMING；Valuation NORMAL。
- Hypotheses：SYSTEMIC_SELL_OFF、THEME_DERATING、FUNDAMENTAL_MISPRICING。
- Counter：若市場恢復但聯亞持續落後，或新增官方負面Fact，錯殺假說轉弱。
- Unknown：fresh company facts、expectation gap、20D／60D Context。
- Confidence：LOW。
- Thesis Impact：UNKNOWN；Possible Mispricing仍只是候選。

### C. 國巨：村田產品調整是否形成EPS Catalyst？

- Evidence：既有高階MLCC產業報導；尚缺村田與國巨兩端可對接的官方量價證據。
- Context：Market RISK_OFF；被動元件Theme SELL_OFF；Company IN_LINE；Valuation EXTREME。
- Hypotheses：SYSTEMIC_SELL_OFF、THEME_DERATING、VALUATION_COMPRESSION；Catalyst尚未獲獨立確認。
- Counter：產品調整未形成訂單轉移、ASP／稼動率未改善、EPS revision沒有上修。
- Unknown：客戶轉單、產品組合、實際ASP及EPS貢獻。
- Confidence：LOW。
- Thesis Impact：UNKNOWN／UNCHANGED，不能把產業消息直接寫成公司EPS Fact。

### D. 台達電：AI Power需求是否支持高估值？

- Evidence：現有電源／HVDC需求證據；10/22外資賣超與估值資料。
- Context：Market RISK_OFF；Power題材COOLING；Flow DISTRIBUTING；估值位階需持續追蹤。
- Causal Chain：AI功率密度→電源需求為INFERENCE；台達電營收／毛利兌現與估值支撐仍UNKNOWN。
- Hypotheses：SYSTEMIC_SELL_OFF、THEME_DERATING、VALUATION_COMPRESSION。
- Counter：AI電源營收占比不足、毛利未改善、競爭加劇、估值先行price-in。
- Unknown：AI Power營收拆分、客戶官方確認、估值1W／4W／12W變化。
- Confidence：LOW。
- Thesis Impact：UNKNOWN，法人賣超不等於Thesis破壞。

### E. 聯發科：NVIDIA合作／Custom ASIC是否改變中期Earnings Thesis？

- Evidence：MOPS財報與S&P Global ASIC研究來源。
- Context：Market RISK_OFF；Compute題材COOLING；Company IN_LINE；Valuation EXTREME。
- Causal Chain：合作／ASIC機會→營收貢獻→毛利與EPS，目前後三節仍UNKNOWN。
- Hypotheses：SYSTEMIC_SELL_OFF、THEME_DERATING、VALUATION_COMPRESSION；EARNINGS_ACCELERATION待後續Fact確認。
- Counter：量產延遲、營收占比不足、毛利稀釋、客戶集中、EPS revision轉負。
- Unknown：量產時間、訂單與營收規模、毛利、客戶官方確認。
- Confidence：LOW。
- Thesis Impact：UNKNOWN／UNCHANGED；合作消息尚不足以改寫中期Earnings Thesis。

## 10. Known Limitations

1. 完整v1 Context History僅一日，不能做20D／60D推理校準。
2. 初版Thesis來自題材bottleneck contract，不是逐公司完整投資備忘錄，故標LEGACY_PARTIAL。
3. 多數公司缺AI營收占比、客戶確認與完整PIT expectation history。
4. 現有Event方向多為legacy分類，仍需原生v1反證資料持續累積。
5. Leading Hypothesis目前依固定可稽核順序排列，尚未經歷史命中率校準。
6. 本階段沒有績效、勝率或交易用途。

## 11. Phase 4建議

Phase 4若獲核准，應建立Relative Opportunity與Portfolio State前的研究層，但必須先累積Context／Reasoning History並校準Hypothesis resolution。任何排序仍不得直接成為交易，除非另外通過同口徑forward與風險驗收。

本次依規格停在Phase 3，不自動進入Phase 4。
