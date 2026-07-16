# 4739 轉板鏈與 3474 終止上市 bounded source package

- Core post-last 24,118 列只涉及 4739（18,186）與 3474（5,932），沒有第三個 material ticker。
- 4739 是同代碼 TPEx 轉 TWSE，不是終止交易。轉板邊界 2017-09-07 TPEx、2017-09-08 TWSE 均有官方收盤價。
- 4739 共 1,299 個 exact decision dates；本機既有 compact 可補 720，其餘 579 是舊 selected-scope compact 未保留，不得誤列 termination/no-trade。
- 3474 是 100% 現金股份交換後終止上市；官方終止日 2016-12-06，最後本機官方成交日為 2016-11-29，每股現金對價 NT$30。
- 3474 精確 suspension start／歷史公告時間仍保留 blocked；未用終止生效日倒填 market_available_at。
- 本包只含 close 與 listing/termination metadata，不含其他資料 family，不計績效。
