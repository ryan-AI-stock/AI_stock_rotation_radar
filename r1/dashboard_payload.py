from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


def _latest_valuation_rows(root: str | Path, target_date: str) -> dict[str, dict]:
    files = sorted(path for path in Path(root).glob("????-??-??.json") if path.stem <= target_date)
    if not files:
        return {}
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return {row["ticker"]: row for row in payload.get("rows", [])}


def build_dashboard_payload(
    *, config_path: str | Path, market_path: str | Path,
    readiness_path: str | Path = "data/r1/evidence_readiness.json",
    valuation_root: str | Path = "data/r1/valuation_history",
) -> dict:
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
    valuation_by_ticker = _latest_valuation_rows(valuation_root, market["date"])
    tabs: dict[str, list[list[object]]] = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}

    total_value = sum((market_by_ticker[s.ticker]["raw_close"] or 0) * s.shares for s in config.securities)
    held_count = sum(security.shares > 0 for security in config.securities)
    tabs["R1 Dashboard"].extend([
        ["帳戶摘要", "模型", "R1", "CHALLENGER", market["date"]],
        ["帳戶摘要", "目前持股市值", total_value, "參考估值", market["date"]],
        ["帳戶摘要", "目前持股檔數", held_count, "參考資料", market["date"]],
        ["資料品質", "市場資料", f"{market['actual_ticker_count']}/{market['requested_ticker_count']}",
         "READY" if not market["gaps"] else "DATA_MISSING", market["date"]],
        ["資料品質", "EPS共識", f"{readiness['consensus_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["consensus_ready_count"] == readiness["requested_ticker_count"] else "PARTIAL", market["date"]],
        ["資料品質", "催化證據", f"{readiness['catalyst_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["catalyst_ready_count"] == readiness["requested_ticker_count"] else "PARTIAL", market["date"]],
        ["資料品質", "瓶頸證據", f"{readiness['bottleneck_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["bottleneck_ready_count"] == readiness["requested_ticker_count"] else "PARTIAL", market["date"]],
        ["模型狀態", "交易建議", f"{readiness['trade_ready_count']}/{readiness['requested_ticker_count']}",
         "READY" if readiness["trade_ready_count"] else "BLOCKED", market["date"]],
        ["模型狀態", "說明", "資料與Action門檻未完整核准前，只顯示研究資料，不產生模擬成交。",
         "CHALLENGER", market["date"]],
    ])

    for security in config.securities:
        row = market_by_ticker[security.ticker]
        readiness_row = readiness_by_ticker.get(security.ticker, {})
        valuation_row = valuation_by_ticker.get(security.ticker, {})
        if security.core_lock:
            action, reason = "CORE", "CORE_LOCK"
        elif readiness_row.get("trade_ready"):
            action, reason = "WATCH", "ACTION_ENGINE_NOT_MATERIALIZED"
        else:
            action = "DATA_MISSING"
            reason = ";".join(readiness_row.get("blocked_reasons", ["READINESS_NOT_MATERIALIZED"]))
        tabs["R1每日訊號資料庫"].append([
            market["date"], security.ticker, security.company, row["raw_close"], row["daily_return"],
            row["return_1w"], row["return_1m"], row["return_3m"], row["return_6m"], row["ma20"],
            row["ma60"], row["bias20"], row["bias60"], row["turnover_value"], row["avg_turnover_20d"],
            valuation_row.get("forward_eps_mean"), valuation_row.get("forward_pe"),
            bool(readiness_row.get("consensus_ready")), bool(readiness_row.get("catalyst_ready")),
            bool(readiness_row.get("bottleneck_ready")), bool(readiness_row.get("valuation_ready")),
            bool(readiness_row.get("price_chip_ready")), None, action, reason,
        ])

    # No transaction row is emitted until the action policy and execution ledger are both approved.
    validate_tabs(tabs)
    return {
        "model": "R1", "date": market["date"], "tabs": tabs,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the three-tab R1 dashboard payload.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--readiness", default="data/r1/evidence_readiness.json")
    parser.add_argument("--valuation-root", default="data/r1/valuation_history")
    parser.add_argument("--output", default="data/r1/dashboard_payload.json")
    args = parser.parse_args()
    payload = build_dashboard_payload(
        config_path=args.config, market_path=args.market, readiness_path=args.readiness,
        valuation_root=args.valuation_root,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
