# P1 免費歷史來源重新開案

- TDCC 截圖頁已確認是 TAIBIR 01/02 利率資料，不是股權分散。2009/2015/2022 六檔已下載驗證。
- TDCC 集保戶股權分散 OpenAPI 1-5 無日期參數，只回單一最新資料日；P1 仍 blocked。
- TAIFEX 2015/2018/2022 官方 range endpoint 都回 DateTime error；免費 P1 仍 blocked，未購買。
- TPEx 法人 exhausted 結論已修正：正確 `insti/dailyTrade?sect=EW` 路線鎖存 1943/1943 交易日，rows=1091250。
- 民間來源僅作 trusted/web inventory；沒有把可見頁面當可重現批次來源。
- future_data_violation_count=0。
