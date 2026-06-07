# Formal Data Source Feasibility

## Conclusion

Current status: `ready_for_formal_strategy_conclusion=false`.

The existing `backtest_grade_2021_2023` and `formal_grade_2021_2023` outputs can support internal research only. They cannot support formal radar stock-rotation strategy conclusions yet.

Formal-grade replay is blocked by three source-data gaps:

1. Point-in-time fundamentals are not available in the repo.
2. Theme membership is still a current static map, not date-aware history.
3. Official TWSE/TPEx turnover amount has not been ingested into replay snapshots.

## Current Evidence

- Source replay snapshots: `data/history_replay/backtest_grade_2021_2023`
- Formal audit output: `data/history_replay/formal_grade_2021_2023`
- Source snapshot count: 507 trading days
- Formal universe with OHLCV available: 69 symbols
- Missing OHLCV excluded from formal universe: 91 symbols
- Missing or non-point-in-time fundamentals: 62 missing baseline symbols, all 166 theme-map rows lack true point-in-time fundamentals
- Blocking issue count: 3

## Feasibility Summary

| Source | Feasibility | Current repo status | Can make formal ready now? |
| --- | --- | --- | --- |
| Point-in-time fundamentals | Partially feasible, but not currently present | Only baseline/carry-forward stock metrics exist | No |
| Date-aware theme membership | Feasible only with curated source evidence or a new start date | Current static `theme_map.csv` only | No |
| Official turnover | Feasible for TWSE/TPEx, but needs implementation and terms check | Replay uses `close * volume` approximation | No |

## Official / Public Source Notes

- TWSE individual daily trading page states the data is provided since 2010-01-04 and supports CSV download.
  Source: https://wwwc.twse.com.tw/zh/trading/historical/stock-day.html
- TPEx daily stock quote page states its information is available since 2007-01 and supports CSV download.
  Source: https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote.php?l=en-us
- MOPS contains monthly revenue, financial reports, major announcements, and company disclosures, but this repo does not yet have a normalized point-in-time fundamentals table with announcement/acquisition dates.
  Source: https://mops.twse.com.tw/mops/web/ezsearch
- TWSE Data E-Shop lists paid market data products including after-market information and historical trading data. Before public redistribution or paid product use, data licensing and commercial use terms must be checked.
  Sources: https://eshop.twse.com.tw/ and https://www.twse.com.tw/zh/products/dataeshop.html

## Required Next Step To Reach Formal-Grade

Build a new pipeline stage:

1. `data/formal_sources/point_in_time_fundamentals.csv`
2. `data/formal_sources/date_aware_theme_membership.csv`
3. `data/formal_sources/official_turnover_20211201_20231231.csv`
4. Validation script that joins the three tables into historical replay snapshots and only sets `ready_for_formal_strategy_conclusion=true` when all acceptance gates pass.

## Non-Negotiable Boundary

Do not rename `formal_grade_blocked` or `backtest_grade_limited_replay` as formal-grade snapshots. Until the three source-data gaps are closed, BACKTEST_LAB must label radar replay results as `research_only_limited_replay`.
