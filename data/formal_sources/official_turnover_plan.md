# Official Turnover Plan

## Goal

Upgrade from `turnover_mode=approximate_close_times_volume` to:

- `turnover_mode=official_exchange_turnover`
- or `turnover_mode=official_partial_with_gap_report`

## Required Schema

```csv
symbol,date,official_turnover_value,exchange,source,source_url,ingested_at
```

## Candidate Sources

1. TWSE listed stocks
   - TWSE individual daily trading data is available historically and supports CSV download.
   - TWSE OpenAPI also exposes exchange report endpoints.
   - Source: https://wwwc.twse.com.tw/zh/trading/historical/stock-day.html

2. TPEx mainboard stocks
   - TPEx daily stock market value information is available historically and supports CSV download.
   - Source: https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote.php?l=en-us

3. TWSE Data E-Shop
   - Paid EOD products may be required for robust bulk/commercial workflows.
   - Use only after checking licensing and commercial redistribution terms.
   - Sources: https://eshop.twse.com.tw/ and https://www.twse.com.tw/zh/products/dataeshop.html

## Current Gap

The replay cache has OHLCV files only. It does not include official exchange turnover amount. The current replay computes:

```text
turnover_value = close * volume
```

That is useful for research ranking, but it is not the official turnover figure.

## Feasibility

Status: `feasible_needs_fetcher_and_terms_check`.

The public TWSE/TPEx pages indicate historical availability. Implementation still needs:

1. Exchange detection for each symbol.
2. TWSE daily fetcher.
3. TPEx daily fetcher.
4. Retry/cache layer.
5. Gap report for missing symbol-date pairs.
6. Licensing review before public redistribution or paid product use.

## Validation Rules

1. Every formal universe symbol-date must have official turnover.
2. `official_turnover_value > 0`.
3. Source exchange must match symbol market.
4. Missing pairs must be listed in `official_turnover_gap_report.csv`.

## Can This Make Formal Ready Now?

Not yet. The source appears feasible, but the repo has not ingested official turnover data.
