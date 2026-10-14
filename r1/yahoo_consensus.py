from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

import yfinance as yf

from r1.toalpha_consensus import CONSENSUS_FIELDS, EVIDENCE_FIELDS


def parse_estimates(table, *, ticker: str, retrieved_at: str) -> list[dict[str, str]]:
    """Convert Yahoo Finance's labelled annual estimates without inferring absent values."""
    if table is None or getattr(table, "empty", True):
        raise ValueError("annual_eps_estimates_missing")
    fiscal_year = int(retrieved_at[:4])
    mapping = {"0y": fiscal_year, "+1y": fiscal_year + 1}
    rows: list[dict[str, str]] = []
    for period, year in mapping.items():
        if period not in table.index:
            continue
        row = table.loc[period]
        mean_eps = row.get("avg")
        analysts = row.get("numberOfAnalysts")
        if mean_eps is None or analysts is None or float(mean_eps) == 0 or int(analysts) < 2:
            continue
        rows.append({
            "ticker": ticker, "fiscal_year": str(year), "mean_eps": f"{float(mean_eps):.12g}",
            "median_eps": f"{float(mean_eps):.12g}",
            "high_eps": "" if row.get("high") is None else f"{float(row['high']):.12g}",
            "low_eps": "" if row.get("low") is None else f"{float(row['low']):.12g}",
            "analyst_count": str(int(analysts)), "source": "Yahoo Finance analyst consensus",
            "published_at": retrieved_at, "available_at": retrieved_at, "retrieved_at": retrieved_at,
            "quality": "MEDIUM", "status": "READY",
        })
    if {row["fiscal_year"] for row in rows} != {str(fiscal_year), str(fiscal_year + 1)}:
        raise ValueError("current_and_next_year_estimates_incomplete")
    return rows


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def acquire(*, tickers: list[str], consensus_path: str | Path, evidence_path: str | Path,
            checkpoint_path: str | Path, retrieved_at: str | None = None,
            market_by_ticker: dict[str, str] | None = None) -> dict:
    retrieved_at = retrieved_at or date.today().isoformat()
    checkpoint = Path(checkpoint_path)
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if state.get("retrieved_at") != retrieved_at:
        state = {"retrieved_at": retrieved_at, "completed": {}, "failed": {}}
    allowed = {str(ticker).zfill(4) for ticker in tickers}
    state["completed"] = {k: v for k, v in state.get("completed", {}).items() if k in allowed}
    state["failed"] = {k: v for k, v in state.get("failed", {}).items() if k in allowed}
    for ticker in sorted(allowed):
        if ticker in state["completed"]:
            continue
        try:
            suffix = ".TWO" if (market_by_ticker or {}).get(ticker) == "TPEx" else ".TW"
            table = yf.Ticker(ticker + suffix).get_earnings_estimate(as_dict=False)
            rows = parse_estimates(table, ticker=ticker, retrieved_at=retrieved_at)
            state["completed"][ticker] = {"symbol": ticker + suffix, "rows": rows}
            state["failed"].pop(ticker, None)
        except Exception as exc:
            state["failed"][ticker] = {"error": f"{type(exc).__name__}:{exc}"}
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    consensus = _read(Path(consensus_path))
    keys = {(r["ticker"], r["fiscal_year"], r["available_at"], r["source"]) for r in consensus}
    evidence = _read(Path(evidence_path))
    evidence_keys = {(r["ticker"], r["fiscal_year"], r["source_family"]) for r in evidence}
    for ticker, payload in state["completed"].items():
        for row in payload["rows"]:
            key = (ticker, row["fiscal_year"], row["available_at"], row["source"])
            if key not in keys:
                consensus.append(row); keys.add(key)
            ekey = (ticker, row["fiscal_year"], "yahoo_finance_analyst_consensus")
            if ekey not in evidence_keys:
                evidence.append({
                    "ticker": ticker, "fiscal_year": row["fiscal_year"],
                    "source_url": f"https://finance.yahoo.com/quote/{payload['symbol']}/analysis/",
                    "source_family": "yahoo_finance_analyst_consensus", "source_tier": "2",
                    "available_at": retrieved_at,
                    "note": f"Yahoo Finance公開分析師共識，{row['analyst_count']}位分析師",
                }); evidence_keys.add(ekey)
    consensus.sort(key=lambda r: (r["ticker"], int(r["fiscal_year"]), r["available_at"], r["source"]))
    evidence.sort(key=lambda r: (r["ticker"], int(r["fiscal_year"]), r["source_family"]))
    _write(Path(consensus_path), CONSENSUS_FIELDS, consensus)
    _write(Path(evidence_path), EVIDENCE_FIELDS, evidence)
    return {"requested_ticker_count": len(allowed), "completed_ticker_count": len(state["completed"]),
            "failed_ticker_count": len(state["failed"]), "failed": state["failed"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire a second public R1 EPS consensus source.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--checkpoint", default="data/r1/consensus/yahoo_checkpoint.json")
    parser.add_argument("--retrieved-at")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tickers = [str(row["ticker"]).zfill(4) for row in config["securities"]]
    markets = {str(row["ticker"]).zfill(4): str(row.get("market", "TWSE")) for row in config["securities"]}
    print(json.dumps(acquire(tickers=tickers, consensus_path=args.consensus,
                             evidence_path=args.evidence, checkpoint_path=args.checkpoint,
                             retrieved_at=args.retrieved_at, market_by_ticker=markets),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
