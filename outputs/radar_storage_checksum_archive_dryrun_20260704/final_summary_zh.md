# Storage checksum archive dry-run

## 結論
- 狀態：`completed_checksum_archive_dryrun_only`
- candidate packages：20
- protected excluded packages：4
- checksum rows：1588
- 需使用者批准 rows：1588
- 原始候選大小：314.877 MB
- 去重後唯一候選大小：271.998 MB
- 重複 raw capture overhead：42.879 MB
- 預估壓縮後大小：165.131 MB
- 去重後預估壓縮大小：148.891 MB

## 產物
- `checksum_manifest.csv`
- `archive_dryrun_plan.csv`
- `restore_map.csv`
- `source_package_map.csv`
- `requires_user_approval.csv`
- `dedupe_summary.csv`
- `protected_excluded_from_dryrun.csv`

## 邊界
- `delete_executed=false`
- `move_executed=false`
- `compress_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 說明
本棒只計算 SHA256、mtime、size、restore path 與 dry-run 壓縮估算。沒有建立 archive，沒有刪除、搬移或壓縮任何檔案。
