# P3 Layer0-4 rank1 sequential lifecycle adjusted HLC source package

- 實際範圍：101 tickers / 715 decision rows / 715 decision dates。
- Trusted adjusted HLC ready: 100/101 tickers；2888 explicit blocked。
- Adjusted HLC rows: 96,677；official raw overlap: 78,970。
- 252TD segment warmup: 135/136 ready；短掛牌歷史與 source blocker 分開標示。
- Corporate-action inventory: 476 official rows；factor changes保留human review，不包裝formal。
- 此包只支援 sequential low-turnup/high-turndown rank1 timing diagnostic；不代表完整all80 Layer5。
- 不計state、績效或NAV；future_data_violation_count=0。
