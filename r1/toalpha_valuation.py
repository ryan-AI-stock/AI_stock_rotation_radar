from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import date
from pathlib import Path

import requests
from curl_cffi import requests as browser_requests

from r1.toalpha_consensus import _get_public_page


FIELDS = (
    "ticker", "data_date", "next_year_forward_pe", "five_year_percentile",
    "five_year_median_pe", "source_url", "retrieved_at", "quality",
)


def parse_valuation_page(text: str, *, ticker: str, source_url: str,
                         retrieved_at: str) -> dict[str, str]:
    """Parse the labelled next-year forward-PE row; absent labels stay missing."""
    clean = html.unescape(re.sub(r"<!--.*?-->", "", text, flags=re.S))
    date_match = re.search(r"<b>(\d{4}-\d{2}-\d{2})</b><span>資料日期</span>", clean)
    if not date_match:
        raise ValueError("source_data_date_missing")
    row_html = next((
        row for row in re.findall(r"<tr[^>]*>(.*?)</tr>", clean, flags=re.S)
        if "前瞻本益比(下年度共識" in row
    ), None)
    if row_html is None:
        raise ValueError("next_year_forward_pe_row_missing")
    cells = [
        re.sub(r"<.*?>", "", cell, flags=re.S).strip()
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.S)
    ]
    if len(cells) < 5:
        raise ValueError("next_year_forward_pe_cells_missing")
    pe_match = re.fullmatch(r"([\d.]+)x", cells[1])
    percentile_match = re.search(r"(\d+)\s*/\s*100", cells[3])
    median_match = re.fullmatch(r"([\d.]+)x", cells[4])
    if not pe_match or not percentile_match or not median_match:
        raise ValueError("next_year_forward_pe_values_missing")
    return {
        "ticker": str(ticker).zfill(4),
        "data_date": date_match.group(1),
        "next_year_forward_pe": pe_match.group(1),
        "five_year_percentile": f"{int(percentile_match.group(1)) / 100:g}",
        "five_year_median_pe": median_match.group(1),
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "quality": "HIGH",
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
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
    progress["completed"] = {k: v for k, v in progress.get("completed", {}).items() if k in allowed}
    progress["failed"] = {k: v for k, v in progress.get("failed", {}).items() if k in allowed}
    for raw_ticker in tickers:
        ticker = str(raw_ticker).zfill(4)
        if ticker in progress["completed"]:
            continue
        url = f"https://toalpha.tw/stock/{ticker}/valuation"
        try:
            response = _get_public_page(url, timeout=timeout)
            text = response.content.decode("utf-8")
            row = parse_valuation_page(
                text, ticker=ticker, source_url=url, retrieved_at=retrieved_at,
            )
            progress["completed"][ticker] = row
            progress["failed"].pop(ticker, None)
        except (requests.RequestException, browser_requests.errors.RequestsError,
                UnicodeDecodeError, ValueError) as exc:
            progress["failed"][ticker] = {"url": url, "error": str(exc)}
        checkpoint.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    existing = _read_rows(Path(output_path))
    by_key = {(row["ticker"], row["data_date"]): row for row in existing}
    for row in progress["completed"].values():
        by_key[(row["ticker"], row["data_date"])] = row
    rows = sorted(by_key.values(), key=lambda row: (row["ticker"], row["data_date"]))
    _write_rows(Path(output_path), rows)
    return {
        "requested_ticker_count": len(allowed),
        "completed_ticker_count": len(progress["completed"]),
        "failed_ticker_count": len(progress["failed"]),
        "failed": progress["failed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire R1 five-year forward-PE references.")
    parser.add_argument("--tickers")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--output", default="data/r1/valuation_reference.csv")
    parser.add_argument("--checkpoint", default="data/r1/valuation_checkpoint.json")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.tickers:
        tickers = [item.strip() for item in args.tickers.split(",") if item.strip()]
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
