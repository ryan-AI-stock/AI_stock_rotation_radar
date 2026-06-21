# Core Contract Recommendation: 0050 Holdings Proxy

This package should not satisfy the exact TW50 point-in-time constituent
contract.

## Required Distinction

Exact TW50 constituent history:

- official index membership
- official effective dates
- exact constituent add/delete events
- suitable for exact TW50 validator only when official source coverage is enough

Yuanta 0050 holdings proxy:

- ETF/fund disclosed holdings
- monthly or quarterly snapshot dates
- may differ from official index membership because of ETF operation, cash,
  disclosure timing, sampling, temporary tracking differences, or reporting lag
- suitable for proxy-specific large-cap pool replay only

## Suggested Readiness Fields

- `source_mode`
- `is_proxy`
- `snapshot_date`
- `effective_date`
- `ticker`
- `name`
- `weight_pct`
- `source_url`
- `source_file`
- `parse_status`
- `review_status`
- `proxy_coverage_ratio`
- `exact_tw50_validator_allowed`

## Fail-Closed Rule

If `source_mode=yuanta_0050_holdings_proxy`, Core should set:

- `exact_tw50_validator_allowed=false`
- `tw50_exact_readiness=blocked`
- `tw50_proxy_readiness=partial` or `ready`, depending on snapshot coverage

This prevents proxy rows from silently passing as exact official TW50 history.
