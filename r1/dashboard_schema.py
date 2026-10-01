from __future__ import annotations


TAB_SCHEMAS = {
    "R1 Dashboard": ("section", "metric", "value", "status", "as_of_date"),
    "Portfolio": ("ticker", "company", "shares", "core_lock", "price", "position_value", "current_weight", "target_weight", "action", "reason"),
    "Universe": ("ticker", "company", "market", "role", "bottleneck", "status", "added_date", "evidence_status"),
    "Weekly Snapshot": ("date", "ticker", "company", "price", "position_shares", "position_value", "portfolio_weight", "next_year_eps", "eps_rev_1w", "eps_rev_4w", "eps_rev_12w", "forward_pe", "base_upside", "bias20", "bias60", "total_score", "action", "target_weight", "suggested_transfer"),
    "Daily Market Data": ("date", "ticker", "raw_close", "adjusted_analysis_close", "daily_return", "return_1w", "return_1m", "return_3m", "return_6m", "ma20", "ma60", "bias20", "bias60", "volume", "avg_volume_20d", "turnover_value", "avg_turnover_20d"),
    "EPS Consensus History": ("ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps", "analyst_count", "source", "published_at", "available_at", "retrieved_at", "quality", "status"),
    "Valuation": ("date", "ticker", "price", "forward_eps", "forward_pe", "forward_pe_percentile", "bear_eps", "base_eps", "bull_eps", "bear_pe", "base_pe", "bull_pe", "bear_fair_value", "base_fair_value", "bull_fair_value", "bear_upside", "base_upside", "bull_upside"),
    "Bottleneck Map": ("date", "category", "tightness", "trend", "global_companies", "taiwan_candidates", "stage", "thesis", "evidence_status"),
    "Catalyst Events": ("event_date", "ticker", "event_type", "description", "source_url", "source_tier", "impact_direction", "impact_score", "confidence", "expiry_weeks", "affected_bottleneck"),
    "Discovery Pool": ("discovery_date", "ticker", "company", "bottleneck", "reason", "evidence_count", "source_quality", "revenue_exposure", "customer_evidence", "financial_evidence", "potential_eps_impact", "status"),
    "Rotation History": ("date", "ticker", "current_weight", "target_weight", "weight_gap", "action", "uncapped_transfer", "suggested_transfer", "reason"),
    "Config": ("key", "value", "effective_date", "version", "notes"),
    "Data Quality Logs": ("date", "ticker", "field_group", "source", "as_of_date", "available_at", "retrieved_at", "quality", "status", "error"),
}


def validate_tabs(tabs: dict[str, list[list[object]]]) -> None:
    missing = set(TAB_SCHEMAS) - set(tabs)
    extra = set(tabs) - set(TAB_SCHEMAS)
    if missing or extra:
        raise ValueError(f"R1 tab topology mismatch missing={sorted(missing)} extra={sorted(extra)}")
    for title, schema in TAB_SCHEMAS.items():
        rows = tabs[title]
        if not rows or tuple(rows[0]) != schema:
            raise ValueError(f"R1 tab header mismatch: {title}")
        width = len(schema)
        if any(len(row) != width for row in rows):
            raise ValueError(f"R1 tab row width mismatch: {title}")
