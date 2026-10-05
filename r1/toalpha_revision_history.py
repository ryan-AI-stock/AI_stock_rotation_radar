from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import date
from pathlib import Path

import requests

FIELDS = (
    "ticker", "fiscal_year", "source_data_date", "eps_90d", "eps_60d",
    "eps_30d", "eps_current", "revision_30d", "revision_90d", "source_url",
    "available_at", "retrieved_at", "basis", "status",
)


def parse_revision_panel(text: str, *, ticker: str) -> dict[str, str]:
    """Parse the four source-labelled current-year EPS revision observations."""
    clean = html.unescape(re.sub(r"<!--.*?-->", "", text, flags=re.S))
    date_match = re.search(r"<b>(\d{4}-\d{2}-\d{2})</b><span>資料日期</span>", clean)
    if not date_match:
        raise ValueError("source_data_date_missing")
    value_marker = re.search(
        r'font-size:\s*13px;\s*font-weight:\s*600;\s*margin-bottom:\s*4px', clean,
    )
    if not value_marker:
        raise ValueError("revision_panel_anchor_missing")
    heading_start = clean.rfind("<h3", 0, value_marker.start())
    heading_end = clean.find("</h3>", heading_start)
    if heading_start < 0 or heading_end < 0:
        raise ValueError("revision_panel_heading_missing")
    heading = clean[heading_start:heading_end]
    year_match = re.search(r"\b(20\d{2})\b", re.sub(r"<.*?>", " ", heading))
    if not year_match:
        raise ValueError("revision_fiscal_year_missing")
    if not re.search(rf'href=["\']/stock/{re.escape(ticker)}/estimates["\']', heading):
        raise ValueError("revision_estimates_link_missing")
    panel = clean[heading_end + 5:heading_end + 7000]
    values = re.findall(
        r'font-size:\s*13px;\s*font-weight:\s*600;\s*margin-bottom:\s*4px["\']?[^>]*>\s*(-?[\d.]+)\s*</div>',
        panel,
    )
    if len(values) < 4:
        raise ValueError("revision_values_missing")
    eps_90d, eps_60d, eps_30d, eps_current = map(float, values[:4])
    if eps_30d == 0 or eps_90d == 0:
        raise ValueError("revision_base_zero")
    return {
        "ticker": ticker,
        "fiscal_year": year_match.group(1),
        "source_data_date": date_match.group(1),
        "eps_90d": f"{eps_90d:.6g}",
        "eps_60d": f"{eps_60d:.6g}",
        "eps_30d": f"{eps_30d:.6g}",
        "eps_current": f"{eps_current:.6g}",
        "revision_30d": f"{eps_current / eps_30d - 1:.12g}",
        "revision_90d": f"{eps_current / eps_90d - 1:.12g}",
    }


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _upsert(path: Path, incoming: list[dict[str, str]]) -> None:
    rows = _read(path)
    keys = {(row["ticker"], row["source_data_date"]) for row in rows}
    for row in incoming:
        key = (row["ticker"], row["source_data_date"])
        if key not in keys:
            rows.append(row)
            keys.add(key)
    rows.sort(key=lambda row: (row["source_data_date"], row["ticker"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def acquire(*, tickers: list[str], output_path: str | Path, checkpoint_path: str | Path,
            retrieved_at: str | None = None, timeout: int = 30) -> dict:
    retrieved_at = retrieved_at or date.today().isoformat()
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    progress = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if progress.get("retrieved_at") != retrieved_at:
        progress = {"retrieved_at": retrieved_at, "completed": {}, "failed": {}}
    allowed = {str(ticker).zfill(4) for ticker in tickers}
    progress["completed"] = {
        ticker: value for ticker, value in progress.get("completed", {}).items() if ticker in allowed
    }
    progress["failed"] = {
        ticker: value for ticker, value in progress.get("failed", {}).items() if ticker in allowed
    }
    for ticker in tickers:
        if ticker in progress["completed"]:
            continue
        main_url = f"https://toalpha.tw/stock/{ticker}"
        try:
            headers = {"User-Agent": "Mozilla/5.0 R1 research"}
            response = requests.get(main_url, timeout=timeout, headers=headers)
            response.raise_for_status()
            row = parse_revision_panel(response.text, ticker=ticker)
            source_data_date = row["source_data_date"]
            row.update({
                "source_data_date": source_data_date,
                "source_url": main_url,
                "available_at": source_data_date,
                "retrieved_at": retrieved_at,
                "basis": "SOURCE_REPORTED_OFFSETS",
                "status": "SUPPLEMENTAL_NOT_TOTAL_SCORE",
            })
            progress["completed"][ticker] = row
            progress["failed"].pop(ticker, None)
        except (requests.RequestException, ValueError) as exc:
            progress["failed"][ticker] = {"url": main_url, "error": str(exc)}
        checkpoint.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _upsert(Path(output_path), list(progress["completed"].values()))
    return {
        "requested_ticker_count": len(tickers),
        "completed_ticker_count": len(progress["completed"]),
        "failed_ticker_count": len(progress["failed"]),
        "failed": progress["failed"],
    }


def latest_rows(path: str | Path, *, as_of_date: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in _read(Path(path)):
        if row["available_at"] <= as_of_date:
            current = result.get(row["ticker"])
            if current is None or current["available_at"] < row["available_at"]:
                result[row["ticker"]] = row
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire public current-year EPS revision history.")
    parser.add_argument("--tickers")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output", default="data/r1/consensus/current_year_revision_history.csv")
    parser.add_argument("--checkpoint", default="data/r1/consensus/toalpha_revision_checkpoint.json")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.tickers:
        tickers = [item.strip().zfill(4) for item in args.tickers.split(",") if item.strip()]
    else:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        tickers = [str(row["ticker"]).zfill(4) for row in config["securities"]]
    result = acquire(
        tickers=tickers, output_path=args.output, checkpoint_path=args.checkpoint,
        retrieved_at=args.retrieved_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_complete and result["failed_ticker_count"]:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
