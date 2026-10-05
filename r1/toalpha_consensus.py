from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import date
from pathlib import Path

import requests


CONSENSUS_FIELDS = (
    "ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps",
    "analyst_count", "source", "published_at", "available_at", "retrieved_at",
    "quality", "status",
)
EVIDENCE_FIELDS = (
    "ticker", "fiscal_year", "source_url", "source_family", "source_tier",
    "available_at", "note",
)


def required_fiscal_years(as_of_date: str) -> set[str]:
    """R1 needs current and next-year EPS; the second forward year is optional."""
    year = int(as_of_date[:4])
    return {str(year), str(year + 1)}


def _prune_progress(progress: dict, tickers: list[str]) -> dict:
    allowed = {str(ticker).zfill(4) for ticker in tickers}
    progress["completed"] = {
        ticker: value for ticker, value in progress.get("completed", {}).items() if ticker in allowed
    }
    progress["failed"] = {
        ticker: value for ticker, value in progress.get("failed", {}).items() if ticker in allowed
    }
    return progress


def parse_estimates_page(text: str, *, ticker: str, retrieved_at: str) -> list[dict[str, str]]:
    """Parse only the labelled forward-estimate table; never infer absent values."""
    clean = html.unescape(re.sub(r"<!--.*?-->", "", text, flags=re.S))
    date_match = re.search(r"<b>(\d{4}-\d{2}-\d{2})</b><span>資料日期</span>", clean)
    if not date_match:
        raise ValueError("source_data_date_missing")
    available_at = date_match.group(1)
    table_match = re.search(r"<h2>前瞻估值.*?<tbody>(.*?)</tbody>", clean, flags=re.S)
    if not table_match:
        raise ValueError("forward_valuation_table_missing")
    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", table_match.group(1), flags=re.S):
        cells = [re.sub(r"<.*?>", "", cell).strip() for cell in re.findall(r"<td.*?>(.*?)</td>", row_html, flags=re.S)]
        if len(cells) != 8 or not re.fullmatch(r"\d{4}E", cells[0]):
            continue
        fiscal_year = cells[0][:4]
        mean_eps = cells[1]
        analysts = cells[5]
        bounds = re.fullmatch(r"(-?[\d.]+)\s*/\s*(-?[\d.]+)", cells[7])
        if not bounds:
            continue
        high_eps, low_eps = bounds.groups()
        rows.append({
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "mean_eps": mean_eps,
            "median_eps": mean_eps,
            "high_eps": high_eps,
            "low_eps": low_eps,
            "analyst_count": analysts,
            "source": "ToAlpha public consensus",
            "published_at": available_at,
            "available_at": available_at,
            "retrieved_at": retrieved_at,
            "quality": "MEDIUM",
            "status": "READY",
        })
    if not rows:
        raise ValueError("forward_estimate_rows_missing")
    return rows


def parse_eps_page(text: str, *, ticker: str, retrieved_at: str) -> list[dict[str, str]]:
    """Fallback for estimates omitted from the valuation table when coverage is below three analysts."""
    clean = html.unescape(re.sub(r"<!--.*?-->", "", text, flags=re.S))
    date_match = re.search(r"<b>(\d{4}-\d{2}-\d{2})</b><span>資料日期</span>", clean)
    if not date_match:
        raise ValueError("source_data_date_missing")
    rows: list[dict[str, str]] = []
    for match in re.finditer(
        r'<tr class="fcrow"><td><b>(\d{4})</b><small>\s*預估\s*(\d+)\s*家</small></td>'
        r'<td><b>(-?[\d.]+)</b></td>', clean,
    ):
        fiscal_year, analysts, mean_eps = match.groups()
        rows.append({
            "ticker": ticker, "fiscal_year": fiscal_year, "mean_eps": mean_eps,
            "median_eps": mean_eps, "high_eps": "", "low_eps": "",
            "analyst_count": analysts, "source": "ToAlpha public consensus",
            "published_at": date_match.group(1), "available_at": date_match.group(1),
            "retrieved_at": retrieved_at, "quality": "MEDIUM", "status": "READY",
        })
    if not rows:
        raise ValueError("annual_eps_estimate_rows_missing")
    return rows


