# P1/P2 primary80 path-independent official close local audit

- 固定 universe：1,163 tickers / 592 snapshots。
- unique ticker-date requirements：1,972,684。
- local ready：782,799；official no-trade/termination：45,168。
- true missing：1,144,181；policy/conflict blocked：536。
- one-shot market-date routes：5,821；估計 2766.6 MB / 51.5~176.5 分鐘。
- 本輪 network_requests=0；等待 Strategy Center 裁決是否一次性補 close-only market-date routes。
- abs return >15% 僅為 warning，不視為 corporate-action event。
