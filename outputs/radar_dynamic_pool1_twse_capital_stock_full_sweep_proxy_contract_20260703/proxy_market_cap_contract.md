# TWSE Quarterly Capital Stock + Daily Close Proxy Contract

This package unlocks a source-backed proxy path, not formal exact daily market cap.

1. Capital stock source: MOPS `ajax_t163sb05` quarterly balance-sheet route.
2. Availability policy: use conservative statutory deadlines per quarter, not exact company filing timestamps.
3. As-of rule: carry the latest available quarterly capital stock forward until the next quarter becomes available.
4. Daily price join: join to TWSE daily close by ticker and trade date.
5. Proxy formula: daily close times shares proxy derived from capital stock/par-value policy.
6. Boundaries: `formal_exact=false`, not direct official market cap, not daily exact issued shares, not free-float market cap.

Core must decide whether the capital_stock-to-shares normalization is acceptable before any full daily proxy table is used in challenger replay.
