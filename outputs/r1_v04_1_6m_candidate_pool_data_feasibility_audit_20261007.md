# R1 1–6M Candidate Pool Data Feasibility Audit

- 稽核日期：2026-10-07
- 稽核對象：R1 v0.3 challenger；11 題材、54 檔唯一股票、57 個題材席位
- 目的：評估建立 `ACTIVE_1_6M_POOL` 前的資料可得性與模型設計
- 狀態：`research_audit_only`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=false`

## 一、結論

v0.4 可以做，但不能把五個新概念直接各壓成一個 0～100 分。

正確架構應拆成：

1. **自動量化層**：官方價格、報酬、BIAS、月營收、已公布財報、可驗證的 EPS 共識與分歧。
2. **半自動證據層**：催化事件、公司指引、訂單能見度、產能稀缺、客戶認證與替代難度。LLM 只抽取與分類，不自行創造分數。
3. **6M 風險閘門**：`PASS / CAUTION / FAIL / DATA_MISSING`，不建立模糊的抗跌總分。
4. **信心與覆蓋層**：任何重要資料缺失均保留 `NA / DATA_MISSING / LOW_CONFIDENCE`，不補 0、不重分配權重。

目前可以先建研究版 schema 與累積 PIT 快照；**尚不足以穩定發布 12～18 檔高信心主攻池**。最大缺口是可合法、穩定、可追溯的法人預估歷史，以及 54 檔完整催化／稀缺性證據。

## 二、現況實測

| 資料群 | 現況（截至本次稽核） | 判定 |
|---|---:|---|
| 官方收盤與市場資料 | 2026-10-06：54/54 有官方收盤；6230 缺調整後歷史分析序列 | 可日更；技術指標為 53/54 完整 |
| 官方季財報 | 2026-10-02 舊 50 檔：50/50 損益、資產負債、營業現金流 READY；新增 4 檔尚待下一次重建 | 可季更，PIT 可行 |
| EPS consensus | 46/54 有至少部分 2026E/2027E；2028E 為 40 檔 | PARTIAL |
| 共識擷取 checkpoint | 44 完成、6 失敗；另有 4 檔為其後新增，尚未納入該輪 | 可續跑，但非保證覆蓋 |
| 1W/4W/12W 真實快照歷史 | 最早自 2026-10-02 開始累積；尚無足夠 4W/12W 實際快照 | 尚未成熟 |
| 來源頁面回報的 30D/90D EPS 修正 | 已有 46 檔附近的補充資料，但標為 `SUPPLEMENTAL_NOT_TOTAL_SCORE` | 只可輔助，不能冒充自建 PIT 時序 |
| 五年前瞻估值參考 | 14/54 | 覆蓋不足 |
| 催化事件證據 | 28 筆、14/54 檔 | 覆蓋不足 |
| 瓶頸證據 | 28 筆、14/54 檔 | 覆蓋不足 |

官方資料路線存在且適合自動化：證交所 OpenAPI 提供月營收、損益表、資產負債表與日收盤等資料；MOPS 提供歷史重大訊息、法說會、月營收與財務報告。法人預估則不是主管機關官方資料，目前依賴公開彙總頁，必須視為外部來源而非永久 authority。

## 三、五構面總稽核

| 構面 | 判定 | 更新頻率 | PIT | 歷史回溯 | 自動化 | LLM | 主觀風險 | 建議 |
|---|---|---|---|---|---|---|---|---|
| 1M Catalyst Score | **PARTIAL** | 每日事件掃描；每週彙整 | 可，需保存 `published_at/available_at/retrieved_at` | MOPS事件可回溯；產業研究與公司簡報不保證完整 | 半自動 | 需要抽取與分類 | 中高 | **MODIFY**：改為事件帳本與規則狀態，不先做主觀總分 |
| 6M Earnings Visibility | **PARTIAL** | 月營收每月；財報每季；共識每週 | 官方實績可；共識只能從開始保存日起可靠 | 官方實績佳；歷史法人共識不足 | 混合 | 指引／訂單文字需 LLM | 中 | **KEEP+MODIFY**：保留最高優先，但分成可量化與證據欄位 |
| Bottleneck Scarcity | **PARTIAL** | 每季＋重大事件 | 可，若每條證據有 available_at | 官方與公司資料可回溯但不完整；產業研究受授權與保存限制 | 半自動 | 需要分類 | 高 | **MODIFY**：LOW/MEDIUM/HIGH＋證據，不做假精確 73 分 |
| Price Catch-up Potential | **PARTIAL** | 每日價格＋每週共識＋每月營收 | 價格／營收可；共識需自建快照 | 價格／營收佳；歷史共識與前瞻估值不足 | 高度可自動 | 不需要，僅例外說明 | 低 | **優先 NEW**：先做不依賴歷史共識的 core，再逐步啟用 enhanced |
| 6M Downside Resilience | **PARTIAL** | 每日市場風險＋每週／每季基本面 | 多數可；事件型風險需證據時間 | 價格與財報佳；客戶集中、延遲與供需反轉不足 | 混合 | 事件判讀需要 | 中高 | **MODIFY**：改為 6M Risk Gate |

五項均不是 `AVAILABLE`，因為附件要求的是完整構面，而不是其中某幾個容易取得的欄位。也沒有整項必須 `DROP`；但每項都要拆分或降級。

## 四、1M Catalyst Event Ledger

### 4.1 事件可得性

| 事件 | 可得性 | 主要來源 | 備註 |
|---|---|---|---|
| DESIGN_WIN | PARTIAL | 公司／客戶公告、法說 | 常因保密只用間接語句，不能猜客戶 |
| CUSTOMER_QUALIFICATION | PARTIAL | 公司、客戶、MOPS、法說 | 需要明確認證階段與日期 |
| MASS_PRODUCTION | PARTIAL | 公司公告、法說、客戶公告 | 可規則化，但需區分試產／小量／量產 |
| NEW_PRODUCT | AVAILABLE/PARTIAL | 公司公告、產品頁、法說 | 事件容易取得，營收影響不一定可得 |
| PRICE_INCREASE | PARTIAL | 公司、客戶、TrendForce等產業研究 | 媒體轉述不得單獨升高信心 |
| SUPPLY_SHORTAGE | PARTIAL | 公司、客戶、產業研究 | 缺少可驗證供需數字時只能 LOW_CONFIDENCE |
| CAPACITY_TIGHTNESS | PARTIAL | 公司法說、產業研究 | 不可把「需求佳」直接等同產能吃緊 |
| CUSTOMER_PREPAY | PARTIAL | MOPS、財報、重大訊息 | 若沒有具體合約／會計證據則 NA |
| LONG_TERM_AGREEMENT | PARTIAL | MOPS、公司／客戶公告 | 合約期間與金額可能未揭露 |
| CAPACITY_EXPANSION | AVAILABLE/PARTIAL | MOPS、董事會重大訊息、法說 | 擴產可得，但不等於需求已兌現 |
| GUIDANCE_UP | PARTIAL | 法說、公司財測／簡報 | 台灣公司正式財測覆蓋不普遍 |
| MONTHLY_REVENUE_ACCELERATION | **AVAILABLE** | TWSE／TPEx／MOPS月營收 | 可完全規則化，需處理季節性與基期 |
| EARNINGS_CALL_POSITIVE_REVISION | PARTIAL | 法說逐字稿／簡報 | 需比較前後指引，不能只判斷正面語氣 |
| STRATEGIC_INVESTMENT | AVAILABLE/PARTIAL | MOPS、公司／投資方公告 | 必須另判斷是否直接改變獲利路徑 |

### 4.2 建議 schema

每一事件一列，不先產生主觀 0～100：

`ticker, catalyst_type, catalyst_date, published_at, available_at, retrieved_at, expected_impact_start, expected_impact_end, expected_impact_window, earnings_path, impact_direction, confidence, source_count, independent_source_family_count, source_quality, primary_source_url, corroborating_source_urls, evidence_excerpt, evidence_status, decay_state`

規則：

- `confidence` 只用 `HIGH / MEDIUM / LOW`。
- `HIGH` 至少要有一個 Tier 1 官方／公司來源，且關鍵敘述可直接驗證。
- 只有媒體轉述時最高為 `LOW`；兩篇轉載同一消息不算兩個獨立來源。
- `earnings_path` 限定枚舉：`REVENUE / ASP / VOLUME / MARGIN / CAPEX / CUSTOMER_LOCK_IN / COST / UNKNOWN`。
- LLM 只負責從原文提出候選欄位；規則驗證器負責日期、來源層級、獨立來源數與合法值。
- 無法確認營收影響時填 `UNKNOWN`，不能因語氣樂觀給高分。

## 五、6M Earnings Visibility

### 5.1 可量化與不可量化部分

| 元件 | 判定 | 實作方式 |
|---|---|---|
| 2026E/2027E/2028E EPS | PARTIAL | 現有公開彙總 46/54；2028E 40/54；需保存每週 append-only snapshot |
| EPS revision 1W/4W/12W | UNRELIABLE（目前） | 真實快照只自 2026-10-02 累積；滿足週距後才逐欄啟用 |
| Analyst Count | PARTIAL | 來源頁可取得；需和每一 fiscal year、available_at 綁定 |
| High/Median/Low | PARTIAL | 多數有覆蓋；低分析師數時不得視為可靠分歧 |
| Revenue consensus | PARTIAL/UNRELIABLE | 個別頁可見，但目前 R1 ingestion 未建立 54 檔穩定契約 |
| Gross/Operating Margin trend（實績） | AVAILABLE | TWSE／TPEx季財報；只使用已公告季度 |
| Forward margin consensus | UNRELIABLE | 無付費共識 authority，覆蓋與歷史不穩定 |
| Monthly Revenue | AVAILABLE | 官方月營收；月更，可做季節性／3M加速 |
| Company Guidance | PARTIAL | 法說與公告；半自動事件證據 |
| Order Visibility | PARTIAL | 法說／年報／客戶公告；多為文字與區間 |
| Capacity Utilization | PARTIAL | 公司揭露不一致，不能要求所有股票都有 |

### 5.2 `ESTIMATE_DISPERSION`

只在 `analyst_count >= 3` 且 high/median/low 同期可得時計算：

`estimate_dispersion = (high_eps - low_eps) / abs(median_eps)`

- median 為 0 或三欄不完整：`NA`。
- 分歧度越高，降低 `DATA_CONFIDENCE`，而不是直接把獲利趨勢改成負面。
- 建議同時保存 `analyst_count`，避免 3 人與 30 人的分歧被視為同等可靠。

### 5.3 建議輸出

現階段不先凍結單一加權分數，先輸出可追溯的狀態：

- `EPS_REVISION_STATE`: UP / FLAT / DOWN / DATA_MISSING
- `ESTIMATE_DISPERSION_STATE`: LOW / MEDIUM / HIGH / DATA_MISSING
- `REVENUE_MOMENTUM_STATE`: ACCELERATING / STABLE / DECELERATING / DATA_MISSING
- `GUIDANCE_DIRECTION`: UP / UNCHANGED / DOWN / UNKNOWN
- `ORDER_VISIBILITY`: HIGH / MEDIUM / LOW / UNKNOWN
- `MARGIN_DIRECTION`: EXPANDING / STABLE / CONTRACTING / DATA_MISSING
- `EARNINGS_VISIBILITY`: HIGH / MEDIUM / LOW / DATA_MISSING

待至少 12 週真實 PIT 共識累積後，再研究是否需要數值分數；不能用來源頁回報的歷史偏移值取代自建快照做回測。

## 六、Bottleneck Scarcity

建議季度＋事件更新，輸出七個 ordinal 欄位：

- `AI_BOTTLENECK_DIRECTNESS`
- `TECHNICAL_BARRIER`
- `SUPPLIER_CONCENTRATION`
- `SUBSTITUTION_DIFFICULTY`
- `QUALIFICATION_BARRIER`
- `CAPACITY_SCARCITY`
- `CUSTOMER_LOCK_IN`

每欄只能為 `LOW / MEDIUM / HIGH / NA`，並必須附：

`evidence_note, source_url, source_family, source_tier, published_at, available_at, reviewed_at`

判定原則：

- 官方市場占有率、客戶認證、長約、預付款、明確產能利用率與交期可支撐 HIGH。
- 公司自行宣稱「技術領先」但沒有外部或客戶證據，最高 MEDIUM。
- 沒揭露不等於 LOW；必須是 NA。
- LLM 可以把證據映射到七類，但不能直接輸出 HIGH，也不能補公司未揭露的客戶或市占。

現有證據只有 14/54 檔，不能直接形成全池相對排名。

## 七、Price Catch-up Potential

### 7.1 Core（可先做）

- `price_change_1w/4w/12w`
- `bias20/bias60`
- `monthly_revenue_yoy`
- `revenue_momentum_3m`
- 已公布財報的 EPS、毛利率與營益率方向
- `position_120td`、波動與歷史回撤

### 7.2 Enhanced（資料成熟後啟用）

- `eps_revision_1w/4w/12w`
- `forward_pe_change_1w/4w/12w`
- `fair_value_change_1w/4w/12w`
- `historical_forward_pe_percentile`

### 7.3 計算方式

每個窗口分開，不跨窗口混算：

`price_eps_gap_N = eps_revision_N - price_change_N`

狀態：

- `EARNINGS_LEADS_PRICE`：EPS 修正為正，且 gap 明顯為正。
- `POSITIVE_DIVERGENCE`：股價下跌、EPS 上修。
- `PRICE_LEADS_EARNINGS`：股價上漲顯著快於 EPS。
- `NEGATIVE_DIVERGENCE`：股價上漲、EPS 下修。
- `INCONCLUSIVE / DATA_MISSING`：訊號不足或缺資料。

`CATCH_UP_SCORE` 只在同一窗口、同一資料完整門檻下，對當期合格股票做百分位；不以人工敘事加分。若 EPS 歷史未成熟，僅發布 `CATCH_UP_CORE_STATE`，不得冒稱完整 Catch-up。

## 八、6M Risk Gate

結論：**應改成 Risk Gate，不做總分。**

### 可自動檢查

- EPS 4W/12W 下修（待快照成熟）
- 自身歷史估值極端（目前僅 14/54 有前瞻參考；其餘可用 PIT trailing valuation，但須另標）
- 價格波動與歷史最大回撤
- 資產負債、營業現金流、毛利率與營益率惡化
- 收入與獲利動能下降

### 半自動事件風險

- 重大客戶流失／集中度惡化
- 產品量產延遲
- 產業供需明確反轉
- 擴產執行延遲或成本失控

### Gate 規則

- `FAIL`：至少一項具可驗證證據的重大風險條件成立。
- `CAUTION`：非致命風險成立，或多項風險轉弱。
- `PASS`：必要量化欄位完整且沒有 FAIL/CAUTION 證據。
- `DATA_MISSING`：重要欄位不足；**不得當 PASS**。

不得使用「一個媒體標題」直接觸發 FAIL；重大事件至少要有 Tier 1 來源，或兩個獨立高品質來源。

## 九、兩層候選池

### `STRUCTURAL_UNIVERSE`

- 保留 11 題材、54 檔唯一股票。
- 題材半年檢視、結構性領先地位季度檢視。
- 不因短期價格漲跌退出結構池。

### `ACTIVE_1_6M_POOL`

12～18 檔只能是**目標區間，不是硬湊名額**。准入必須同時符合：

1. Bottleneck Directness 與 Scarcity 證據達最低門檻。
2. `EARNINGS_VISIBILITY` 不為 LOW 或 DATA_MISSING。
3. `6M_RISK_GATE` 為 PASS 或經明確政策允許的 CAUTION；FAIL 不得進入。
4. Catalyst 或 1–6M earnings path 至少一項有明確 evidence。
5. Catch-up 為正向或至少不是明確 `PRICE_LEADS_EARNINGS / NEGATIVE_DIVERGENCE`。
6. `DATA_CONFIDENCE` 達最低門檻。

如果只有 7 檔符合，就發布 7 檔；不能為了維持 12 檔，把缺資料或低信心股票塞入。

主攻排序輸出：

`ACTIVE_POOL_RANK, 1M_CATALYST_STATE, 6M_EARNINGS_VISIBILITY, BOTTLENECK_SCARCITY, PRICE_CATCH_UP, 6M_RISK_GATE, DATA_CONFIDENCE`

全部維持 `active_in_trade_decision=false`。

## 十、換倉研究輸出

`ROTATION_ADVANTAGE` 不應先做單一黑箱分數。先輸出逐欄比較：

| 欄位 | Current Holding | Challenger | 優勢方 | 信心 |
|---|---|---|---|---|
| 結構性瓶頸 |  |  |  |  |
| 獲利可見度 |  |  |  |  |
| 1M催化 |  |  |  |  |
| Price Catch-up |  |  |  |  |
| 6M Risk Gate |  |  |  |  |
| 目前估值 |  |  |  |  |
| EPS Revision |  |  |  |  |

只有在雙方相同欄位都有資料時才能比較；缺資料保持 `INCOMPARABLE`。輸出只供 Ryan 判斷，不產生自動買賣。

## 十一、v0.4 Proposal

### KEEP

- 11 題材 `STRUCTURAL_UNIVERSE`。
- 官方價格、月營收、季財報、現金流、資產負債與 PIT/available_at 治理。
- 現有 `NA_NO_ZERO_NO_REWEIGHT`、future-data 禁止與 append-only 快照政策。
- 結構性龍頭季度審查、題材成分半年審查。
- R1 只作 research challenger，不產生自動交易。

### MODIFY

- `1M Catalyst Score` → `Catalyst Event Ledger + 1M_CATALYST_STATE`。
- `6M Earnings Visibility Score` → 六個可觀測子狀態；快照成熟後再評估是否數值化。
- `Bottleneck Scarcity` → 七項 LOW/MEDIUM/HIGH/NA，逐項 evidence_note。
- `Price Catch-up` → Core 與 Enhanced 兩層，避免因共識缺失整欄停擺。
- `6M Downside Resilience` → `6M_RISK_GATE`。
- 固定 12～18 檔 → 目標 12～18 檔，實際檔數由完整准入條件決定。

### DROP

- 沒有證據支持的 Catalyst／Scarcity／Resilience 主觀 0～100。
- 資料缺失時補 0、重分配權重或以 LLM 猜值。
- 僅因近期漲幅、低 PE 或正面新聞就加入主攻池。
- 用目前截面 consensus 回填過去歷史，或把來源頁的歷史偏移欄當成自建 PIT 快照。

### NEW

- `ACTIVE_1_6M_POOL` 與准入理由／排除理由。
- `CATALYST_EVENT_LEDGER`。
- `ESTIMATE_DISPERSION` 與 analyst-count confidence。
- `PRICE_EPS_GAP_1W/4W/12W`。
- `CATCH_UP_CORE_STATE / CATCH_UP_ENHANCED_STATE`。
- `6M_RISK_GATE`。
- `DATA_CONFIDENCE`、component coverage 與 `INCOMPARABLE`。
- `ROTATION_ADVANTAGE` 逐欄比較表，研究用途、不產生交易指令。

## 十二、七個問題的直接答案

1. **可穩定自動化**：官方收盤、報酬、BIAS、波動／回撤、成交金額、月營收、已公布季財報、資產負債與營業現金流；在來源仍可用且有完整快照後，也可自動算 EPS dispersion、price–EPS gap。
2. **只能半自動**：設計勝出、客戶認證、量產、漲價、供需吃緊、公司指引、訂單能見度、稀缺性、客戶鎖定、量產延遲與供需反轉。LLM抽取，規則與證據驗證，人類處理歧義。
3. **目前不建議加入正式排序**：歷史 1W/4W/12W 共識修正、全池 forward PE 歷史分位、forward fair-value change、forward margin consensus、供應商集中度與客戶集中度的跨公司精確比較。原因是覆蓋或歷史不足。
4. **6M Downside Resilience應否改 Risk Gate**：是。`PASS / CAUTION / FAIL / DATA_MISSING` 比假精確總分可靠。
5. **能否穩定維持12～18檔**：目前不能保證。只可把 12～18 當目標；現有催化與瓶頸證據僅 14/54，前瞻估值參考也僅 14/54，硬維持檔數會降低標準。
6. **最大資料瓶頸**：第一是可合法持續取得、具歷史 PIT 的法人 EPS／營收／毛利率共識與修正；第二是54檔一致格式的公司指引、訂單、產能與客戶認證；第三是長期前瞻估值歷史。現有公開共識頁可作 current research input，但不是主管機關 authority，也無法保證永久可用或完整歷史。
7. **能否不製造假精確完成v0.4**：可以。條件是採用量化值＋ordinal evidence＋risk gate＋confidence/coverage，且不強迫每檔都有總分、不強迫池內固定12～18檔。

## 十三、建議的實作順序（待 Ryan 核准後）

1. 先建 schema 與 append-only snapshots，不改 R1 v0.3 排名。
2. 補 54 檔官方月營收、季財報與市場資料完整性。
3. 持續累積每週 consensus，滿 4W／12W 後逐欄解鎖。
4. 建 Catalyst Event Ledger 與來源去重／證據閘門。
5. 建 Catch-up Core；Enhanced 僅對完整股票啟用。
6. 建 6M Risk Gate。
7. 先影子發布 `ACTIVE_1_6M_POOL`，觀察 coverage、穩定性與換榜原因；仍維持 `active_in_trade_decision=false`。

## 十四、來源與限制

- [臺灣證券交易所 OpenAPI](https://openapi.twse.com.tw/)：月營收、財務報表與市場資料等官方資料集。
- [公開資訊觀測站](https://mops.twse.com.tw/mops/web/t57sb01_q3)：重大訊息、公告、法說會、月營收與財報查詢。
- [ToAlpha 共識頁範例](https://toalpha.tw/stock/2330/estimates)：現有 R1 公開法人共識補充來源；頁面提供年度 EPS、分析師家數與高低區間，但非主管機關官方預估資料。
- [ToAlpha 估值頁範例](https://toalpha.tw/stock/2330/valuation)：可取得部分歷史估值位置；頁面本身亦說明其共識歷史自 2026 年 9 月才開始保存，因此不能當成完整歷史 PIT authority。

本稽核沒有修改 R1 v0.3 正式研究評分、每日 Dashboard、持股、換倉或任何交易決策。
