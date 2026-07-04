# MOPS document extraction v1

## 結論
- 狀態：`partial_ready_all_requested_tickers_document_evidence_v1`
- requested tickers：22
- accepted document evidence rows：22
- accepted unique tickers：22
- blocked tickers：0
- `future_data_violation_count=0`
- `ready_for_taxonomy_evidence_panel_update=true`
- `ready_for_strategy_replay=false`

## 邊界
- 本棒只做 MOPS 年報 document locator + PDF text extraction，沒有全市場擴張。
- 所有 accepted rows 都是 diagnostic-only：`accepted_for_formal=false`、`formal_exact=false`、`human_review_required=true`。
- raw PDF 留在 `raw_sources/pdf` 並以 `.gitignore` 排除；提交的是 locator、snippets、evidence ledger 與 audit。
- 未使用 current/static/generated maps。

## 下一步
- Core 可用本包增量更新 taxonomy evidence panel，但不能交 strategy replay。
- 若 Research/Core 需要提高信心，再補 investor conference / material information / company IR presentations；本棒不把年報 evidence 包裝成 formal taxonomy。
