# Date-Aware Theme Membership Plan

## Goal

Upgrade from `theme_membership_mode=current_static_map` to:

- `theme_membership_mode=date_aware`

## Required Schema

```csv
symbol,name,theme,effective_start,effective_end,source_date,source_type,source_url,confidence,notes
```

## Current Gap

Current `data/theme_map.csv` contains:

```csv
theme,symbol,name,role,conviction,primary
```

It has no effective dates, source dates, evidence, or confidence. Applying today's theme map back to 2021-2023 creates historical membership bias.

## Feasibility

Status: `feasible_with_curated_evidence_or_later_start_date`.

There is no single official exchange dataset for custom market themes such as memory, AI server/ODM, PCB/substrate, CPO, or silicon photonics. These are research-defined themes. Formal replay therefore needs one of the following:

1. Curated historical theme table
   - Use news, company filings, revenue product notes, industry reports, and dated internal research notes.
   - Every membership row gets effective dates and source evidence.

2. Start formal replay only after radar started archiving daily theme maps
   - This avoids backfilling today's theme taxonomy into the past.
   - Earlier data remains `research_only_current_static_map_replay`.

3. Downgrade strategy claim
   - Keep current static map, but label results as "today's theme taxonomy applied backward".
   - This cannot become formal-grade strategy evidence.

## Validation Rules

1. `effective_start <= snapshot_date`.
2. `effective_end` is blank or `snapshot_date <= effective_end`.
3. Every snapshot row must include `theme_membership_source_date`.
4. Rows without source evidence must be excluded or downgraded.

## Suggested First Formal Window

Start with the first date where the radar project has actual archived theme definitions and source evidence. Do not force 2021-2023 formal claims unless a dated historical membership table is built.

## Can This Make Formal Ready Now?

No. The repo currently has only a static theme map.
