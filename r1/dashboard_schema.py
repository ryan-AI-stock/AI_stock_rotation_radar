from __future__ import annotations


TAB_SCHEMAS = {
    "R1 Dashboard": ("section", "metric", "value", "status", "as_of_date"),
    "R1每日訊號資料庫": (
        "date", "ticker", "company", "raw_close", "daily_return", "return_1w", "return_1m",
        "return_3m", "return_6m", "ma20", "ma60", "bias20", "bias60", "turnover_value",
        "avg_turnover_20d", "forward_eps", "forward_pe", "consensus_ready", "catalyst_ready",
        "bottleneck_ready", "valuation_ready", "price_chip_ready", "total_score", "action", "reason",
    ),
    "R1模擬交易紀錄": (
        "transaction_date", "signal_date", "action", "ticker", "company", "shares", "price",
        "gross_amount", "fees", "tax", "net_cash_flow", "slot", "holding_td", "realized_pnl",
        "withdrawal_amount", "reason_status",
    ),
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
