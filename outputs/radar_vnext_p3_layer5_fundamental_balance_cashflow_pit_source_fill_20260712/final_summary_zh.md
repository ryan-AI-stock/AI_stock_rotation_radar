# P3 Layer5 F 軸 balance/cashflow PIT source package

- Status: official_cashflow_and_leverage_liquidity_proxy_source_ready_for_core_absorption
- Official source: MOPS 財務比較 E 點通 `/compare/data`。
- Exact Core candidate matrix: 57,200 rows / 698 tickers。
- Bounded ticker-period requirements: 6,141，2022Q1～2026Q1。
- OCF coverage: 99.32%。
- Investing cashflow coverage: 99.32%。
- Debt ratio coverage: 99.36%。
- Current ratio coverage: 94.77%。
- OCF + investing cashflow 僅為 diagnostic FCF proxy candidate，human_review_required=true；不是 exact capex FCF。
- 金融業或官方無值列為 missing/not-applicable，不填 0。
- available_date 使用保守法定申報期限，不使用 period-end 或 query/retrieval time。
- future_data_violation_count=0。
- 只交 Core absorption/readiness，不交 Experiments、不計績效、不改 formal/report/trade decision。
