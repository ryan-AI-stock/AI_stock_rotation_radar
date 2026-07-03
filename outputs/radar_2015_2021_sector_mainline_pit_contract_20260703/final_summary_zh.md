# 2015-2021 sector/mainline PIT contract

- Task: `TASK-BACKTEST-DATA-2015-2021-SECTOR-MAINLINE-PIT-CONTRACT-001`
- Readiness: `blocked`
- formal_ready: `false`
- diagnostic_only: `false` for sector/mainline backtest, because breadth/liquid universe panels are absent.
- future_data_violation_count: `0` for accepted package rows.
- current static maps excluded: `sector_map.csv` and `theme_map.csv` are not accepted as PIT membership.

## Contract decision

2015-2021 sector/mainline pool does **not** currently have a reliable backtest data foundation in this repo. Existing dated membership evidence is partial and concentrated in 2021 memory-theme rows. Existing official turnover and PIT revenue sources start at 2021-12 and cannot cover 2015-2021.

## Blocking data

- Full date-aware sector/mainline membership panel with `source_date`, `effective_date`, and `as_of_date`.
- Daily sector/mainline breadth panel after membership is available.
- Full-market liquid tradable universe panel with listing, delisting, suspension, volume, and turnover filters.

## Next programmable sources

- TWSE/TPEx daily full-market trading files for OHLCV/turnover/liquidity.
- TWSE/TPEx listing/delisting/suspension metadata or announcements.
- MOPS annual reports/prospectuses/company formal filings for dated sector/mainline membership evidence.
- Any official historical industry classification archive, if available; otherwise classify as manual evidence candidate, not exact.
