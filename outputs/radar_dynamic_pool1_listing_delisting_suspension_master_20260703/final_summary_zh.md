# Dynamic Pool1 listing / delisting / suspension master metadata

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-LISTING-DELISTING-SUSPENSION-MASTER-20260703`
- Status: `completed_partial_event_sources_but_master_ready_false`
- Accepted listing/delisting metadata rows: `379`
- Accepted suspension/resumption event rows: `178`
- Proxy/current snapshot rows: `2153`
- Blocked source rows: `3`
- listing_delisting_suspension_metadata_ready: `false`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- future_data_violation_count: `0`

## Accepted partial event sources

- TWSE `/company/suspendListingCsvAndHtml` produced dated official delisting rows.
- TWSE `/company/newlisting` produced dated recent listing rows where `ListingDate` or `ApprovedListingDate` was present.
- TPEx `/tpex_spendi_history` produced dated suspension/resumption rows.

These rows are source-backed event evidence, but they are not a complete 2015-latest master. Dynamic Pool1 cannot use this package alone as a formal tradable-universe master.

## Proxy-only sources

TWSE/TPEx current company profile and current status endpoints were saved to `proxy_source_rows.csv` only. They were not used to infer 2015 historical membership, delisting, suspension, resumption, transfer listing, or name change state.

## Remaining blockers

- TWSE full historical suspension/resumption master was not found in this bounded OpenAPI probe.
- TPEx complete historical listing/delisting master was not found in this bounded OpenAPI probe.
- Code/name change and transfer listing master still needs a date-range MOPS/TWSE/TPEx material-information crawler.

## Boundary

No strategy replay, formal model change, trade decision change, or report change was made.
