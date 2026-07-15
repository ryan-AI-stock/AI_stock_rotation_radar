# P1/P2 MA-slope CD50 frontier source 結案

## 結論

- 下載 authority 僅限 Core 指定 84 筆 frontier exact legs。
- exact official raw ready：82/84；official no-trade：2/84；true source blocked：0/84。
- local official raw reuse：44 筆；bounded official route patch：38 筆。
- incumbent continuity 共 24,701 筆僅做 local A/B/C/D/E 分類，網路下載 0 筆。
- 42 筆 atomic policy blockers 與 9,169 provisional gaps 均未作下載清單。
- future_data_violation_count=0。

## 治理

- 此包只供 Core/Data rechain individual-stock research action legs。
- 未改正式 0050 signal -> 00631L execution MA4+7 / MA10+20 / CD7 主線。
- adjusted 缺失但 raw ready 只允許 unadjusted MA/slope research fallback，並保留 corporate-action warning；不得包裝 formal adjusted。

## Authority date resolution

- Core authority 有 0 筆 execution date 空值；均以官方 ticker-month route 的 decision date 後首個實際交易日解析。
- 原始空值、resolved date、URL、raw hash 與 policy 均獨立保存，silent_fill=false。
