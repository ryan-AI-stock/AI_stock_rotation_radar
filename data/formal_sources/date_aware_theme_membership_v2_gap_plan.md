# Date-Aware Theme Membership V2 Gap Plan

Task: `TASK-SECTOR-RADAR-THEME-MEMBERSHIP-V2-20260619`

## Conclusion

`date-aware theme membership` remains the formal replay blocker.

Current repo evidence is not enough to set any full-universe radar replay to
`formal_ready`:

- full-universe membership coverage is `8/69` symbols, coverage ratio
  `0.11594203`.
- `formal_top3_capital_flow_2022_2023` is still `formal_blocked`.
- official turnover coverage is already high enough for ingestion
  (`0.99868508`) and PIT monthly revenue coverage is `1.0`, so the gating gap is
  theme membership evidence, not turnover or revenue.

The current static `theme_map.csv`, limited replay snapshots, and memory-only
partial source must remain research-only unless the membership row has dated
source evidence.

## V2 Goal

Build a maintained evidence table that can answer this question for each
symbol/theme/date:

> On this historical snapshot date, could the radar have known that this symbol
> belonged to this theme, based on dated evidence available on or before that
> date?

V2 is a data-source and maintenance design. It is not a strategy success claim
and does not change the daily radar report, fixed PDF, LINE entry point, or
historical replay labels.

## Proposed Files

1. `data/formal_sources/theme_membership_evidence_v2.csv`
   - append-only evidence ledger.
   - one row per source-backed membership claim.

2. `data/formal_sources/date_aware_theme_membership_v2.csv`
   - normalized membership intervals derived from the evidence ledger.
   - usable by formal replay only after validation.

3. `data/formal_sources/date_aware_theme_membership_v2_gap.csv`
   - missing or low-confidence rows by formal universe symbol/theme.

4. `data/formal_sources/date_aware_theme_membership_v2_readiness.json`
   - readiness gate with coverage, confidence distribution, future-data checks,
     and formal-ready/blocking status.

5. `data/formal_sources/theme_membership_evidence_sources_v2/`
   - optional local evidence snapshots or source exports when redistribution is
     allowed.
   - if redistribution is not allowed, store only source metadata and links.

## Evidence Ledger Schema

Required columns for `theme_membership_evidence_v2.csv`:

| Column | Meaning |
| --- | --- |
| `evidence_id` | Stable id, e.g. `TMEM-20230608-2382-AISERVER-001`. |
| `symbol` | Numeric stock id. |
| `ticker` | TW ticker, e.g. `2382.TW`. |
| `exchange` | `TWSE` or `TPEx`. |
| `name` | Company name at collection time. |
| `theme` | Radar theme taxonomy, e.g. `AI伺服器/ODM`. |
| `subtheme` | More precise product or role label. |
| `membership_role` | `core`, `supplier`, `component`, `downstream`, `proxy`, or `watchlist`. |
| `effective_start` | Earliest date this membership can be used. |
| `effective_end` | Blank if still valid; otherwise last valid date. |
| `source_date` | Date the evidence became public or was archived. Must be `<= effective_start` unless source proves earlier operations. |
| `source_type` | Controlled enum listed below. |
| `source_title` | Short human-readable source title. |
| `source_url` | URL or internal archive reference. |
| `source_publisher` | MOPS, company, TWSE, TPEx, investor conference, news vendor, internal radar archive, etc. |
| `source_license_status` | `public_link_only`, `redistributable`, `licensed_required`, `internal_only`, or `unknown`. |
| `evidence_quote_or_summary` | Short paraphrase or summary; avoid long copyrighted text. |
| `confidence` | `high`, `medium`, or `low`. |
| `confidence_reason` | Why this confidence level was assigned. |
| `collector` | Person/thread that collected the evidence. |
| `review_status` | `draft`, `reviewed`, `accepted`, `rejected`, `expired`, or `needs_license_check`. |
| `reviewer` | Reviewer id/name. |
| `reviewed_at` | Review timestamp. |
| `usable_for_formal_replay` | `true` only after review and validation. |
| `notes` | Boundary notes, ambiguity, or taxonomy caveats. |

## Source Type Rules

| Source type | Formal use | Confidence default | Maintenance cost | Notes |
| --- | --- | --- | --- | --- |
| `mops_company_filing` | Preferred | high | medium | Best for dated public-company disclosure. |
| `annual_report_segment` | Preferred | high | high | Useful for older years but collection is manual. |
| `investor_conference_material` | Preferred | high/medium | high | Good dated evidence; licensing must be checked before redistribution. |
| `company_product_page_archived` | Usable if archived date is clear | medium | high | Needs archive timestamp; current product page alone is not enough. |
| `monthly_revenue_note` | Usable when product line is explicit | medium | medium | Good for PIT if available date is known. |
| `dated_industry_report` | Usable with license limits | medium | high | Often not redistributable; store metadata only if needed. |
| `dated_news_article` | Supporting evidence | medium/low | high | Must avoid long copied text; article date alone may not prove business exposure start. |
| `internal_archived_radar_theme_definition` | Usable only from archive date onward | medium | low after archive exists | Best path for future years; does not backfill older years. |
| `current_static_theme_map` | Not formal | none | low | May populate research-only gap context, never formal-ready. |

## Validation Rules

