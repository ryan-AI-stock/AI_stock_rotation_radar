# Pool2/TW50 exact PIT source package

- 狀態：partial_exact_events_parsed_baseline_missing
- formal_ready：false
- official technical notice PDFs：29 downloaded / 29 candidates
- Core parser accepted events：62 rows
- Core parser status：events_ready_pending_baseline_snapshot
- baseline snapshot：blocked_not_found
- Core parser output：data\formal_sources\pool2_tw50_exact_pit_sources_20260624_batch01\core_parser_output
- future_data_violation_count：0

## 邊界

- 本包只包含 official technical notice event source，屬於 `exact_candidate`。
- Core parser 已解析出 accepted add/delete event rows，但事件來源本身不能單獨重建完整 50 檔 PIT 成分股。
- 仍需要第一筆 accepted event 前的官方完整 baseline snapshot；本包不得標 formal ready。
- 元大 0050 持股/月報/季報只能作 proxy_candidate，不在本包混入 exact。
- raw PDF 放在 ignored folder，不提交 repo；commit 僅保留 metadata、manifest、audit 與 Core parser output。

## Core 下一步

- 使用 `core_parser_output/tw50_technical_notice_events.csv` 作為 official event rows。
- 找到或匯入 `2022-03-21` 前可驗證的 official complete TW50 baseline snapshot。
- baseline 到位後再跑 Core PIT interval builder 與 Pool2/TW50 coverage validator。