def acquire(*, tickers: list[str], consensus_path: str | Path, evidence_path: str | Path,
            checkpoint_path: str | Path, retrieved_at: str | None = None,
            timeout: int = 30) -> dict:
    retrieved_at = retrieved_at or date.today().isoformat()
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    progress = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
        "retrieved_at": retrieved_at, "completed": {}, "failed": {},
    }
    if progress.get("retrieved_at") != retrieved_at:
        progress = {"retrieved_at": retrieved_at, "completed": {}, "failed": {}}
    progress = _prune_progress(progress, tickers)
    for ticker in tickers:
        expected_years = required_fiscal_years(retrieved_at)
        completed_years = {
            row["fiscal_year"] for row in progress["completed"].get(ticker, {}).get("rows", [])
        }
        if expected_years.issubset(completed_years):
            continue
        url = f"https://toalpha.tw/stock/{ticker}/estimates"
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 R1 research"})
            response.raise_for_status()
            try:
                rows = parse_estimates_page(response.text, ticker=ticker, retrieved_at=retrieved_at)
            except ValueError:
                rows = []
            eps_response = requests.get(
                f"https://toalpha.tw/stock/{ticker}/eps", timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 R1 research"},
            )
            eps_response.raise_for_status()
            fallback = parse_eps_page(eps_response.text, ticker=ticker, retrieved_at=retrieved_at)
            by_year = {row["fiscal_year"]: row for row in fallback}
            by_year.update({row["fiscal_year"]: row for row in rows})
            rows = sorted(by_year.values(), key=lambda row: row["fiscal_year"])
            missing_years = sorted(expected_years - set(by_year))
            if missing_years:
                raise ValueError("missing_fiscal_years:" + ",".join(missing_years))
            progress["completed"][ticker] = {"url": url, "rows": rows}
            progress["failed"].pop(ticker, None)
        except (requests.RequestException, ValueError) as exc:
            progress["failed"][ticker] = {"url": url, "error": str(exc)}
        checkpoint.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _upsert_missing(progress, Path(consensus_path), Path(evidence_path))
    return {
        "requested_ticker_count": len(tickers),
        "completed_ticker_count": len(progress["completed"]),
        "failed_ticker_count": len(progress["failed"]),
        "failed": progress["failed"],
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def _upsert_missing(progress: dict, consensus_path: Path, evidence_path: Path) -> None:
    consensus = _read_csv(consensus_path)
    existing = {
        (row["ticker"], row["fiscal_year"], row["available_at"], row["source"])
        for row in consensus
    }
    evidence = _read_csv(evidence_path)
    existing_evidence = {
        (row["ticker"], row["fiscal_year"], row["source_family"]) for row in evidence
    }
    for ticker, payload in progress["completed"].items():
        for row in payload["rows"]:
            key = (ticker, row["fiscal_year"], row["available_at"], row["source"])
            if key not in existing:
                consensus.append(row)
                existing.add(key)
            evidence_key = (ticker, row["fiscal_year"], "toalpha_consensus")
            if evidence_key not in existing_evidence:
                evidence.append({
                    "ticker": ticker,
                    "fiscal_year": row["fiscal_year"],
                    "source_url": payload["url"],
                    "source_family": "toalpha_consensus",
                    "source_tier": "2",
                    "available_at": row["available_at"],
                    "note": f"{row['analyst_count']}家共識平均{row['mean_eps']}；單一來源，不單獨形成可交易共識",
                })
                existing_evidence.add(evidence_key)
    consensus.sort(key=lambda row: (row["ticker"], int(row["fiscal_year"]), row["available_at"], row["source"]))
    evidence.sort(key=lambda row: (row["ticker"], int(row["fiscal_year"]), row["source_family"]))
    _write_csv(consensus_path, CONSENSUS_FIELDS, consensus)
    _write_csv(evidence_path, EVIDENCE_FIELDS, evidence)


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire public R1 EPS consensus with resumable checkpointing.")
    parser.add_argument("--tickers", help="Comma-separated tickers")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--consensus", default="data/r1/consensus/consensus.csv")
    parser.add_argument("--evidence", default="data/r1/consensus/evidence.csv")
    parser.add_argument("--checkpoint", default="data/r1/consensus/toalpha_checkpoint.json")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.tickers:
        tickers = [item.strip() for item in args.tickers.split(",") if item.strip()]
    else:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        tickers = [str(row["ticker"]).zfill(4) for row in config["securities"]]
    result = acquire(
        tickers=tickers,
        consensus_path=args.consensus, evidence_path=args.evidence,
        checkpoint_path=args.checkpoint, retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_complete and result["failed_ticker_count"]:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
