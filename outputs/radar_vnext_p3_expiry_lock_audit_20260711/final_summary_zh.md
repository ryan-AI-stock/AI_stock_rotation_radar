# P3 滾動期限資料到期鎖存稽核

- TAIFEX：官方區間 CSV 鎖存 728/728 個交易日，涵蓋交易淨口數／金額與 OI 淨口數／金額；missing=0。
- TDCC：官方仍保留 51 週（2025-07-11～2026-07-03），鎖存 61856 rows；11 ticker-week 為官方成功查詢但零列，未回填。
- 法人／融資融券／借券／外資持股：實體 compact、來源 manifest、日期與 checksum 已稽核；true failed 逐列保留。
- Yahoo adjusted/global：只驗證本機 coverage/checksum，未重探已知 adjusted structural blocker。
- corporate action：Yahoo trusted candidates 已鎖存；官方歷史完整性仍 partial，不包裝 formal-ready。
- future_data_violation_count=0。
