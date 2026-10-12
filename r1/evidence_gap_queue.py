from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.bottleneck_evidence import load_bottleneck_evidence
from r1.catalyst_evidence import load_catalyst_evidence
from r1.config import R1Config


def _state(rows: list, ticker: str) -> dict:
    selected = [row for row in rows if row.ticker == ticker]
    families = sorted({row.source_family for row in selected})
    best_tier = min((row.source_tier for row in selected), default=None)
    return {
        "source_family_count": len(families),
        "source_families": families,
        "best_source_tier": best_tier,
        "ready": len(families) >= 2 and best_tier is not None and best_tier <= 2,
        "missing_independent_source_families": max(0, 2 - len(families)),
        "missing_tier_1_or_2_source": best_tier is None or best_tier > 2,
    }


def materialize(*, as_of_date: str, config_path: str | Path,
                catalyst_path: str | Path, bottleneck_path: str | Path,
                output_path: str | Path,
                theme_path: str | Path = "config/r1_v02_themes.json") -> dict:
    config = R1Config.load(config_path)
    theme_payload = json.loads(Path(theme_path).read_text(encoding="utf-8"))
    theme_by_ticker = {}
    for theme in theme_payload.get("themes", []):
        for member in theme.get("members", []):
            theme_by_ticker.setdefault(str(member[0]).zfill(4), str(theme["id"]))
        for member in theme.get("watch_discovery", []):
            theme_by_ticker.setdefault(str(member[0]).zfill(4), str(theme["id"]) + "_discovery")
    catalyst_file = Path(catalyst_path)
    bottleneck_file = Path(bottleneck_path)
    catalysts, catalyst_rejected = (
        load_catalyst_evidence(catalyst_file, as_of_date=as_of_date)
        if catalyst_file.exists() else ([], [{"error": "file_missing"}])
    )
    bottlenecks, bottleneck_rejected = (
        load_bottleneck_evidence(bottleneck_file, as_of_date=as_of_date)
        if bottleneck_file.exists() else ([], [{"error": "file_missing"}])
    )
    targets = {str(ticker).zfill(4) for ticker in theme_payload.get("target_portfolio_6m", [])}
    rows = []
    for security in config.securities:
        catalyst = _state(catalysts, security.ticker)
        bottleneck = _state(bottlenecks, security.ticker)
        missing = []
        if not catalyst["ready"]:
            missing.append("CATALYST_EVIDENCE")
        if not bottleneck["ready"]:
            missing.append("BOTTLENECK_EVIDENCE")
        rows.append({
            "ticker": security.ticker,
            "company": security.company,
            "theme_id": theme_by_ticker.get(security.ticker, "UNMAPPED"),
            "priority": 0 if security.ticker in targets else 1,
            "catalyst": catalyst,
            "bottleneck": bottleneck,
            "missing": missing,
            "status": "READY" if not missing else "NEEDS_EVIDENCE",
        })
    rows.sort(key=lambda row: (row["status"] == "READY", row["priority"], row["theme_id"], row["ticker"]))
    payload = {
        "model": "R1",
        "version": "r1-evidence-gap-queue-v0.1",
        "as_of_date": as_of_date,
        "requested_ticker_count": len(rows),
        "ready_ticker_count": sum(row["status"] == "READY" for row in rows),
        "pending_ticker_count": sum(row["status"] != "READY" for row in rows),
        "rejected_evidence": {
            "catalyst": catalyst_rejected,
            "bottleneck": bottleneck_rejected,
        },
        "rows": rows,
        "resume_path": str(output_path),
        "future_data_violation_count": sum(
            "future_data" in str(item.get("error", ""))
            for items in (catalyst_rejected, bottleneck_rejected) for item in items
        ),
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": True,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the resumable R1 company-evidence gap queue.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--catalysts", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--bottlenecks", default="data/r1/bottleneck_evidence.csv")
    parser.add_argument("--output", default="data/r1/evidence_gap_queue.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    args = parser.parse_args()
    payload = materialize(
        as_of_date=args.date, config_path=args.config,
        catalyst_path=args.catalysts, bottleneck_path=args.bottlenecks,
        output_path=args.output, theme_path=args.themes,
    )
    print(json.dumps({
        "requested": payload["requested_ticker_count"],
        "ready": payload["ready_ticker_count"],
        "pending": payload["pending_ticker_count"],
        "resume_path": payload["resume_path"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
