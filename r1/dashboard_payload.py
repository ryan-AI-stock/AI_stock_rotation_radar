from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


def build_dashboard_payload(*, config_path: str | Path, market_path: str | Path,
                            readiness_path: str | Path = "data/r1/evidence_readiness.json") -> dict:
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    readiness_file = Path(readiness_path)
    readiness = json.loads(readiness_file.read_text(encoding="utf-8")) if readiness_file.exists() else {
        "requested_ticker_count": len(config.securities), "consensus_ready_count": 0,
        "catalyst_ready_count": 0, "bottleneck_ready_count": 0, "trade_ready_count": 0,
        "action_policy_approved": False, "rows": [],
    }
    readiness_by_ticker = {row["ticker"]: row for row in readiness.get("rows", [])}
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    tabs: dict[str, list[list[object]]] = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}
    tabs["R1 Dashboard"].extend([
        ["Portfolio Summary", "Model", "R1", "CHALLENGER", market["date"]],
        ["Data Quality", "Market coverage", f"{market['actual_ticker_count']}/{market['requested_ticker_count']}",
         "READY" if not market["gaps"] else "DATA_MISSING", market["date"]],
        ["Data Quality", "EPS Consensus", f"{readiness['consensus_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["consensus_ready_count"] == readiness["requested_ticker_count"] else "PARTIAL", market["date"]],
        ["Data Quality", "Catalyst evidence", f"{readiness['catalyst_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["catalyst_ready_count"] == readiness["requested_ticker_count"] else "PARTIAL", market["date"]],
        ["Data Quality", "Bottleneck evidence", f"{readiness['bottleneck_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["bottleneck_ready_count"] == readiness["requested_ticker_count"] else "DATA_MISSING", market["date"]],
        ["Actions", "Trade decisions", f"{readiness['trade_ready_count']}/{readiness['requested_ticker_count']}; action policy approved={readiness['action_policy_approved']}",
         "READY" if readiness["trade_ready_count"] else "BLOCKED", market["date"]],
    ])
    total_value = sum((market_by_ticker[s.ticker]["raw_close"] or 0) * s.shares for s in config.securities)
    for security in config.securities:
        row = market_by_ticker[security.ticker]
        readiness_row = readiness_by_ticker.get(security.ticker, {})
        value = (row["raw_close"] or 0) * security.shares
        tabs["Portfolio"].append([
            security.ticker, security.company, security.shares, security.core_lock,
            row["raw_close"], value, value / total_value if total_value else None,
            None, "CORE" if security.core_lock else "WATCH" if readiness_row.get("component_score_ready") else "DATA_MISSING",
            "CORE_LOCK" if security.core_lock else ";".join(readiness_row.get("blocked_reasons", ["READINESS_NOT_MATERIALIZED"])),
        ])
        for role in security.roles:
            tabs["Universe"].append([
                security.ticker, security.company, security.market, role, None,
                "ACTIVE", None,
                "READY" if readiness_row.get("trade_ready") else
                "PARTIAL" if any(readiness_row.get(key) for key in ("consensus_ready", "catalyst_ready", "bottleneck_ready")) else
                "DATA_MISSING",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local R1 dashboard payload.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--readiness", default="data/r1/evidence_readiness.json")
    parser.add_argument("--output", default="data/r1/dashboard_payload.json")
    args = parser.parse_args()
    payload = build_dashboard_payload(config_path=args.config, market_path=args.market,
                                      readiness_path=args.readiness)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
