# Dynamic Pool1 sector taxonomy readiness 20260704

## 結論
- 狀態：`completed_readiness_blocked_with_evidence`
- TPEx accepted sector rows：0
- AI/mainline/theme accepted taxonomy rows：0
- `future_data_violation_count=0`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`

## 判斷
- TPEx：已有官方 route probe evidence，但尚未找到可接受的 all-stock date-aware historical sector membership endpoint，因此不能回推歷史。
- AI/mainline/theme：repo 內 current/static/generated maps 只能列 inventory / blocked，不能作 2015+ PIT evidence。
- TWSE official industry：可保留為 TWSE-only diagnostic sector proxy，但不能轉寫成 AI 主線、market mainline 或 theme taxonomy。

## 下一個最小資料缺口
1. Reverse TPEx IC platform JS/API 與 `statistics/idx` schema，找 date-aware all-stock membership route。
2. 建立 MOPS dated document evidence ledger，從年報、公開說明書、法說/簡報、重大訊息中抽 AI/mainline/theme evidence。
3. official industry -> market mainline/theme 若要建立，只能由 Research 另做 policy judgment，不能由 Data 直接映射。
