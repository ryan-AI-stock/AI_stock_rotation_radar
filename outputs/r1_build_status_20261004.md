# R1 build status — 2026-10-04

## 結論

R1仍是challenger與shadow tracking，不是正式交易模型。資料管線、週狀態、分階段換倉、自然收斂及五構面計分契約已建立；尚未完成的是必須靠未來週快照自然累積的EPS 1W／4W／12W序列。

## 已完成

- 14檔官方日價、三大法人及融資融券每日資料。
- 2026E／2027E／2028E共42筆法人EPS觀測；2026E與2027E為14／14可用，2028E為13／14可用。
- 上詮2028E有數值但缺第二個獨立來源，狀態固定為`EVIDENCE_GAP`，不進決策。
- 每週共識下載器具checkpoint、resume、逐檔錯誤及完整性檢查；已接入R1 weekly workflow。
- Forward valuation score已按核准權重物化，2026-10-02為14／14可計算。
- Bottleneck與Catalyst score已按核准的事件強度、證據階段及13／26週線性衰減物化，2026-10-02均為14／14可計算。
- Price/Chip已固定為earnings-vs-price、過熱安全、法人20TD流量與融資20TD結構的池內百分位；缺任一子項時整項維持NA。
- EPS、估值、籌碼、瓶頸、催化狀態，以及WAIT／EARLY_SIGNAL／CONFIRMING／CONFIRMED／DETERIORATING。
- Shadow pairwise rotation、25%分段換倉、每週最多10%、最多5檔與Natural Convergence。

## 不能用假資料補的時間缺口

- EPS revision 1W最早需2026-10-09後的有效週快照。
- EPS revision 4W最早需2026-10-30後的有效週快照。
- EPS revision 12W最早需2026-12-25後的有效週快照。
- 未到日期前維持NA；正式Action開啟後若仍缺，會報`R1_REQUIRED_DATA_MISSING`並中止決策。

## 目前資料結果

- 2026-10-02獨立重建：Bottleneck 14／14、Catalyst 14／14。
- Price/Chip 0／14，主因EPS 4W revision尚未到自然可觀測日；不以0分或推估補值。
- 因EPS revision與Price/Chip仍不完整，總分維持0／14可用，R1不產生ADD／TRIM／EXIT或真實換倉指令。

## GitHub排程

- Daily workflow於台灣時間17:00至23:00每小時喚醒，並讀取中央`AI_stock_schedule_rules`的daily profile。
- Weekly workflow於台灣時間19:00至23:00每小時喚醒，並讀取同一中央規則的weekly profile。
- 中央規則以Asia/Taipei、15:00後、正常交易日／當週最後交易日為gate；cron只負責喚醒，不自行認定交易日。

## 邊界

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
