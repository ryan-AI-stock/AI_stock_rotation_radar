from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from r1.config import R1Config


BASE_URL = "https://hk.investing.com"
FIELDS = (
    "ticker", "institution", "target_price", "horizon", "available_at",
    "source_url", "retrieved_at", "note",
)


def _get(url: str, *, timeout: int = 30, attempts: int = 2) -> str:
    from curl_cffi import requests as curl_requests

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = curl_requests.get(url, impersonate="chrome", timeout=timeout)
            response.raise_for_status()
            return response.content.decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                sleep(5 * attempt)
    assert last_error is not None
    raise last_error


def resolve_equity_path(html: str, *, ticker: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select("a.js-inner-all-results-quote-item"):
        symbol = item.select_one("span.second")
        href = item.get("href")
        if symbol and symbol.get_text(strip=True) == ticker and href and "/equities/" in href:
            return str(href).split("?", 1)[0]
    return None


def _parse_date(value: str) -> str | None:
    match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", value)
    if not match:
        return None
    year, month, day = (int(item) for item in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_ratings(html: str, *, ticker: str, source_url: str, retrieved_at: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for tr in soup.select("tbody tr"):
        cells = tr.select("td")
        if len(cells) < 8:
            continue
        institution = cells[0].get_text(" ", strip=True)
        price_text = cells[3].get_text(" ", strip=True).replace(",", "")
        upside_text = cells[4].get_text(" ", strip=True)
        available_at = _parse_date(cells[-1].get_text(" ", strip=True))
        try:
            target_price = float(price_text)
        except ValueError:
            continue
        if (not institution or not re.search(r"[A-Za-z]", institution)
                or "%" not in upside_text or not available_at or target_price <= 0):
            continue
        rows.append({
            "ticker": ticker,
            "institution": institution,
            "target_price": f"{target_price:g}",
            "horizon": "12M",
            "available_at": available_at,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "note": "公開分析師評級表；機構可識別；自動擷取",
        })
    return rows


def _load_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{field: str(row.get(field, "")) for field in FIELDS} for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _merge_rows(existing: list[dict[str, str]], added: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in existing + added:
        key = (row["ticker"], row["institution"], row["available_at"], row["target_price"])
        merged[key] = row
    return sorted(merged.values(), key=lambda row: (
        row["ticker"], row["available_at"], row["institution"], row["target_price"],
    ))


def _reusable_consensus(rows: list[dict[str, str]], *, ticker: str,
                        retrieved_at: str, refresh_after_days: int = 28) -> bool:
    """Preserve request capacity for source gaps instead of refetching fresh winners.

    Reuse is only an acquisition optimization.  The downstream snapshot still
    enforces the 90-day PIT window and three identifiable institutions.
    """
    asof = date.fromisoformat(retrieved_at[:10])
    retrieved_cutoff = asof - timedelta(days=refresh_after_days - 1)
    target_cutoff = asof - timedelta(days=90)
    institutions = {
        row["institution"].strip()
        for row in rows
        if row.get("ticker") == ticker
        and row.get("institution", "").strip()
        and row.get("retrieved_at", "")[:10] >= retrieved_cutoff.isoformat()
        and target_cutoff.isoformat() <= row.get("available_at", "")[:10] <= asof.isoformat()
    }
    return len(institutions) >= 3


def acquire(*, config_path: str | Path, evidence_path: str | Path,
            checkpoint_path: str | Path, retrieved_at: str,
            pause_seconds: float = 0.5) -> dict[str, Any]:
    config = R1Config.load(config_path)
    evidence = Path(evidence_path)
    checkpoint = Path(checkpoint_path)
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {"completed": {}}
    completed = state.setdefault("completed", {})
    existing = _load_existing(evidence)
    added: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    securities = list(config.securities)
    start_index = int(state.get("next_index", 0)) % len(securities)
    ordered_securities = securities[start_index:] + securities[:start_index]
    consecutive_forbidden = 0
    circuit_breaker_tripped = False
    attempted_count = 0
    for offset, security in enumerate(ordered_securities):
        ticker = security.ticker
        if _reusable_consensus(existing, ticker=ticker, retrieved_at=retrieved_at):
            completed[ticker] = {
                "retrieved_at": retrieved_at, "row_count": 0,
                "status": "REUSED_READY",
                "note": "three or more identifiable institutions remain fresh; request capacity reserved for source gaps",
            }
            continue
        if (completed.get(ticker, {}).get("retrieved_at") == retrieved_at
                and completed.get(ticker, {}).get("status") == "READY"):
            continue
        try:
            attempted_count += 1
            search_html = _get(f"{BASE_URL}/search/?q={ticker}")
            equity_path = resolve_equity_path(search_html, ticker=ticker)
            if not equity_path:
                raise ValueError("taiwan_equity_search_result_missing")
            source_url = urljoin(BASE_URL, equity_path.rstrip("/") + "-consensus-estimates")
            page = _get(source_url)
            ticker_rows = parse_ratings(
                page, ticker=ticker, source_url=source_url, retrieved_at=retrieved_at,
            )
            if not ticker_rows:
                source_url = urljoin(BASE_URL, equity_path)
                ticker_rows = parse_ratings(
                    _get(source_url), ticker=ticker, source_url=source_url, retrieved_at=retrieved_at,
                )
            if not ticker_rows:
                raise ValueError("identifiable_analyst_target_rows_missing")
            added.extend(ticker_rows)
            existing = _merge_rows(existing, ticker_rows)
            _write_rows(evidence, existing)
            completed[ticker] = {
                "retrieved_at": retrieved_at, "source_url": source_url,
                "row_count": len(ticker_rows), "status": "READY",
            }
            consecutive_forbidden = 0
        except Exception as exc:  # source failures are checkpointed and retried next run
            failures[ticker] = f"{type(exc).__name__}:{exc}"
            completed[ticker] = {
                "retrieved_at": retrieved_at, "row_count": 0,
                "status": "SOURCE_GAP", "error": failures[ticker],
            }
            if "403" in failures[ticker]:
                consecutive_forbidden += 1
            else:
                consecutive_forbidden = 0
            if consecutive_forbidden >= 3:
                circuit_breaker_tripped = True
                state["next_index"] = (start_index + offset + 1) % len(securities)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if circuit_breaker_tripped:
            break
        if pause_seconds:
            sleep(pause_seconds)
    if not circuit_breaker_tripped:
        state["next_index"] = 0
    ordered = _merge_rows(existing, [])
    _write_rows(evidence, ordered)
    payload = {
        "retrieved_at": retrieved_at,
        "requested_ticker_count": len(config.securities),
        "ready_ticker_count": sum(
            item.get("retrieved_at") == retrieved_at
            and item.get("status") in {"READY", "REUSED_READY"}
            for item in completed.values()
        ),
        "reused_ready_ticker_count": sum(
            item.get("retrieved_at") == retrieved_at and item.get("status") == "REUSED_READY"
            for item in completed.values()
        ),
        "source_gap_ticker_count": len(failures),
        "new_evidence_row_count": len(added),
        "total_evidence_row_count": len(ordered),
        "attempted_ticker_count": attempted_count,
        "circuit_breaker_tripped": circuit_breaker_tripped,
        "next_index": state.get("next_index", 0),
        "failures": failures,
    }
    state["last_summary"] = payload
    checkpoint.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire identifiable public 12M analyst target prices.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--evidence", default="data/r1/target_prices/evidence.csv")
    parser.add_argument("--checkpoint", default="data/r1/target_prices/investing_checkpoint.json")
    parser.add_argument("--retrieved-at", default=date.today().isoformat())
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    args = parser.parse_args()
    result = acquire(
        config_path=args.config, evidence_path=args.evidence,
        checkpoint_path=args.checkpoint, retrieved_at=args.retrieved_at,
        pause_seconds=args.pause_seconds,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
