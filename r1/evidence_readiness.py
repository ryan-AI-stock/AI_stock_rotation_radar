from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

from r1.config import R1Config
from r1.catalyst_evidence import evidence_ready, load_catalyst_evidence
from r1.bottleneck_evidence import evidence_ready as bottleneck_evidence_ready, load_bottleneck_evidence
from r1.consensus import consensus_actionable, load_consensus_csv, load_consensus_evidence
from r1.evidence import load_catalyst_csv


def _price_chip_coverage(root: str | Path, *, as_of_date: str, minimum_days: int = 20) -> dict[str, dict]:
    """Count complete PIT trading dates; this is source readiness, not a trading score."""
    coverage: dict[str, dict[str, set[str]]] = {}
    for path in sorted(Path(root).glob("????-??-??.json")):
        if date.fromisoformat(path.stem) > date.fromisoformat(as_of_date):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload_date = str(payload.get("date", ""))[:10]
        if not payload_date or payload_date != path.stem:
            continue
        for row in payload.get("price_rows", []):
            ticker = str(row.get("ticker", "")).zfill(4)
            if ticker and row.get("close") not in {None, ""}:
                coverage.setdefault(ticker, {"price": set(), "institutional": set(), "margin_short": set()})[
                    "price"
                ].add(payload_date)
        for row in payload.get("chip_rows", []):
            ticker = str(row.get("ticker", "")).zfill(4)
            family = str(row.get("family", ""))
            if ticker and family in {"institutional", "margin_short"}:
                coverage.setdefault(ticker, {"price": set(), "institutional": set(), "margin_short": set()})[
                    family
                ].add(payload_date)
    return {
        ticker: {
            "price_days": len(families["price"]),
            "institutional_days": len(families["institutional"]),
            "margin_short_days": len(families["margin_short"]),
            "ready": all(len(families[family]) >= minimum_days for family in families),
        }
        for ticker, families in coverage.items()
    }


def _current_chip_coverage(root: str | Path, *, as_of_date: str) -> dict[str, bool]:
    """Exact-date PIT readiness. Historical sequence readiness is intentionally separate."""
    path = Path(root) / f"{as_of_date}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    families: dict[str, set[str]] = {}
    for row in payload.get("chip_rows", []):
        ticker = str(row.get("ticker", "")).zfill(4)
        family = str(row.get("family", ""))
        if ticker and family in {"institutional", "margin_short"}:
            families.setdefault(ticker, set()).add(family)
    return {ticker: values == {"institutional", "margin_short"} for ticker, values in families.items()}


def _valuation_reference(path: str | Path, *, as_of_date: str) -> dict[str, dict]:
    source = Path(path)
    if not source.exists():
        return {}
    rows: dict[str, dict] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("ticker", "")).zfill(4)
            data_date = str(row.get("data_date", ""))[:10]
            try:
                percentile = float(row["five_year_percentile"])
            except (KeyError, TypeError, ValueError):
                continue
            if ticker and data_date and data_date <= as_of_date and 0 <= percentile <= 1:
                rows[ticker] = {**row, "five_year_percentile": percentile}
    return rows


def _eps_revision_coverage(root: str | Path, *, as_of_date: str, fiscal_year: int) -> dict[str, bool]:
    snapshots: list[tuple[str, dict]] = []
    for path in sorted(Path(root).glob("????-??-??.json")):
        if path.stem <= as_of_date:
            snapshots.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
    horizons = (7, 28, 84)
    current_day = date.fromisoformat(as_of_date)
    result: dict[str, bool] = {}
    tickers = {
        str(row.get("ticker", "")).zfill(4)
        for _, payload in snapshots for row in payload.get("rows", [])
    }
    for ticker in tickers:
        ready = True
        for days in horizons:
            cutoff = (current_day - timedelta(days=days)).isoformat()
            found = any(
                snapshot_date <= cutoff and any(
                    str(row.get("ticker", "")).zfill(4) == ticker
                    and int(row.get("fiscal_year", 0)) == fiscal_year
                    and row.get("status") == "READY" and row.get("mean_eps") not in {None, 0}
                    for row in payload.get("rows", [])
                )
                for snapshot_date, payload in snapshots
            )
            ready = ready and found
        result[ticker] = ready
    return result


