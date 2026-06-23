# Pool2 TW50/0050 Public Source Search

Status: `partial_exact_public_sources_found_parse_pending`
Ready: `False`
Public source exhausted: `False`
Exact candidate count: `74`
Proxy candidate count: `1`
Accepted rows: `0`
Future data violation count: `0`
Exact candidates by year: `{'2011': 2, '2012': 1, '2013': 5, '2014': 5, '2015': 4, '2016': 4, '2017': 4, '2018': 5, '2019': 4, '2020': 5, '2021': 6, '2022': 4, '2023': 4, '2024': 6, '2025': 6, '2026': 9}`
Download status counts: `{'download_failed:HTTPError': 67, 'http_non_pdf_or_unverified': 1, 'http_pdf_verified': 35}`

## Boundary

- `exact_candidate` means the source may support official Taiwan 50/TWSE-FTSE PIT events after parsing and review.
- `proxy_candidate` means Yuanta 0050 holdings proxy only; it must not be treated as exact TW50 official constituents.
- This package is a source-search/readiness audit. It does not make Pool2 ready by itself.

## Sample Audit Rows

| source_id | publish_date | source_title | exact_or_proxy | parse_status |
| --- | --- | --- | --- | --- |
| tip_1276_tw | 2026/06/18 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：禾伸堂延期納入成分股 | exact_candidate | notice_pdf_download_pending |
| tip_1275_tw | 2026/06/18 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：大量延期納入成分股 | exact_candidate | notice_pdf_download_pending |
| tip_1270_tw | 2026/06/15 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：延期刪除來億-KY及富邦媒 | exact_candidate | notice_pdf_download_pending |
| tip_1262_tw | 2026/06/05 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列及臺灣高股息指數成分股定期審核結果 | exact_candidate | notice_pdf_download_pending |
| tip_1217_tw | 2026/04/09 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：旺宏納入成分股 | exact_candidate | notice_pdf_download_pending |
| tip_1215_tw | 2026/04/02 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：欣興納入刪除成分股 | exact_candidate | notice_pdf_download_pending |
| tip_1205_tw | 2026/03/19 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：旺宏納入成分股延期 | exact_candidate | notice_pdf_download_pending |
| tip_1206_tw | 2026/03/19 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：欣興納入刪除成分股延期 | exact_candidate | notice_pdf_download_pending |
| tip_1199_tw | 2026/03/06 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列及臺灣高股息指數成分股定期審核結果 | exact_candidate | notice_pdf_download_pending |
| tip_1173_tw | 2025/12/23 | 臺灣證券交易所與富時國際有限公司合編之臺灣指數系列成分股變動：南亞科納入刪除成分股 | exact_candidate | notice_pdf_download_pending |

## Next Actions

- Download the exact_candidate technical notices and parse constituent add/delete/effective-date events.
- Build point-in-time TW50 constituent intervals from accepted official events only.
- Run Core tw50 constituent coverage validator before marking ready.
