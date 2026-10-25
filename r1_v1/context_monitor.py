from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def build_context_monitor(snapshots: list[dict], output: str | Path) -> dict:
    latest_date = max((s["date"] for s in snapshots), default=None)
    current = [s for s in snapshots if s["date"] == latest_date]
    market_state = current[0]["market_context"]["market_state"] if current else "UNKNOWN"
    theme_states = {}
    for row in current:
        theme_states[row["theme_id"]] = row["theme_context"]["theme_context_state"]
    def select(anomaly: str):
        return [r["ticker"] for r in current if r["anomaly_type"] == anomaly][:10]
    payload = {"status": "RESEARCH_DEBUG_ONLY", "date": latest_date,
        "market_state": market_state, "theme_states": theme_states,
        "top_market_driven_movers": select("MARKET_DRIVEN_MOVE"),
        "top_theme_driven_movers": select("THEME_DRIVEN_MOVE"),
        "top_company_specific_movers": select("COMPANY_SPECIFIC_MOVE"),
        "possible_mispricing_candidates": [r["ticker"] for r in current if r["possible_mispricing_candidate"]],
        "unknown_or_data_missing": [r["ticker"] for r in current if r["primary_context"] == "UNKNOWN" or r["unknowns"]],
        "attribution_counts": dict(Counter(r["primary_context"] for r in current)),
        "snapshots": current,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False}
    path=Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