`date_aware_theme_membership_v2.csv` can be generated from accepted evidence
only when:

1. `usable_for_formal_replay=true`.
2. `review_status=accepted`.
3. `source_date <= snapshot_date`.
4. `effective_start <= snapshot_date`.
5. `effective_end` is blank or `snapshot_date <= effective_end`.
6. `source_type != current_static_theme_map`.
7. `source_url` or `source_archive_ref` is present.
8. `confidence in {high, medium}` for formal top3; low-confidence rows remain
   diagnostic only.
9. no row uses a source published after the replay date.

Readiness should stay false unless:

- coverage is near-complete for the requested formal universe and themes.
- all top3 candidate symbols have accepted rows on each replay date.
- `future_data_violation_count=0`.
- missing rows are either excluded by explicit universe rules or listed in the
  gap report.

## Suggested Rollout

### Phase 1: Lock Taxonomy And Evidence Queue

Scope: existing 69-symbol formal universe for 2022-2023.

Work:

- freeze theme taxonomy aliases used by replay (`theme`, `subtheme`, role).
- create an evidence queue from
  `date_aware_theme_membership_full_2022_2023_gap.csv`.
- prioritize missing themes by blocker count:
  `PCB/載板` 15, `CPO/矽光子` 10, `AI伺服器/ODM` 8,
  `電源/BBU` 7, `ASIC/IP` 7, `車用電子` 6,
  `機器人/自動化` 6, `記憶體` 2.

Output: evidence queue and empty v2 readiness still blocked.

### Phase 2: Manual Evidence Collection Batch

Scope: 10 to 15 missing symbols per batch.

Work:

- collect one or more dated sources per symbol/theme.
- prefer MOPS/company filings and investor materials before news.
- store links, dates, source metadata, confidence, and license status.
- keep rows in `draft` until reviewed.

Output: `theme_membership_evidence_v2.csv` with draft/reviewed rows.

### Phase 3: Review And Generate Normalized Intervals

Work:

- reviewer marks accepted/rejected.
- builder converts accepted evidence into date-aware intervals.
- validator emits coverage, confidence distribution, and future-data checks.

Output:

- `date_aware_theme_membership_v2.csv`
- `date_aware_theme_membership_v2_gap.csv`
- `date_aware_theme_membership_v2_readiness.json`

### Phase 4: Formal Top3 Rebuild Gate

Only after v2 readiness is true or explicitly partial by a defined narrow
universe:

- rebuild `formal_top3_capital_flow_2022_2023`.
- keep `formal_blocked` if full coverage remains insufficient.
- if partial, name it partial and restrict the universe; do not call it
  full-universe formal-grade.

## Maintainable Start-Year Options

### 2022-2023 Full Backfill

Feasibility: possible but high manual cost.

Needs:

- 61 missing symbol/theme evidence rows at minimum, likely more if symbols have
  multiple themes or membership changes.
- source review and license tagging.
- periodic taxonomy reconciliation.

Formal-grade status: not feasible until collection/review is done.

### 2024-Forward Curated Backfill

Feasibility: medium.

Needs:

- collect from recent filings, company materials, and archived radar notes.
- still manual for pre-archive evidence.

Formal-grade status: possible sooner than 2022-2023 if evidence density is
better, but still not automatic.

### 2026-Forward Native Archive

Feasibility: best ongoing path.

Needs:

- archive daily radar theme definitions from the day they are created.
- require every new theme-map membership change to include source metadata.
- store membership change history instead of overwriting `theme_map.csv`.

Formal-grade status: most defensible for future windows after enough live
archive history accumulates.

## Manual Maintenance Requirements

Manual work is unavoidable for custom themes because there is no single official
exchange dataset for radar-defined themes such as AI server/ODM, CPO/silicon
photonics, PCB/substrate, memory, robotics, or power/BBU.

Minimum human-maintained items:

- theme taxonomy and alias mapping.
- source selection and confidence grading.
- evidence review, rejection, and expiration.
- source license status and redistribution boundary.
- handling ambiguous business exposure, e.g. product page exists now but
  historical availability is unclear.
- deciding whether a symbol is a core member or only a loose market proxy.

## Not Automatable Reliably

- proving historical theme membership from today's company/product page.
- inferring membership solely from price action, turnover, or market chatter.
- using current `theme_map.csv` as if it existed in 2022-2023.
- redistributing paid research/news text without license review.
- resolving theme taxonomy changes without human judgment.
- turning partial memory coverage into all-theme formal top3 evidence.

## Engineering Notes For A Future Implementation

Recommended modules:

- `rotation_radar/theme_membership_evidence.py`
- `rotation_radar/date_aware_theme_membership_v2.py`
- `tests/test_date_aware_theme_membership_v2.py`

Recommended commands:

- build evidence queue from current gap CSV.
- validate evidence ledger schema and source dates.
- generate normalized intervals.
- regenerate readiness JSON.

No implementation should alter daily report templates, fixed PDF paths, Drive
file ids, LINE behavior, or `ep04_sector_radar_numbers.csv`.

## Current Formal-Grade Decision

`formal_ready=false`.

The correct next state is not "radar formal backtest ready"; it is:

`blocked_with_v2_evidence_collection_plan`.

This moves the project forward by defining exactly what evidence must be
collected and maintained, while preserving the current formal-grade boundary.
