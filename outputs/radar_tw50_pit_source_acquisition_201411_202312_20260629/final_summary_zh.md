# TW50/0050 PIT Source Acquisition Batch - 2026-06-29

## 結論

本批完成 RADAR/Data 的 source acquisition 盤點包，但 2014/11-2023/12 尚未達到 exact-ready。

- `exact_ready_2014_11_to_2023_12=false`
- `manual_candidate_ready=false`
- `proxy_only_sources_identified=true`
- `future_data_violation_count=0`
- 未啟動大型 PDF/CSV 下載，未提交 raw binary。

## 已確認

1. Core Phase 2 runner 的治理結構與模板已讀取，輸出可接回 Core 的 `tw50_pit_backfill.py` 後續 normalizer。
2. Radar 既有 Pool2 TW50 exact PIT package 已有 Taiwan Index 官方技術公告事件來源，主要可支援 2022 以後的 event evidence，但仍缺第一個事件以前的 dated official baseline。
3. 0050 / 元大月報或年報目前只能列為 `manual_evidence_candidate_proxy`，不能當 TW50 exact membership。
4. repository current TW50 snapshot 只能作 current proxy，禁止反推 2014-2023 exact history。
5. 00631L 在 TWSE 官方 2014/11 日成交端點已有交易資料；因此 2014/11-2015 不可用「商品未上市/不可交易」解釋缺口，若資料缺漏應歸類為 source/cache backfill gap。

## 仍然 blocked

正式 PIT 成分股表仍缺：

- 2014/11-2021/12 的官方 dated TW50 constituent archive 或 baseline snapshot。
- 2022 前後事件 reconstruction 所需的 on/before first event official baseline。
- 2014/11-2023/12 的 Yuanta 0050 dated monthly/annual holdings PDFs/CSVs，若要作 manual evidence/proxy diagnostics。

## 給 Core 的下一步

1. 若取得 FTSE Russell / Taiwan Index / TWSE 的 dated official archive，先填入 `raw_source_archive_manifest.csv`，再交 Core normalizer。
2. 若只能取得 Yuanta 0050 月報/年報，請維持 `manual_evidence_candidate_proxy`，不可標 formal exact。
3. 對 00631L，Core 可先把 2014/11 以後視為交易存在期間，資料缺漏需走價格/交易 source backfill，不得 synthetic。