def _eps_revision_progress(root: str | Path, *, as_of_date: str, fiscal_year: int) -> dict:
    first_dates: dict[str, str] = {}
    ready_counts = {"1w": 0, "4w": 0, "12w": 0}
    horizons = {"1w": 7, "4w": 28, "12w": 84}
    snapshots: list[tuple[str, dict]] = []
    for path in sorted(Path(root).glob("????-??-??.json")):
        if path.stem <= as_of_date:
            snapshots.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
    tickers = set()
    for snapshot_date, payload in snapshots:
        for row in payload.get("rows", []):
            ticker = str(row.get("ticker", "")).zfill(4)
            if (ticker and int(row.get("fiscal_year", 0)) == fiscal_year
                    and row.get("status") == "READY" and row.get("mean_eps") not in {None, 0}):
                tickers.add(ticker)
                first_dates.setdefault(ticker, snapshot_date)
    current_day = date.fromisoformat(as_of_date)
    for label, days in horizons.items():
        cutoff = (current_day - timedelta(days=days)).isoformat()
        ready_counts[label] = sum(first_date <= cutoff for first_date in first_dates.values())
    first_observation = min(first_dates.values()) if first_dates else None
    return {
        "first_observation_date": first_observation,
        "observed_ticker_count": len(tickers),
        "ready_counts": ready_counts,
        "earliest_calendar_eligibility": {
            label: None if first_observation is None else (
                date.fromisoformat(first_observation) + timedelta(days=days)
            ).isoformat()
            for label, days in horizons.items()
        },
        "note": "Calendar eligibility does not guarantee a usable snapshot; the first later weekly run must still contain valid PIT consensus.",
    }


