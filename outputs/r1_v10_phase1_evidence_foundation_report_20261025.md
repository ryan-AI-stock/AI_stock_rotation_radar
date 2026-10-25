# R1 v1.0 Phase 1 — Evidence Foundation

- 完成日期：2026-10-25
- 狀態：`PHASE1_COMPLETE / RESEARCH_DEBUG_ONLY`
- 範圍：只建立平行 `r1_v1` 證據底座；未進入 Phase 2
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=false`

## 1. 本階段完成內容

1. 新增獨立命名空間 `r1_v1/` 與資料區 `data/r1_v1/`，未覆寫現行 R1 v0.x。
2. 建立六個可追溯物件：Evidence Source、Fact、Event、Claim、Event-Claim Link、Claim-Evidence Link。
3. Fact 明確區分 `ACTUAL / FORECAST / CONSENSUS / OPINION / RESEARCH_ESTIMATE`；缺值不補 0。
4. 所有來源、Fact、Event、Claim、拒絕與去重決策都有 append-only audit log。
5. PIT gate 以 `available_at <= evaluation_time` 判定；未來資料拒收並寫入 rejection/audit。
6. 修訂資料保留每個 revision，不覆蓋舊值；`previous_revision_id` 只連接同一公司、同一期間、同一來源的前版共識。
7. Event 去重採可解釋規則：公司、事件類型、日期、產品、客戶、數字與原始來源 lineage。文字相似度不能單獨合併；日期相距超過3日視為不同事件。
8. 同一原始來源被多篇媒體轉載時，以 `primary_lineage_id` 只計一份獨立證據。
9. 支持與反駁證據可同時連到同一 Claim，不把反例刪掉。
10. LLM 邊界已鎖定：只能抽取／整理 Claim，不能建立 Fact，也不能產生買賣、部位或權重指令。
11. 舊資料只做 shadow migration，標記 `LEGACY_PARTIAL`；不把舊資料假裝成完整 v1 原生資料。
12. 建立 Evidence Monitor JSON，只供研究與除錯，不發布至正式 Dashboard。

## 2. Shadow migration 實際 coverage

截至本次匯入：

| 物件 | 數量 |
|---|---:|
| Evidence Source | 133 |
| Fact | 1,448 |
| Event observation | 104 |
| Canonical Event | 104 |
| Claim | 104 |
| Event-Claim Link | 104 |
| Claim-Evidence Link | 104 |
| Audit record | 1,789 |
| Future-data violation | 0 |
| Possible duplicate | 0 |

來源類別：交易所／MOPS 24、公司官方 30、產業研究 48、一般媒體 31。

注意：這是「既有資料能被新架構吸收的範圍」，不是 R1 所需證據已完整。Consensus 舊表沒有逐列原始 URL，因此以 `legacy://` 並標 `LEGACY_PARTIAL`；只有未來原生匯入具備真正來源 URL 才能升級為完整證據。

## 3. 實際案例

1. **中砂 1560 月營收**：2026-07 MOPS 月營收 886,323,000 元，分類為 `ACTUAL` Fact；2026-08 是不同期間，不誤連成前值修訂。
2. **中砂 1560 EPS 共識**：2026 年 mean EPS 14.54，分類為 `CONSENSUS`，不是公司實績；10/05、10/06 等每日快照以 revision chain 保留。
3. **台積電 2330 資本支出上調**：公司法說逐字稿建立 `CAPEX_UP` Event，並以 Claim 表達「AI與先進製程需求支持資本支出」；Event 本身不被當成已驗證財務 Fact。
4. **台積電 2330 產能吃緊**：TrendForce 研究建立另一個 `CAPACITY_TIGHTNESS` Event；因事件型別與日期不同，不與資本支出事件合併。
5. **南亞科 2408 售價／產能訊息**：官方財報建立 `PRICE_INCREASE` Event；方向可記錄為正向 Claim，但不直接轉成買進建議。

## 4. 驗收

- R1 全測試：279項通過。
- Phase 1 新增14項測試，涵蓋規格要求的12類：PIT接受／拒絕、revision保留、同事件去重、不同事件分離、possible duplicate保留、Fact與Forecast分離、支持與反駁並存、primary lineage去重、缺值不補0、audit完整、legacy不改正式資料，以及LLM禁止寫Fact／交易指令。
- `git diff --check`：通過。
- 現有 R1 v0.x Dashboard、評分、交易建議與排程：未修改。

## 5. 本階段仍不回答的問題

Phase 1 只回答「證據是什麼、何時可得、來自哪裡、是否修訂、彼此是否為同一事件」。它尚不能回答：

- 一檔股票的投資 thesis 是否成立。
- 哪一項事件應提高或降低持有優先級。
- 消息屬短期雜訊、中期催化或結構變化的最終判斷。
- 是否應換股、買入、賣出或調整部位。
- R1 的投資建議是否優於基準。

## 6. Phase 2 建議與 stop gate

下一階段應建立 Context Engine，但開始前需另行核准。Phase 2 不得直接把新聞正負面轉成交易；應先讓同一 Claim 在市場、題材、公司、供應鏈、時間尺度中被判讀，並保留反例與 UNKNOWN。

Phase 2 開始條件：

1. Phase 1 schema 與 append-only contract 凍結。
2. 原生來源新增時必須具備真實 URL、available_at、retrieved_at 與 primary lineage。
3. Context 輸出仍為 research-only，不寫正式 Dashboard 或交易建議。
4. 未通過 PIT、來源獨立性與反例測試時停止，不進入 Thesis Engine。
