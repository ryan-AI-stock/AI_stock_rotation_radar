from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.providers import MissingConsensusProvider


def build_weekly_snapshot(
    *, date: str, config_path: str | Path, market_path: str | Path,
    daily_source_root: str | Path, output_root: str | Path,
) -> Path:
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    if market.get("date") != date:
        raise ValueError("weekly snapshot market date mismatch")
    if market.get("actual_ticker_count") != market.get("requested_ticker_count"):
        raise ValueError("weekly snapshot requires complete market coverage")
    daily_paths = sorted(Path(daily_source_root).glob("????-??-??.json"))
    daily_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in daily_paths if path.stem <= date]
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    consensus = {row.ticker: row for row in MissingConsensusProvider().fetch(market_by_ticker, date)}
    rows = []
    for security in config.securities:
        market_row = market_by_ticker[security.ticker]
        price_history = [row for payload in daily_payloads for row in payload.get("price_rows", [])
                         if row.get("ticker") == security.ticker]
        chip_today = [row for payload in daily_payloads if payload.get("date") == date
                      for row in payload.get("chip_rows", []) if row.get("ticker") == security.ticker]
        volumes = [float(row["volume"]) for row in price_history if row.get("volume") not in {None, ""}]
        latest_by_family = {row["family"]: row for row in chip_today}
        institution = latest_by_family.get("institutional", {})
        margin = latest_by_family.get("margin_short", {})
        record = consensus[security.ticker]
        rows.append({
            **market_row,
            "position_shares": security.shares,
            "core_lock": security.core_lock,
            "position_value": market_row["raw_close"] * security.shares if market_row["raw_close"] is not None else None,
            "volume": volumes[-1] if volumes else None,
            "avg_volume_20d": sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None,
            "foreign_net": institution.get("foreign_net") or None,
            "trust_net": institution.get("trust_net") or None,
            "dealer_net": institution.get("dealer_net") or None,
            "margin_balance": margin.get("margin_balance") or None,
            "margin_change": margin.get("margin_change") or None,
            "chip_data_status": "AVAILABLE" if institution and margin else "DATA_MISSING",
            "consensus_status": record.status,
            "consensus_quality": record.quality,
            "eps_score": None,
            "valuation_score": None,
            "bottleneck_score": None,
            "catalyst_score": None,
            "price_chip_score": None,
            "total_score": None,
            "action": "CORE" if security.core_lock else "DATA_MISSING",
            "action_reason": "CORE_LOCK" if security.core_lock else "EPS_CONSENSUS_NOT_CONFIGURED",
            "target_weight": None,
            "suggested_transfer": None,
        })
    payload = {
        "model": "R1", "date": date, "snapshot_policy": "append_only",
        "rows": rows, "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output = Path(output_root) / f"weekly_snapshot_{date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != payload:
            raise FileExistsError(f"append-only snapshot already exists with different content: {output}")
        return output
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an append-only R1 weekly snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--daily-source-root", default="data/r1/daily_sources")
    parser.add_argument("--output-root", default="data/r1/weekly")
    args = parser.parse_args()
    print(build_weekly_snapshot(date=args.date, config_path=args.config, market_path=args.market,
                                daily_source_root=args.daily_source_root, output_root=args.output_root))


if __name__ == "__main__":
    main()
