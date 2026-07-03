# Dynamic Pool1 TPEx static reverse / archive probe summary

## 結論

狀態：`completed_partial_with_accepted_historical_rows`。

本棒沒有重跑上一棒已知的 current-only / 404 route，而是從 TPEx 官方 `tables.js`、`main.js`、`global.js` 與 `menu.json` 反推出新站 table API contract：

- `main.js` 定義 `API_PATTERN=/www/{LANG}/{ACTION}`。
- `tables.js` 的 `bxRport.init/#u/#k` 會把頁面 `tables.init({ action })` 組成 `apiAction`，用 POST 送出表單欄位並加上 `response=json`；server paging 另加 `paging-*`。
- 官方 `menu.json` 找到有效頁面：`/mainboard/trading/info/altered.html`、`/mainboard/listed/delisted.html`、`/mainboard/listed/latest.html`、`/announce/market/halt.html`、`/announce/market/download.html` 等。

## Accepted historical rows

- `accepted_listing_metadata_rows.csv`：150 rows。
  - `company/latest`：sample years 2015、2018、2021、2025 可回 listing rows。
  - `company/deListed`：sample years 2015、2018、2021、2025 可回 delisting rows。
- `accepted_status_snapshot_rows.csv`：107 rows。
  - `afterTrading/chtm`：sample dates 2015-01-05、2018-01-05、2021-01-05 可回變更交易 / 分盤 / 管理股票 / 停止交易 status snapshot；2025-01-05 無 rows。
- `accepted_suspension_event_rows.csv`：0 rows。
  - `bulletin/sprc` 目前 confirmed current-only，未找到 historical date parameter。

## 不可包裝的邊界

- 這不是 full 2015-2025 master，只是官方 route contract + bounded sample accepted rows。
- `afterTrading/chtm` 是每日 status snapshot，不是 suspension/resumption transition event ledger。
- `bulletin/annDownload`、`bulletin/disposal`、`bulletin/attention` 只保留 route evidence；不混入 listing master。
- 沒有用 current snapshot 回推，`future_data_violation_count=0`。

## 下一步

1. Radar/Data 可用相同 contract 跑 full 2015-2025 sweep：
   - `company/latest`
   - `company/deListed`
   - `afterTrading/chtm`
2. 對 `company/applicantStatDl?type=list|app&date=YYYY` 做 annual download parse，交叉檢查 new-listed rows。
3. 對 `bulletin/annDownload` 的 monthly ZIP 做 keyword/content extraction，找 `終止上櫃`、`暫停`、`恢復` 等 announcement event dates。
4. Core 可先重跑 readiness，確認 TPEx listing/delisting/status blocker 是否從 blocked 降到 stronger partial。

`formal_model_changed=false`、`trade_decision_changed=false`、`active_in_trade_decision=false`。
