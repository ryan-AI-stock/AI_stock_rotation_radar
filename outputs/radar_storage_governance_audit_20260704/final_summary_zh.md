# RADAR/Data storage governance audit

## 結論
- 狀態：`completed_audit_plan_only`
- 掃描 packages：35
- 掃描檔案：10721
- `outputs/` 估計大小：5800.28 MB
- 最大 package：`radar_dynamic_pool1_market_cap_twse_route_tpex_full_sweep_20260703`，3567.255 MB
- 不可動 / 回測必要 packages：11，約 5376.002 MB
- large shard / cache candidate rows：360

## 不可動資料
- 0050 PIT / PCF full-range candidate。
- 2015-latest TWSE/TPEx liquidity / price data。
- Pool1B price repair including `6488.TWO`。
- MOPS monthly revenue / quarterly fundamentals full-universe candidate。
- listing/status metadata、transition ledgers。
- source manifests / readiness ledgers / future-data audits。

## 可瘦身方向
- raw PDF/HTML/JSON/browser artifacts：先補 checksum manifest，再壓縮封存。
- failed route attempts：保留 manifest/summary/attempt logs， bulky raw artifacts 列 archive candidate。
- normalized/cache-compatible 大表：另開 migration task 集中到共用 normalized data directory，不能在本 audit 直接搬移。

## 邊界
- `delete_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
