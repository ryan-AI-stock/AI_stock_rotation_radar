# AI-R1 Market Signal Audit

稽核日期：2026-10-03  
模型狀態：challenger；Action policy 尚未核准。  
邊界：`formal_model_changed=false`、`trade_decision_changed=false`、`active_in_trade_decision=false`、`report_changed=true`。

| 功能 | 狀態 | 程式位置 | 資料來源／頻率 | Score | Action | 歷史 | 缺失與修改 |
|---|---|---|---|---|---|---|---|
| Price Signal | PARTIAL | `r1/market_snapshot.py`, `r1/daily_sources.py` | TWSE/TPEx官方；每日 | 價格籌碼骨架 | 否 | 約20TD | Close、報酬、MA、BIAS、成交額已具備；BIAS百分位、真實成交量比率、異常狀態未完成 |
| Chip / Flow | PARTIAL | `r1/daily_sources.py`, `r1/weekly_snapshot.py`, `r1/market_signal_state.py` | 官方三大法人、融資融券；每日 | 欄位存在，完整分數未落地 | 否 | 約20TD | 當日值、外資加投信5D/20D及FLOW_STATE已接；dealer可靠性與更多流向交叉驗證未完成 |
| EPS / Fundamental | PARTIAL | `r1/consensus_snapshot.py`, `r1/weekly_snapshot.py` | 公開法人共識；每週 | EPS score骨架已接 | 否 | 自2026-10起累積 | 目前主要為下年度EPS；本年度、下下年度及完整1W/4W/12W尚未成熟 |
| Forward valuation | PARTIAL | `r1/valuation.py`, `r1/valuation_snapshot.py`, `r1/weekly_snapshot.py` | 五年Forward PE定位；每週 | 估值score骨架 | 否 | 快照開始累積 | Base公允價值及PE/Fair Value/Upside 1W變化已接；Bear/Bull PE分位與4W/12W變化未完成 |
| Industry / Event | PARTIAL | `r1/catalyst_evidence.py`, `r1/bottleneck_evidence.py` | 公告／證據表；事件／每週 | 構面骨架 | 否 | 證據有日期 | 事件類別與證據存在；訂單→稼動率→ASP→營收→毛利→EPS傳導鏈未物化 |
| Market Signal State | PARTIAL | `r1/market_signal_state.py`, `r1/weekly_snapshot.py` | 週快照 | 否 | 否 | 自新快照累積 | EPS_STATE、VALUATION_STATE、FLOW_STATE已建立；PRICE/BOTTLENECK/CATALYST_STATE待建 |
| Trend Confirmation | PARTIAL | `r1/market_signal_state.py`, `r1/weekly_snapshot.py` | 跨週快照 | 否 | 否 | 自新快照累積 | EPS連續週數、stage及confidence已建立；多構面Trend 1W/2W/4W/12W待建 |
| Price vs Earnings | PARTIAL | `r1/price_eps.py`, `r1/weekly_snapshot.py` | 價格＋EPS快照；每週 | 尚未 | 否 | EPS歷史累積中 | 已統一為 earnings minus price，新增正／負背離；尚未進Action |
| Signal Stage | PARTIAL | `r1/market_signal_state.py` | 每週 | 否 | 否 | 自新快照累積 | WAIT/EARLY/CONFIRMING/CONFIRMED/DETERIORATING已用EPS持續週數產生；尚未結合產業與估值 |
| Source vs Target rotation | MISSING | `r1/rotation.py`僅有金額差與10%上限 | 需完整Score/Trend | 否 | 否 | 無 | 尚無成對ROTATION_ADVANTAGE比較 |
| Staged rotation | MISSING | `r1/scoring.py`目前只有ADD/KEEP/TRIM/EXIT骨架 | 每週 | 否 | 未核准 | 無 | TRIM_1/TRIM_2與ADD_1/ADD_2/FULL_POSITION待建 |
| Natural Convergence | MISSING | 尚無 | Portfolio週評估 | 否 | 否 | 無 | 現有持股不強砍的收斂狀態機待建 |
| Dashboard market message | PARTIAL | `r1/dashboard_payload.py`, `r1/dashboard_schema.py` | 每日發布 | 不適用 | 顯示用 | 讀取最近有效週快照 | 已顯示Price/EPS、EPS stage/confidence/持續週數、估值與籌碼狀態；動態trigger尚未完成 |
| Required-data failure contract | DONE | `r1/required_data.py`, `r1/weekly_snapshot.py` | 每週 | 不補0 | 啟用Action後強制 | 缺口逐檔保存 | challenger可累積NA；`action_policy_approved=true`後任何必要欄位缺失會報股票與欄位並中止決策 |
| Scheduling | PARTIAL | `.github/workflows/r1-daily.yml`, `r1-weekly.yml` | 每日收盤後／每週末 | 是 | 尚未交易 | Git持久化 | 每日與每週分流已存在；重大事件即時重評與完整異常偵測未完成 |

## 七個問題的答案

1. 每天監控→每週判斷→2至4週確認→換倉：**否**。前兩段已有排程，Trend與換倉決策未完成。
2. 股價漲但EPS漲更快所以不賣：**PARTIAL**。可計算`EARNINGS_LEADS_PRICE`，尚未進Action。
3. 股價漲但EPS未跟上所以TRIM：**PARTIAL**。可計算`PRICE_LEADS_EARNINGS`／`NEGATIVE_DIVERGENCE`，尚未進Action。
4. 欣興與南亞科成對比較：**否**。目前不是pairwise rotation engine。
5. 是否避免單週雜訊過度交易：**目前不會交易**；正式Trend防抖尚未完成。
6. Natural Convergence：**否**。
7. Dashboard解釋訊號、持續時間、可信度與下一觸發：**PARTIAL**。前3項已接；下一觸發尚未完成。

## 修改順序

1. 完成跨週特徵與六類Market Signal State。
2. 完成Trend 1W/2W/4W/12W、持續週數與confidence。
3. 將Price/EPS、估值變化、瓶頸及催化傳導接入Score，但仍不啟用Action。
4. 建立來源股對目標股的pairwise rotation advantage。
5. 建立分階段換倉及Natural Convergence狀態機。
6. 核准門檻、完成回測與forward shadow後，才開Action policy。
7. 最後擴充Dashboard與讀回驗證。
