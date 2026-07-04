# MOPS / official dated mainline evidence ledger v0

## 結論
- 狀態：`partial_ready_diagnostic_evidence_v0`
- bounded candidate scope：41 檔
- accepted diagnostic evidence rows：22
- accepted unique tickers：19
- blocked / needs review tickers：22
- `future_data_violation_count=0`
- `ready_for_taxonomy_evidence_panel=true`
- `ready_for_strategy_replay=false`

## 邊界
- accepted rows 只來自有 source_date / effective_date / as_of_date 的官方 dated disclosure aggregation。
- 所有 accepted rows 都是 `accepted_for_formal=false`、`human_review_required=true`。
- current/static/generated theme map 沒有被放入 accepted evidence。
- 本包不是 strategy replay，也不改正式模型或交易動作。

## 下一步
1. 建 MOPS 年報 / 法說會 / 公開說明書 / 重大訊息文件 locator，補更多 Pool1B / TPEx / 材料層文本。
2. 對 accepted v0 rows 交 Research 做 taxonomy policy review。
3. 若需要 formal，需 Core/Research 定義可重複抽取規則與標籤政策。
