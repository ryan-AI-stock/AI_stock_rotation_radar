# R1 v1.0 Phase 2 Context Engine Report

- 完成日期：2026-10-25
- 狀態：`PHASE2_COMPLETE / RESEARCH_ONLY / SHADOW_MODE`
- 正式R1 Dashboard：未修改
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=false`

## 1. Phase 1 Dedup壓力測試

先以兩個真實公司事件重播，通過後才進Phase 2：

| 事件 | Primary | Secondary | Canonical Event | Claim | 獨立證據 |
|---|---:|---:|---:|---:|---:|
| 台積電2026-07-16上調資本支出 | 1 | 3 | 1 | 4 | 1 |
| 技嘉2026-05-15法說／AI伺服器展望 | 1 | 3 | 1 | 4 | 1 |

Secondary來源保留各自Claim與URL，但不增加事件Impact次數。所有轉載的`primary_lineage_id`回指公司原始法說來源，因此獨立證據只算一份。無法確定是否同事件時保留`POSSIBLE_DUPLICATE`；日期相距超過3日不強制合併。

## 2. 新增模組與Schema

- `context_schema.py`：Market、Theme、Company、Valuation、Flow、Context Snapshot。
- `context_engine.py`：五層固定規則與Attribution。
- `context_store.py`：append-only每日Context History。
- `context_materializer.py`：從既有PIT資料產生52檔影子快照。
- `context_monitor.py`：研究用Context Monitor，不發布到正式Dashboard。
- `context_llm_boundary.py`：限制LLM只能整理理由、正反證據與Unknown。
- `dedup_stress.py`：真實來源壓力測試。

Context Snapshot保存Market、Theme、Company、Valuation、Flow五層完整內容，以及primary／secondary context、信心、正反證據與unknowns；同一snapshot ID不得覆寫。

## 3. Theme Basket設計

沿用`r1-theme-universe-v0.2`的11題材與當時成分股，不回填或改寫Universe。

每題材採成分股等權計算：

- 1D／5D／20D等權報酬。
- 1D中位數、上漲／下跌家數、breadth。
- 相對TAIEX 1D報酬。
- 成交額相對20日均值的中位數作volume state。
- 單一股票大漲不能使題材進入`ACCELERATING`；需相對市場領先且breadth達門檻。

狀態：`ACCELERATING / STABLE / COOLING / SELL_OFF / RECOVERING / UNKNOWN`。

## 4. Market Context方法

使用TAIEX官方當日報酬、R1全池breadth、上漲／下跌家數、全池成交額及成交額相對20日均值。

狀態不是只看單日指數。至少同時檢查價格與breadth；5D／20D TAIEX、TW50、全市場法人、VIX、美股及USD/TWD若尚無可靠PIT輸入，維持`UNKNOWN`並降低confidence。

2026-10-22實際結果：TAIEX -1.81%、R1池52檔中51檔下跌，Market State=`RISK_OFF`。

## 5. Company Relative Move方法

每檔計算1D／5D／20D報酬，以及相對大盤、相對題材等權、相對同題材同業的差異。

- 與題材差距在小範圍：`IN_LINE`。
- 顯著領先／落後：`OUTPERFORMING / UNDERPERFORMING`。
- 顯著異於題材且存在同方向公司事件：`IDIOSYNCRATIC_STRENGTH / STRESS`。
- 自身波動z-score需要累積足夠Context History；不足時不硬算。

## 6. Valuation Context方法

優先使用公司自己的Forward PE五年歷史百分位，不做南亞科與台達電等跨產業PE絕對比較。

狀態：

- `DEPRESSED`：自身百分位≤10%。
- `BELOW_NORMAL`：10%～35%。
- `NORMAL`：35%～70%。
- `ABOVE_NORMAL`：70%～90%。
- `EXTREME`：≥90%。
- 缺歷史百分位：`UNKNOWN`。

PB、EV/EBITDA、EPS revision與1W／4W／12W估值變化只有在真實資料存在時才填入，缺值不補0。

## 7. Flow Context方法

使用官方外資、投信、自營商買賣超股數；物質化時以當日收盤價換算估計淨買賣超金額，再除以當日成交額，避免直接拿「股數」除以「金額」。搭配成交額相對20日均值判斷：

`ACCUMULATING / NEUTRAL / DISTRIBUTING / CROWDED / CAPITULATION / UNKNOWN`。

融資、借券、大戶資料缺漏時保留Unknown。任何Flow狀態都不產生BUY或SELL。

## 8. Attribution方法

歸因順序不是預測模型，而是可稽核的背景分類：

1. 個股顯著異於題材且有公司事件證據：COMPANY。
2. 題材顯著異於大盤：THEME。
3. 大盤RISK_OFF／PANIC且個股大致同步：MARKET。
4. 只有籌碼顯著異常：FLOW。
5. 只有估值位於自身極端：VALUATION。
6. 市場與題材同時成立：PRIMARY=`MIXED`、SECONDARY=`THEME`。
7. 證據不足：UNKNOWN。

大盤、題材與個股同步下跌，且沒有新公司負面事件時，只能標記`POSSIBLE_MISPRICING_CANDIDATE`，不能標記買進。

## 9. LLM邊界

固定程式負責全部報酬、breadth、相對報酬、估值百分位、flow與異常分類。

LLM只可輸出：primary／secondary理由、支持證據、反駁證據、Unknown與可追溯Evidence ID。禁止修改數值、覆寫Market State、建立Thesis、調整部位或輸出BUY／SELL／ADD／TRIM。

## 10. 測試結果

- R1相關測試：293項全數通過。
- Phase 2新增14項測試，涵蓋規格要求的12類情境。
- 真實Dedup壓力測試：2案全數通過。
- Context Snapshot append-only測試：通過。
- Phase 1 PIT與lineage不被Phase 2破壞：通過。
- Missing不補0、LLM禁止交易指令：通過。

## 11. 五個真實案例

以下使用2026-10-22收盤PIT快照；這些是Context歸因，不是交易建議。

### A. 全市場急殺、台積電無新增公司利空

- Evidence：TAIEX -1.81%；R1池51／52檔下跌；台積電當日公司負面事件0。
- Market：RISK_OFF。
- Theme：AI運算／先進製程 COOLING。
- Company：OUTPERFORMING，跌幅小於題材平均。
- Valuation：ABOVE_NORMAL。
- Flow：DISTRIBUTING。
- Attribution：PRIMARY=MIXED，SECONDARY=THEME；不能推論公司惡化。

### B. 矽光子／CPO題材整體大跌

- Evidence：題材6檔全部下跌，等權-6.40%、相對大盤-4.60%。
- Market：RISK_OFF。
- Theme：SELL_OFF。
- Company：聯亞-9.52%，相對題材再落後3.12%，但沒有新增公司負面事件。
- Valuation：NORMAL。
- Flow：依官方資料為NEUTRAL。
- Attribution：PRIMARY=MIXED，SECONDARY=THEME；聯亞只列`POSSIBLE_MISPRICING_CANDIDATE`。

### C. 聯電相對題材異常強勢並有公司公告證據

- Evidence：聯電-1.95%，矽光子／CPO題材等權-6.40%；既有公司技術公告可追溯。
- Market：RISK_OFF。
- Theme：SELL_OFF。
- Company：相對題材+4.45%，`IDIOSYNCRATIC_STRENGTH`。
- Valuation：EXTREME。
- Flow：NEUTRAL。
- Attribution：PRIMARY=COMPANY；這只說明相對走勢與事件一致，不代表應買入。

### D. 國巨股價下跌且估值仍處自身高檔

- Evidence：國巨當日-6.46%，Forward PE自身五年百分位100%。
- Market：RISK_OFF。
- Theme：高階被動元件SELL_OFF。
- Company：IN_LINE，並非單獨崩跌。
- Valuation：EXTREME。
- Flow：DISTRIBUTING。
- Attribution：PRIMARY=MIXED、SECONDARY=THEME；估值擴張是附加背景，不是賣出指令。

### E. 台達電外資賣超、但未見新增公司事件

- Evidence：官方外資買賣超換算約-50.05億元；當日公司事件數0。
- Market：RISK_OFF。
- Theme：電源供應／HVDC／BBU COOLING。
- Company：與題材背景合併判讀。
- Valuation：依資料顯示自身歷史位置，缺欄維持Unknown。
- Flow：DISTRIBUTING。
- Attribution：市場／題材優先，Flow作次級背景；禁止`foreign sell → SELL`。

## 12. Known Limitations

1. Context History目前只有2026-10-22一個完整v1快照，20日歸因頻率與自身波動z-score需之後逐日累積。
2. TAIEX 5D／20D、TW50、VIX、美股、USD/TWD與全市場法人尚未接成Phase 2原生PIT輸入，因此明確列Unknown。
3. 題材報酬使用11題材固定池等權，不代表整個產業全市場報酬。
4. Flow的外資淨額是「官方淨買賣超股數×收盤價」估值，不是逐筆真實成交金額。
5. Forward PE覆蓋有限；PB、EV/EBITDA及估值1W／4W／12W變化缺值較多。
6. 事件正負計數沿用legacy shadow evidence，仍標`LEGACY_PARTIAL`。
7. Possible Mispricing只是待Phase 3驗證的候選，沒有勝率、報酬或買入含義。

## 13. Phase 3建議與Stop Gate

Phase 3若獲核准，才建立Thesis／Hypothesis層，用Context History驗證「系統性賣壓、題材退潮、公司惡化、估值壓縮」等競爭假說。

進入前必須：

1. 保持Phase 1 Evidence與Phase 2 Context append-only。
2. 不把Possible Mispricing直接轉成交易建議。
3. 每個Hypothesis必須列支持、反駁、Unknown與可被推翻的條件。
4. 尚未累積足夠歷史時，結果維持research-only。

本次依規格停在Phase 2，不自動進入Phase 3。
