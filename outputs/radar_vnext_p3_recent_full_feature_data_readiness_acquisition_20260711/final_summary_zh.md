# P3 最近三年完整特徵資料建置摘要

- requested: 2023-07-11 ~ 2026-07-10
- expected actual end: 2026-07-09（2026-07-10 休市）
- P3 不取代 P1，也不能代表 P1 普通行情。
- raw execution 與 adjusted analysis 已分欄；Yahoo adjusted 僅 trusted_nonofficial research-grade，official_adjusted_ready=false。
- TDCC 官方免費歷史只有約一年，只作 optional recent subperiod，不用 latest 回填。
- 正式欄位名稱為「法人／大戶籌碼代理分數」；只收集 proxy components，不宣稱精確身分類別，也不先定權重。
- 法人每日買賣超是 flow；外資持股比例必須另列，不得以 flow 累積冒充。
- 全球市場欄位使用 Yahoo trusted_nonofficial research-grade，保留 exchange timezone 與台灣決策時間 PIT policy。
- 只有 mandatory 全期 ready 才交 Core 建 full-feature；否則只交 partial readiness contract。
- future_data_violation_count=0。
- 不跑回測、不交 Experiments、不改 formal/report/trade decision。