def materialize(*, config_path: str | Path, consensus_path: str | Path,
                catalyst_path: str | Path, as_of_date: str,
                consensus_evidence_path: str | Path = "data/r1/consensus/evidence.csv",
                bottleneck_path: str | Path = "data/r1/bottleneck_map.json",
                catalyst_evidence_path: str | Path = "data/r1/catalyst_events/evidence.csv",
                bottleneck_evidence_path: str | Path = "data/r1/bottleneck_evidence.csv",
                daily_source_root: str | Path = "data/r1/daily_sources",
                valuation_reference_path: str | Path = "data/r1/valuation_reference.csv",
                consensus_history_root: str | Path = "data/r1/consensus_history") -> dict:
    config = R1Config.load(config_path)
    consensus_file = Path(consensus_path)
    catalyst_file = Path(catalyst_path)
    consensus = load_consensus_csv(consensus_file, as_of_date=as_of_date) if consensus_file.exists() else None
    support_file = Path(consensus_evidence_path)
    support, support_rejected = load_consensus_evidence(support_file, as_of_date=as_of_date) if support_file.exists() else ([], [])
    catalysts, catalyst_rejected = load_catalyst_csv(catalyst_file, as_of_date=as_of_date) if catalyst_file.exists() else ([], [])
    catalyst_evidence_file = Path(catalyst_evidence_path)
    catalyst_evidence, catalyst_evidence_rejected = load_catalyst_evidence(
        catalyst_evidence_file, as_of_date=as_of_date
    ) if catalyst_evidence_file.exists() else ([], [])
    bottleneck_file = Path(bottleneck_path)
    bottleneck_payload = json.loads(bottleneck_file.read_text(encoding="utf-8")) if bottleneck_file.exists() else {"rows": []}
    bottleneck_by_ticker = {str(row.get("ticker", "")).zfill(4): row for row in bottleneck_payload.get("rows", [])}
    bottleneck_evidence_file = Path(bottleneck_evidence_path)
    bottleneck_evidence, bottleneck_evidence_rejected = load_bottleneck_evidence(
        bottleneck_evidence_file, as_of_date=as_of_date
    ) if bottleneck_evidence_file.exists() else ([], [])
    price_chip_coverage = _price_chip_coverage(daily_source_root, as_of_date=as_of_date)
    current_chip_coverage = _current_chip_coverage(daily_source_root, as_of_date=as_of_date)
    fiscal_year = int(as_of_date[:4]) + 1
    valuation_reference = _valuation_reference(valuation_reference_path, as_of_date=as_of_date)
    eps_revision_coverage = _eps_revision_coverage(
        consensus_history_root, as_of_date=as_of_date, fiscal_year=fiscal_year,
    )
    eps_revision_progress = _eps_revision_progress(
        consensus_history_root, as_of_date=as_of_date, fiscal_year=fiscal_year,
    )
    rows = []
    for security in config.securities:
        consensus_ready = bool(consensus and consensus_actionable(
            consensus.records, ticker=security.ticker, fiscal_year=fiscal_year, evidence=support))
        ticker_events = [row for row in catalysts if row.event.ticker == security.ticker]
        catalyst_score_ready = len({row.source_family for row in ticker_events}) >= 2 and any(
            row.event.source_tier <= 2 for row in ticker_events)
        catalyst_ready = evidence_ready(catalyst_evidence, ticker=security.ticker)
        bottleneck_ready = (
            bottleneck_by_ticker.get(security.ticker, {}).get("evidence_status") == "VERIFIED"
            or bottleneck_evidence_ready(bottleneck_evidence, ticker=security.ticker)
        )
        valuation_ready = security.ticker in valuation_reference
        eps_revision_ready = bool(eps_revision_coverage.get(security.ticker, False))
        price_chip_state = price_chip_coverage.get(security.ticker, {
            "price_days": 0, "institutional_days": 0, "margin_short_days": 0, "ready": False,
        })
        price_chip_ready = bool(price_chip_state["ready"])
        current_chip_ready = bool(current_chip_coverage.get(security.ticker, False))
        component_score_ready = (
            consensus_ready and eps_revision_ready and catalyst_score_ready and bottleneck_ready
            and valuation_ready and price_chip_ready
        )
        trade_ready = component_score_ready and config.action_policy_approved
        blocked_reasons = []
        if not consensus_ready:
            blocked_reasons.append("CONSENSUS_NOT_READY")
        if not eps_revision_ready:
            blocked_reasons.append("EPS_REVISION_HISTORY_NOT_READY")
        if not catalyst_ready:
            blocked_reasons.append("CATALYST_EVIDENCE_NOT_READY")
        if not bottleneck_ready:
            blocked_reasons.append("BOTTLENECK_EVIDENCE_NOT_READY")
        if not valuation_ready:
            blocked_reasons.append("VALUATION_HISTORY_NOT_READY")
        if not price_chip_ready:
            blocked_reasons.append("PRICE_CHIP_HISTORY_NOT_READY")
        if not config.action_policy_approved:
            blocked_reasons.append("ACTION_POLICY_NOT_APPROVED")
        rows.append({
            "ticker": security.ticker,
            "consensus_ready": consensus_ready,
            "eps_revision_ready": eps_revision_ready,
            "catalyst_ready": catalyst_ready,
            "catalyst_score_ready": catalyst_score_ready,
            "bottleneck_ready": bottleneck_ready,
            "valuation_ready": valuation_ready,
            "price_chip_ready": price_chip_ready,
            "current_chip_ready": current_chip_ready,
            "price_chip_coverage": price_chip_state,
            "component_score_ready": component_score_ready,
            "trade_ready": trade_ready,
            "blocked_reasons": blocked_reasons,
        })
    return {
        "model": "R1", "as_of_date": as_of_date, "fiscal_year": fiscal_year,
        "requested_ticker_count": len(rows),
        "consensus_ready_count": sum(row["consensus_ready"] for row in rows),
        "eps_revision_ready_count": sum(row["eps_revision_ready"] for row in rows),
        "eps_revision_progress": eps_revision_progress,
        "catalyst_ready_count": sum(row["catalyst_ready"] for row in rows),
        "catalyst_score_ready_count": sum(row["catalyst_score_ready"] for row in rows),
        "bottleneck_ready_count": sum(row["bottleneck_ready"] for row in rows),
        "price_chip_ready_count": sum(row["price_chip_ready"] for row in rows),
        "current_chip_ready_count": sum(row["current_chip_ready"] for row in rows),
        "component_score_ready_count": sum(row["component_score_ready"] for row in rows),
        "trade_ready_count": sum(row["trade_ready"] for row in rows),
        "action_policy_approved": config.action_policy_approved,
        "consensus_rejected": list(consensus.rejected) if consensus else [{"error": "file_missing"}],
        "consensus_evidence_rejected": support_rejected if support_file.exists() else [{"error": "file_missing"}],
        "catalyst_rejected": catalyst_rejected if catalyst_file.exists() else [{"error": "file_missing"}],
        "catalyst_evidence_rejected": catalyst_evidence_rejected if catalyst_evidence_file.exists() else [{"error": "file_missing"}],
        "bottleneck_evidence_rejected": bottleneck_evidence_rejected if bottleneck_evidence_file.exists() else [{"error": "file_missing"}],
        "rows": rows,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize R1 evidence readiness without inventing scores.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--catalysts", default="data/r1/catalyst_events/events.csv")
    parser.add_argument("--catalyst-evidence", default="data/r1/catalyst_events/evidence.csv")
    parser.add_argument("--bottleneck-evidence", default="data/r1/bottleneck_evidence.csv")
    parser.add_argument("--consensus-evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--daily-source-root", default="data/r1/daily_sources")
    parser.add_argument("--valuation-reference", default="data/r1/valuation_reference.csv")
    parser.add_argument("--consensus-history-root", default="data/r1/consensus_history")
    parser.add_argument("--output", default="data/r1/evidence_readiness.json")
    args = parser.parse_args()
    payload = materialize(config_path=args.config, consensus_path=args.consensus,
                          catalyst_path=args.catalysts, as_of_date=args.date,
                          consensus_evidence_path=args.consensus_evidence,
                          catalyst_evidence_path=args.catalyst_evidence,
                          bottleneck_evidence_path=args.bottleneck_evidence,
                          daily_source_root=args.daily_source_root,
                          valuation_reference_path=args.valuation_reference,
                          consensus_history_root=args.consensus_history_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
