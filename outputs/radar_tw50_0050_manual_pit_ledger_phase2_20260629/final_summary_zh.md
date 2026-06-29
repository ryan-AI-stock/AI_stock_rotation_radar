# TW50/0050 Manual PIT Ledger Phase 2 - 2026-06-29

## 結論

本批完成 source-backed manual ledger 工作流與第一批樣本 package，但 2014/11-2023/12 歷史成分資料仍未 formal-ready，也沒有 accepted historical rows。

- 元大 0050 官方頁面可以穩定支援「source-backed manual ledger」的工作流設計。
- 官方 current ratio page 可解析 50 檔 `StockWeights`，本批收錄前 10 檔作 parser/schema sample。
- 官方 download page 會提供 `DOC_YUEBAO_URL` 與 `DOC_HOLD_STOCK_URL`，但它們是 rolling/current fixed URL；若要做歷史 2014/2016/2021/2023，仍需取得 dated PDF 或 archive snapshot。
- Internet Archive CDX 對固定 PDF URL 的小範圍查詢在本批回傳空/null 或 timeout，不足以作 accepted source。

## 第一批 target

本批建立 4 個歷史優先樣本 target：

1. 2014Q4：`yuanta_0050_monthly_201411_or_201412.pdf` 或 `yuanta_domestic_holdings_2014Q4.pdf`
2. 2016Q1：`yuanta_0050_monthly_201603.pdf` 或 `yuanta_domestic_holdings_2016Q1.pdf`
3. 2021Q4：`yuanta_0050_monthly_202112.pdf` 或 `yuanta_domestic_holdings_2021Q4.pdf`
4. 2023Q4：`yuanta_0050_monthly_202312.pdf` 或 `yuanta_domestic_holdings_2023Q4.pdf`

以上 4 期目前都是 `source_pending`。本批沒有用 current PDF 或 current holdings 填歷史日期。

## 給 Core 的使用方式

Core 可以先採用 `manual_pit_ledger_schema.csv` 作為 normalizer contract：

- `source_type` 僅能是 `manual_evidence_candidate` 或 `source_backed_manual_proxy`
- `formal_exact=false`
- exact TW50 validator 不得吃這批 rows
- 若來源只有 top-10 holdings，不能當 50 檔完整成分表
- 若來源是完整 quarterly holdings，可作 quarter-end manual/proxy snapshot，再由 Core 決定是否容許 interval fill

## 下一步

1. 先人工取得 2014Q4、2016Q1、2021Q4、2023Q4 的元大 0050 月報或國內基金季持股 PDF。
2. 放入 raw source archive，不提交大型 PDF；在 `raw_source_archive_manifest.csv` 記錄檔名、來源 URL、文件日期與 checksum。
3. 解析或人工輸入 ticker/name/weight，更新 `manual_pit_ledger_sample.csv`。
4. 二次人工 review 後，才可交 Core normalize 成 PIT/manual/proxy table。

本批未改 Radar public report、Drive/LINE/workflow，也未改 BACKTEST_LAB Core selector/target/trade decision。
