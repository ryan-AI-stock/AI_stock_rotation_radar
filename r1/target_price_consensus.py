from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
import csv
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TargetPriceRecord:
    ticker: str
    institution: str
    target_price: float
    horizon: str
    available_at: str
    source_url: str


def build_consensus(*, records: list[TargetPriceRecord], ticker: str, current_price: float,
                    as_of_date: str, minimum_institutions: int = 3,
                    maximum_age_days: int = 90) -> dict:
    asof = date.fromisoformat(as_of_date)
    accepted: dict[str, TargetPriceRecord] = {}
    rejected: list[dict[str, str]] = []
    for row in records:
        if row.ticker != ticker:
            continue
        try:
            available = date.fromisoformat(row.available_at[:10])
            age = (asof - available).days
            if age < 0:
                raise ValueError("future_data")
            if age > maximum_age_days:
                raise ValueError("stale")
            if row.horizon.upper() != "12M":
                raise ValueError("horizon_not_12m")
            if not row.institution.strip() or not row.source_url.strip() or row.target_price <= 0:
                raise ValueError("identity_price_or_source_missing")
            previous = accepted.get(row.institution.strip())
            if previous is None or row.available_at > previous.available_at:
                accepted[row.institution.strip()] = row
        except ValueError as exc:
            rejected.append({"institution": row.institution, "error": str(exc)})
    values = [row.target_price for row in accepted.values()]
    ready = len(values) >= minimum_institutions and current_price > 0
    consensus = median(values) if values else None
    upside = consensus / current_price - 1 if ready else None
    dispersion = ((max(values) - min(values)) / consensus) if ready and consensus else None
    return {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "institution_count": len(values),
        "consensus_target_price": consensus,
        "consensus_upside": upside,
        "dispersion": dispersion,
        "status": "READY" if ready else "DATA_MISSING",
        "scoreable": ready,
        "rejected": rejected,
        "source_policy": "12M median; independent identifiable institutions; PIT max 90 days",
    }


def load_records(path: str | Path) -> list[TargetPriceRecord]:
    source = Path(path)
    if not source.exists():
        return []
    rows: list[TargetPriceRecord] = []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append(TargetPriceRecord(
                    ticker=str(row["ticker"]).zfill(4), institution=row["institution"].strip(),
                    target_price=float(row["target_price"]), horizon=row["horizon"].strip(),
                    available_at=row["available_at"].strip(), source_url=row["source_url"].strip(),
                ))
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def build_snapshot(*, date: str, market: dict[str, Any], tickers: list[str],
                   evidence_path: str | Path) -> dict[str, Any]:
    records = load_records(evidence_path)
    closes = {str(row["ticker"]).zfill(4): row.get("raw_close") for row in market.get("rows", [])}
    rows = [build_consensus(
        records=records, ticker=ticker, current_price=float(closes.get(ticker) or 0), as_of_date=date,
    ) for ticker in tickers]
    return {
        "date": date, "rows": rows, "requested_ticker_count": len(tickers),
        "ready_ticker_count": sum(row["status"] == "READY" for row in rows),
        "source": str(evidence_path),
    }


def write_snapshot(*, date: str, market_path: str | Path, config_path: str | Path,
                   evidence_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    from r1.config import R1Config
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    config = R1Config.load(config_path)
    payload = build_snapshot(
        date=date, market=market, tickers=[row.ticker for row in config.securities],
        evidence_path=evidence_path,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
