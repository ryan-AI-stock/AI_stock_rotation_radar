# R1免費來源補抓與效率修正（2026-10-24）

狀態：`challenger / report-only / partial source refresh`。

## 本輪實際處理

- 重新取得54檔Yahoo EPS共識：43檔取得當期與次年度資料；正式52檔的可用共識仍為45檔。
- 累積EPS修正PIT：1W可比較由42檔增加為46檔；4W與12W尚未到自然可觀測日期。
- 重新取得Yahoo匿名目標價：54檔中50檔可讀；此資料只展示，不冒充具名法人目標價，也不計入正式信心層。
- ToAlpha目前54檔均無法解析年度EPS表；保留既有歷史資料，不用空值覆蓋。
- Investing在連續403後由既有斷路器停止，未進行無限重試。
- 新增ToAlpha來源版型斷路器：連續5檔同型解析失敗即停止本輪，Yahoo備援仍繼續執行。

## Coverage

- requested：52檔正式核心；另2檔Discovery。
- 公開資料核心：52/52。
- 法人EPS正式共識：45/52。
- EPS修正PIT：1W 46/52、4W 0/52、12W 0/52。
- 嚴格具名法人目標價：8/52。
- 匿名目標價：50/54；`scoreable=false`。
- future-data violation：0。

## 仍不能回答

- 不能把匿名Yahoo彙總拆成可識別機構，因此不能提高嚴格目標價8/52的覆蓋。
- 4W最早需2026-10-30後的有效快照；12W最早需2026-12-25後的有效快照。
- 本輪不修改R1權重、門檻或自動交易邏輯。

## 邊界

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
