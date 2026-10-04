# R1 build status — 2026-10-04

## 結論

R1仍是challenger與shadow tracking，不是正式交易模型。資料管線、週狀態、分階段換倉與自然收斂已建立；尚未完成的是三個構面內部欄位轉成0至100分的契約，以及必須靠未來週快照自然累積的EPS 1W／4W／12W序列。

## 已完成

- 14檔官方日價、三大法人及融資融券每日資料。
- 2026E／2027E／2028E共42筆法人EPS觀測；2026E與2027E為14／14可用，2028E為13／14可用。
- 上詮2028E有數值但缺第二個獨立來源，狀態固定為`EVIDENCE_GAP`，不進決策。
- 每週共識下載器具checkpoint、resume、逐檔錯誤及完整性檢查；已接入R1 weekly workflow。
- Forward valuation score已按核准權重物化，2026-10-02為14／14可計算。
- EPS、估值、籌碼、瓶頸、催化狀態，以及WAIT／EARLY_SIGNAL／CONFIRMING／CONFIRMED／DETERIORATING。
- Shadow pairwise rotation、25%分段換倉、每週最多10%、最多5檔與Natural Convergence。

## 不能用假資料補的時間缺口

- EPS revision 1W最早需2026-10-09後的有效週快照。
- EPS revision 4W最早需2026-10-30後的有效週快照。
- EPS revision 12W最早需2026-12-25後的有效週快照。
- 未到日期前維持NA；正式Action開啟後若仍缺，會報`R1_REQUIRED_DATA_MISSING`並中止決策。

## 唯一待核准的計分契約

1. Bottleneck：tightness與financial proof如何由已驗證證據轉成0至100。
2. Catalyst：各事件類型的impact、confidence及expiry weeks。
3. Price/Chip：earnings-vs-price、overheat safety、institutional與leverage structure的百分位方向及極端值上限。

上述三項沒有核准前，R1不產生總分、ADD／TRIM／EXIT或真實換倉指令。

## 邊界

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
