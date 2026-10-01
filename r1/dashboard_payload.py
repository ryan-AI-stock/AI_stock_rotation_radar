from __future__ import annotations

import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


def build_dashboard_payload(*, config_path: str | Path, market_path: str | Path) -> dict:
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    tabs: dict[str, list[list[object]]] = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}
    tabs["R1 Dashboard"].extend([
        ["Portfolio Summary", "Model", "R1", "CHALLENGER", market["date"]],
        ["Data Quality", "Market coverage", f"{market['actual_ticker_count']}/{market['requested_ticker_count']}",
         "READY" if not market["gaps"] else "DATA_MISSING", market["date"]],
        ["Data Quality", "EPS Consensus", "Not configured", "DATA_MISSING", market["date"]],
        ["Actions", "Trade decisions", "Disabled until consensus and evidence are ready", "BLOCKED", market["date"]],
    ])
    total_value = sum((market_by_ticker[s.ticker]["raw_close"] or 0) * s.shares for s in config.securities)
    for security in config.securities:
        row = market_by_ticker[security.ticker]
        value = (row["raw_close"] or 0) * security.shares
        tabs["Portfolio"].append([
            security.ticker, security.company, security.shares, security.core_lock,
            row["raw_close"], value, value / total_value if total_value else None,
            None, "CORE" if security.core_lock else "DATA_MISSING",
            "CORE_LOCK" if security.core_lock else "EPS_CONSENSUS_NOT_CONFIGURED",
        ])
        for role in security.roles:
            tabs["Universe"].append([
                security.ticker, security.company, security.market, role, None,
                "ACTIVE", None, "DATA_MISSING",
            ])
        tabs["Daily Market Data"].append([
            market["date"], security.ticker, row["raw_close"], row["adjusted_analysis_close"],
            row["daily_return"], row["return_1w"], row["return_1m"], row["return_3m"], row["return_6m"],
            row["ma20"], row["ma60"], row["bias20"], row["bias60"], row["volume"], row["avg_volume_20d"],
            row["turnover_value"], row["avg_turnover_20d"],
        ])
    for key, value in sorted(config.weights.items()):
        tabs["Config"].append([f"weight.{key}", value, market["date"], config.version, "config/r1.json"])
    tabs["Config"].append(["rotation.max_weekly_rotation", config.max_weekly_rotation,
                           market["date"], config.version, "config/r1.json"])
    validate_tabs(tabs)
    return {"model": "R1", "date": market["date"], "tabs": tabs,
            "formal_model_changed": False, "trade_decision_changed": False,
            "active_in_trade_decision": False, "report_changed": False}
