# 0050 歷史成分股 / PIT source 自動下載嘗試 - 2026-06-29

## 結論

本批已主動執行自動定位與下載嘗試，不再只停在 manual-ledger workflow ready。

但結果仍是：

- historical accepted rows：`0`
- parsed historical sample rows：`0`
- raw historical source candidates：`5`（皆為 Wayback HTML wrapper / capture page，非 PDF，未 accepted）
- formal exact：`false`
- current holdings used as historical：`false`
- formal_model_changed：`false`

目前沒有取得 2014Q4、2016Q1、2021Q4、2023Q4 任一節點可接受的歷史 0050 持股清單。第一版 runner 曾下載到 5 個小型 Wayback HTML 回應檔，已保留在 raw_sources 並列入 raw_source_archive_manifest.csv，但它們不是 PDF/CSV 持股來源，不能解析或 accepted。

## 已完成的自動嘗試

對每個指定節點都完成 8 類嘗試：

- 元大 0050 月報固定官方 URL direct probe
- 元大國內基金季持股固定官方 URL direct probe
- 兩個 URL 的 Wayback availability 查詢
- 兩個 URL 的 Wayback timestamp direct 下載
- 兩個 URL 的 bounded CDX 查詢

合計 `37` 筆自動嘗試（含第一版 runner 下載到的 5 個非 PDF Wayback HTML raw candidates），詳見 `download_attempts.csv`。

## 主要發現

1. 元大固定官方 URL 目前可回應 PDF：
   - `1066元大台灣卓越50基金月報.pdf`：HTTP 200 / application/pdf
   - `元大國內基金季持股.pdf`：HTTP 200 / application/pdf
2. 但這兩個是 rolling/current fixed URL；直接下載到的 current PDF 不能當 2014/2016/2021/2023 歷史來源。
3. Wayback availability 有時找到 closest snapshot，但多數不是目標日期附近：
   - 2014Q4 月報 closest 是 2019 snapshot，不可當 2014Q4。
   - 2021Q4 季持股 closest 是 2022 snapshot，需另行確認內容日期，本批未能下載解析。
   - 2023Q4 月報 closest 是 2024 snapshot，不可直接當 2023Q4。
4. Wayback timestamp direct 多數回 `503` 或 read timeout。
5. bounded CDX 多數 timeout 或 0 rows，沒有產生可下載的 dated historical PDF。

## 四個節點狀態

| 期間 | 狀態 | accepted rows | 說明 |
| --- | --- | ---: | --- |
| 2014Q4 | raw_candidate_non_pdf_not_accepted | 0 | official fixed URL 為 current；取得 2 個 Wayback HTML wrapper raw candidates，但不是 PDF；availability closest 非 2014。 |
| 2016Q1 | raw_candidate_non_pdf_not_accepted | 0 | 取得 1 個 Wayback HTML wrapper raw candidate；Wayback direct 另有 503；CDX 月報 0 rows。 |
| 2021Q4 | raw_candidate_non_pdf_not_accepted | 0 | 取得 2 個 Wayback HTML wrapper raw candidates；availability closest 需內容確認但未取得 PDF。 |
| 2023Q4 | missing | 0 | Wayback direct 503/timeout；availability closest 為 2024/2025 snapshot，不可直接當 2023Q4。 |

## 下一個可程式化嘗試

不要再只打固定 PDF URL。下一步應改查 archived HTML：

1. 對 `https://www.yuantaetfs.com/product/detail/0050/download` 與舊站 `yuantafunds.com` / `yuantafunds.com.tw` 做 Wayback HTML snapshot CDX。
2. 下載目標期間附近的 HTML snapshot。
3. 從 HTML 中抽取當時 `DOC_YUEBAO_URL` / `DOC_HOLD_STOCK_URL` 或 fund download href。
4. 再下載該 href 的 snapshot PDF。
5. 解析 PDF 文字或表格，產生 ticker/name/weight rows。

本批已留下 `download_probe_fast.py`，可作為下一步改寫為 archived HTML crawler 的起點。

## 邊界

- 不把 current 0050 holdings 當歷史持股。
- 不把 manual/proxy 包裝成 exact。
- 不改 Core 模型、target、selector 或 trade decision。
- 沒有提交大型 raw PDF。

