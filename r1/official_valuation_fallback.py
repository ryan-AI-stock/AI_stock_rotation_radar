from __future__ import annotations

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import statistics
import time

import requests

from .toalpha_valuation import FIELDS, _read_rows, _write_rows


TWSE_URL = "https://www.twse.com.tw/exchangeReport/BWIBBU"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryStock"


def _month_keys(as_of_date: str, years: int = 5) -> list[str]:
    end = date.fromisoformat(as_of_date)
    start_year, start_month = end.year - years, end.month
    keys = []
    year, month = start_year, start_month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def _number(value: object) -> float | None:
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _fetch_month(ticker: str, month: str, *, timeout: int,
                 attempts: int = 4, market: str = "TWSE") -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            url = TPEX_URL if market == "TPEX" else TWSE_URL
            params = ({"date": f"{month[:4]}/{month[4:]}/01", "code": ticker,
                       "response": "json"} if market == "TPEX" else
                      {"date": month + "01", "stockNo": ticker, "response": "json"})
            response = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36"
                    )
                },
            )
            response.raise_for_status()
            if not response.content.strip():
                raise ValueError("twse_empty_response")
            payload = response.json()
            if str(payload.get("stat", "")).upper() != "OK":
                raise ValueError(f"twse_status:{payload.get('stat')}")
            if market == "TPEX":
                table = (payload.get("tables") or [{}])[0]
                return [
                    {"date": row[0], "pe": _number(row[1]), "pb": _number(row[4])}
                    for row in table.get("data", [])
                ]
            return [
                {"date": row[0], "pe": _number(row[3]), "pb": _number(row[4])}
                for row in payload.get("data", [])
            ]
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise ValueError(f"twse_retry_exhausted:{last_error}")


def _percentile(values: list[float], current: float) -> float:
    below = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return (below + 0.5 * equal) / len(values)


def acquire(*, tickers: list[str], as_of_date: str, output_path: str | Path,
            checkpoint_path: str | Path, timeout: int = 30,
            pause_seconds: float = 0.5, market: str = "TWSE") -> dict:
    months = _month_keys(as_of_date)
    checkpoint = Path(checkpoint_path)
    progress = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if not isinstance(progress.get("months"), dict):
        progress = {"as_of_date": as_of_date, "months": {}, "failed": {}}
    elif progress.get("as_of_date") != as_of_date:
        # Historical months are immutable and reusable.  The current month is
        # refreshed because a later weekly date contains additional sessions.
        for ticker_rows in progress["months"].values():
            ticker_rows.pop(months[-1], None)
        progress["as_of_date"] = as_of_date
    progress.setdefault("months", {})
    progress.setdefault("failed", {})
    normalized_tickers = [str(item).zfill(4) for item in tickers]
    allowed = set(normalized_tickers)
    for ticker in normalized_tickers:
        progress["months"].setdefault(ticker, {})
        for month in months:
            if month in progress["months"][ticker]:
                continue
            key = f"{ticker}:{month}"
            try:
                progress["months"][ticker][month] = _fetch_month(
                    ticker, month, timeout=timeout, market=market,
                )
                progress["failed"].pop(key, None)
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                progress["failed"][key] = str(exc)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            time.sleep(pause_seconds)

    generated = []
    incomplete = []
    for ticker in normalized_tickers:
        observations = [
            row for month in months
            for row in progress["months"].get(ticker, {}).get(month, [])
        ]
        pe_values = [row["pe"] for row in observations if row.get("pe") is not None]
        pb_values = [row["pb"] for row in observations if row.get("pb") is not None]
        latest = next((row for row in reversed(observations)
                       if row.get("pe") is not None or row.get("pb") is not None), None)
        metric = None
        values: list[float] = []
        current = None
        if latest and latest.get("pe") is not None and len(pe_values) >= 252:
            metric, values, current = f"TRAILING_PE_{market}_5Y", pe_values, latest["pe"]
        elif latest and latest.get("pb") is not None and len(pb_values) >= 252:
            metric, values, current = f"PRICE_TO_BOOK_{market}_5Y", pb_values, latest["pb"]
        if metric is None or current is None:
            incomplete.append({"ticker": ticker, "pe_observations": len(pe_values),
                               "pb_observations": len(pb_values)})
            continue
        generated.append({
            "ticker": ticker,
            "data_date": as_of_date,
            "next_year_forward_pe": "",
            "five_year_percentile": f"{_percentile(values, current):.8f}",
            "five_year_median_pe": f"{statistics.median(values):.8f}",
            "valuation_metric": metric,
            "current_multiple": f"{current:.8f}",
            "source_url": f"{TPEX_URL}?code={ticker}" if market == "TPEX"
            else f"{TWSE_URL}?stockNo={ticker}",
            "retrieved_at": date.today().isoformat(),
            "quality": "HIGH_OFFICIAL_FALLBACK",
        })
    existing = _read_rows(Path(output_path))
    replacements = {row["ticker"] for row in generated}
    rows = [row for row in existing if not (row.get("ticker") in replacements and
                                             row.get("data_date") == as_of_date)] + generated
    _write_rows(Path(output_path), sorted(rows, key=lambda row: (row["ticker"], row["data_date"])))
    return {
        "requested_ticker_count": len(tickers),
        "completed_ticker_count": len(generated),
        "incomplete": incomplete,
        "failed_month_count": sum(
            key.split(":", 1)[0] in allowed for key in progress["failed"]
        ),
        "metrics": {row["ticker"]: row["valuation_metric"] for row in generated},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="data/r1/valuation_reference.csv")
    parser.add_argument("--checkpoint", default="data/r1/official_valuation_checkpoint.json")
    parser.add_argument("--market", choices=("TWSE", "TPEX"), default="TWSE")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = acquire(tickers=args.tickers.split(","), as_of_date=args.date,
                     output_path=args.output, checkpoint_path=args.checkpoint,
                     market=args.market)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_complete and (result["incomplete"] or result["failed_month_count"]):
        raise SystemExit(75)


if __name__ == "__main__":
    main()
