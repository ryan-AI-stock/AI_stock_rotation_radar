# Date-Aware Theme Membership V2 Phase 0/1 Summary

Task: evidence ledger / evidence queue Phase 0/1.

## Status

Phase 0/1 is complete as a queue and schema checkpoint, not as a formal-ready
data source.

- `formal_top3` remains `formal_blocked`.
- no new symbol is accepted as formal-ready.
- no draft evidence row is usable for formal replay.
- daily report content, ranking logic, fixed PDF, LINE entry, and publish
  workflow are unchanged.

## Outputs

- Queue: `data/formal_sources/theme_membership_evidence_queue_v2.csv`
- Draft sample ledger: `data/formal_sources/theme_membership_evidence_v2.csv`
- Readiness: `data/formal_sources/date_aware_theme_membership_v2_readiness.json`
- Builder: `rotation_radar/formal_sources/build_theme_membership_evidence_v2.py`
- Validator: `rotation_radar/formal_sources/validate_theme_membership_evidence_v2.py`
- Tests: `tests/test_theme_membership_evidence_v2.py`

## Sample 5 Evidence Rows

These five rows verify the ledger and review flow only. They intentionally use
`source_pending`, `review_status=draft`, and
`usable_for_formal_replay=false`.

| Symbol | Name | Theme | Subtheme | Status |
| --- | --- | --- | --- | --- |
| 1815 | 富喬 | PCB/載板 | 玻纖布/材料 | draft sample only |
| 2313 | 華通 | PCB/載板 | PCB | draft sample only |
| 2316 | 楠梓電 | PCB/載板 | PCB | draft sample only |
| 2367 | 燿華 | PCB/載板 | PCB | draft sample only |
| 2368 | 金像電 | PCB/載板 | AI 伺服器 PCB | draft sample only |

## Remaining 61-Symbol Gap Strategy

The queue contains all 61 missing formal-universe rows from
`date_aware_theme_membership_full_2022_2023_gap.csv`, sorted by blocker count
and split into 10-symbol batches.

| Theme | Missing Count | Priority |
| --- | ---: | ---: |
| PCB/載板 | 15 | 1 |
| CPO/矽光子 | 10 | 2 |
| AI伺服器/ODM | 8 | 3 |
| 電源/BBU | 7 | 4 |
| ASIC/IP | 7 | 5 |
| 車用電子 | 6 | 6 |
| 機器人/自動化 | 6 | 7 |
| 記憶體 | 2 | 8 |

Recommended next batch:

1. Finish batch 01 (`PCB/載板`, 10 symbols) with dated company/MOPS/annual
   report/investor material evidence.
2. Mark each row `draft` until source date, effective start, confidence, and
   license status are reviewed.
3. Convert only reviewed and accepted rows into normalized date-aware intervals.
4. Keep `formal_top3` blocked until accepted evidence coverage is sufficient
   and future-data checks pass.

## Blocking Issues

- no accepted v2 evidence exists yet.
- all 61 missing rows still require dated source review.
- current static theme map remains research-only and cannot be used to release
  formal top3 replay.

