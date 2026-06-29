# 0050 歷史成分股來源 Phase 3：Wayback archived HTML crawler

## 結論

本批完成 Phase 3 archived HTML crawler，已不再重複只打元大 fixed PDF URL。四個指定節點都有 Wayback CDX / availability / selected HTML snapshot download attempt evidence。

本批成功取得元大 0050 archived HTML route evidence，並從 archived ratio/PCF HTML SSR table 抽出 holdings sample rows，但這些 sample 的 snapshot date 不是指定 target period 的 holdings date，因此不能 accepted 成 2014Q4、2016Q1、2021Q4、2023Q4 的 PIT exact / formal rows。

## 產出

- Output: `outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629`
- Previous output read: `outputs/radar_tw50_0050_historical_source_download_201411_202312_20260629`
- HTML snapshot attempts: 68
- PDF href candidates: 77
- PDF/download attempts: 98
- Raw source candidates: 80 local HTML files
- Parsed holdings sample rows: 20
- Accepted historical rows: 0

Raw HTML files are retained locally under `raw_sources/` for audit, but excluded from git because the folder is about 84.6 MB. The committed audit surface is the manifest, CSV ledgers, runner scripts, and this summary.

## Period Status

| period | target date | HTML download attempts | PDF href candidates | parsed sample rows | accepted rows | status |
|---|---:|---:|---:|---:|---:|---|
| 2014Q4 | 2014-12-31 | 4 | 24 | 5 | 0 | parsed sample only |
| 2016Q1 | 2016-03-31 | 3 | 24 | 5 | 0 | parsed sample only |
| 2021Q4 | 2021-12-31 | 2 | 13 | 5 | 0 | parsed sample only |
| 2023Q4 | 2023-12-31 | 3 | 16 | 5 | 0 | parsed sample only |

## Parsed Sample Evidence

The parsed rows prove the archived HTML route can expose holdings table rows, for example:

- 2330 台積電 57.72
- 2454 聯發科 5.79
- 2308 台達電 3.55
- 2317 鴻海 3.06
- 3711 日月光投控 2.12

However, the snapshot dates are:

- 2014Q4 route: 2022-05-26 snapshot
- 2016Q1 route: 2022-05-26 snapshot
- 2021Q4 route: 2022-05-26 snapshot
- 2023Q4 route: 2024-02-22 snapshot

Because the snapshot dates do not match the requested holdings dates, these rows are kept as `source_backed_manual_proxy` samples only. They are not accepted PIT rows and not formal exact evidence.

## Source Quality Decision

- `formal_exact=false`
- `current_snapshot_used_as_historical=false`
- `wayback_wrapper_html_accepted=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`

## Main Blocker

Wayback CDX for older Yuanta 0050 product/download pages often returns empty rows or times out. Wayback availability returns closest snapshots, but for the older targets it points to later snapshots such as 2022-05-26. Those later snapshots are useful for parser development and route discovery, but not accepted as target-period PIT evidence.

## Next Programmatic Attempt

Do not stop at manual download. The next crawler should target dated API/data routes instead of only product pages:

1. Query archived Nuxt/API JSON endpoints referenced by Yuanta HTML, especially `etfapi.yuantaetfs.com` and page `_nuxt` payload routes.
2. Query regulator or association sources for dated fund portfolio/monthly disclosures, including SITCA / fund monthly portfolio files if accessible.
3. Query Taiwan Index / TWSE historical constituents or technical notice archives as cross-source support, while keeping proxy/exact separation.
4. Accept rows only when `holdings_date` or source date can be matched to the target period; otherwise keep them as parser samples or source-backed manual proxy.
