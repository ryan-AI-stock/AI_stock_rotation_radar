# Parser And Manual Review SOP

## Goal

Convert manually obtained Yuanta 0050 monthly or domestic quarterly holdings PDFs
into reviewable proxy ledger rows.

## Inputs

- A dated PDF file saved under the Phase 3 filename rule.
- A row in `source_acquisition_checklist.csv`.
- `manual_ledger_template.csv`.
- Local ticker/name mapping, preferably `data/market_universe.generated.csv`.

## Parser Steps

1. Open the PDF with `pdfplumber`.
2. Extract source date from the visible report text.
3. Compare source date with expected `target_snapshot_date`.
4. Try table extraction first.
5. If the monthly 0050 report only exposes top-10 holdings, set:
   - `parser_status=auto_parsed_top10_only`
   - `review_status=manual_review_required`
6. If a full holdings table is present and row extraction succeeds, set:
   - `parser_status=auto_parsed_full_holdings`
   - `review_status=manual_review_required`
7. If parser fails but the PDF is readable by a human, set:
   - `parser_status=manual_entry_required`
   - `review_status=source_pending`

## Manual Entry Steps

1. Enter only rows visible in the source PDF.
2. Do not infer missing rows from another month.
3. Use ticker/name mapping from local market universe; if uncertain, leave
   ticker blank and add a note.
4. Every manually entered row must include:
   - source file
   - source report date
   - download method
   - reviewer or blank reviewer if not reviewed yet
   - proxy flags

## Review Steps

1. Reviewer opens the PDF and ledger side by side.
2. Confirm source date.
3. Confirm each ticker/name/weight against the PDF.
4. Confirm `is_proxy=true`.
5. Confirm `exact_tw50_official_constituents=false`.
6. Set `review_status=manual_reviewed`.
7. Set `review_status=accepted` only after source date, rows, and proxy flags all
   pass.

## Rejection Rules

Set `review_status=rejected` if:

- file is not a traceable Yuanta or official source
- file date does not match claimed snapshot date
- rows are from a later/current report but assigned to historical dates
- row values cannot be read reliably
- source only has top-10 holdings but downstream requires full holdings

## Output Rule

Accepted rows remain proxy rows. They do not become exact TW50 official
constituent rows.
