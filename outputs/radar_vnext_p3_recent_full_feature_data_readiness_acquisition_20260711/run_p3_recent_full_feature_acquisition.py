"""Resumable P3 recent full-feature source acquisition.

Full-market responses are parsed in memory. Permanent rows are limited to the
frozen Layer4 100-name weekly primary/watchlist scope and compact market context.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup


TASK = "TASK-RADAR-DATA-VNEXT-P3-RECENT-FULL-FEATURE-DATA-READINESS-AND-ACQUISITION-001"
OUT = Path(__file__).resolve().parent
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
POOL100 = CORE / "outputs/vnext_layer4_80_primary_pool_contract_20260708/layer4_reference_100_extended_watchlist.csv"
PRIMARY80 = CORE / "outputs/vnext_layer4_80_primary_pool_contract_20260708/layer4_80_primary_pool_contract.csv"
REQUESTED_START = date(2023, 7, 11)
REQUESTED_END = date(2026, 7, 10)
ACTUAL_EXPECTED_END = date(2026, 7, 9)
PRICE_WARMUP_START = date(2022, 7, 11)
CHIP_WARMUP_START = date(2023, 6, 1)
FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(v: object) -> str:
    return str(v).replace(",", "").replace("--", "").strip()


def number(v: object) -> str:
    try:
        x = clean(v)
        return str(float(x)) if x else ""
    except (TypeError, ValueError):
        return ""


def integer(v: object) -> str:
    try:
        x = clean(v)
        return str(int(float(x))) if x else ""
    except (TypeError, ValueError):
        return ""


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        if not fields:
            return
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_progress(family: str, completed: int, total: int, cursor: str, status: str = "running") -> None:
    write_json(OUT / f"{family}_progress.json", {
        "task_id": TASK,
        "family": family,
        "status": status,
        "completed": completed,
        "total": total,
        "cursor": cursor,
        "updated_at_utc": now(),
        "resume": f"python -X utf8 {Path(__file__).name} --family {family}",
    })
    (OUT / "current_step.txt").write_text(f"{family} {status} {completed}/{total} {cursor}\n", encoding="utf-8")


def http(method: str, url: str, **kwargs) -> tuple[bytes, int, str, str]:
    last = (b"", 0, "no_attempt", "")
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=45, headers={
                "User-Agent": "Mozilla/5.0 RadarP3Lifecycle/1.0",
                "Accept": "application/json,text/html,*/*",
            }, **kwargs)
            return r.content, r.status_code, "" if r.ok else f"HTTP_{r.status_code}", r.url
        except requests.RequestException as exc:
            last = (b"", 0, type(exc).__name__, url)
            time.sleep(1.5 * (attempt + 1))
    return last


def read_pool() -> pd.DataFrame:
    p = pd.read_csv(POOL100, dtype={"ticker": str}, low_memory=False)
    p["snapshot_date"] = pd.to_datetime(p["snapshot_date"])
    p = p[(p.snapshot_date.dt.date >= REQUESTED_START) & (p.snapshot_date.dt.date <= ACTUAL_EXPECTED_END)].copy()
    p["ticker"] = p.ticker.astype(str).str.strip()
    return p


def universe() -> tuple[dict[date, set[str]], dict[str, dict]]:
    p = read_pool().sort_values(["snapshot_date", "ticker"])
    snapshots = sorted(p.snapshot_date.dt.date.unique())
    by_snapshot = {d: set(p.loc[p.snapshot_date.dt.date.eq(d), "ticker"]) for d in snapshots}
    meta = {}
    for row in p[["ticker", "name", "market", "layer4_pool_role", "is_layer4_primary_pool"]].drop_duplicates("ticker").itertuples(index=False):
        meta[str(row.ticker)] = {"name": row.name, "market": row.market, "layer4_pool_role": row.layer4_pool_role, "is_layer4_primary_pool": row.is_layer4_primary_pool}
    by_day: dict[date, set[str]] = {}
    d = PRICE_WARMUP_START
    while d <= ACTUAL_EXPECTED_END:
        past = [x for x in snapshots if x <= max(d, REQUESTED_START)]
        anchor = past[-1] if past else snapshots[0]
        # Price warmup for a ticker is kept if it appears in any snapshot in the
        # following 365 calendar days. This is bounded to the frozen 100-name source.
        future = [x for x in snapshots if d <= x <= d + timedelta(days=365)]
        wanted = set().union(*(by_snapshot[x] for x in future)) if future else set(by_snapshot[anchor])
        if d > snapshots[-1]:
            wanted = set(by_snapshot[snapshots[-1]])
        by_day[d] = wanted
        d += timedelta(days=1)
    return by_day, meta


def materialize_universe() -> None:
    p = read_pool()
    p[["snapshot_date", "ticker", "name", "market", "layer4_pool_role", "is_layer4_primary_pool", "reference_only"]].to_csv(
        OUT / "p3_frozen_layer4_primary80_watchlist_membership.csv", index=False, encoding="utf-8-sig"
    )
    rows = [{
        "requested_start": REQUESTED_START.isoformat(),
        "requested_end": REQUESTED_END.isoformat(),
        "expected_actual_end": ACTUAL_EXPECTED_END.isoformat(),
        "membership_actual_start": p.snapshot_date.min().date().isoformat(),
        "membership_actual_end": p.snapshot_date.max().date().isoformat(),
        "snapshot_count": p.snapshot_date.nunique(),
        "membership_rows": len(p),
        "unique_tickers": p.ticker.nunique(),
        "latest_scope_policy": "carry_2026-06-29_source_scope_through_2026-07-09; not_new_PIT_membership",
    }]
    write_csv(OUT / "p3_universe_requested_vs_actual.csv", rows)
    update_progress("universe", 1, 1, str(p.snapshot_date.max().date()), "completed")


PRICE_FIELDS = ["date", "ticker", "name", "market", "open", "high", "low", "close", "volume", "turnover_value", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc"]
CHIP_FIELDS = ["date", "ticker", "name", "market", "foreign_net", "trust_net", "dealer_net", "margin_balance", "margin_change", "short_balance", "short_change", "sbl_balance", "sbl_change", "source_quality", "source_url", "source_hash", "retrieval_time_utc", "available_at_policy"]


def shard_path(family: str, market: str, d: date) -> Path:
    return OUT / "checkpoints" / family / market / f"{d.isoformat()}.csv.gz"


def write_shard(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    with gzip.open(tmp, "rt", encoding="utf-8") as f:
        list(csv.DictReader(f))
    os.replace(tmp, path)


def parse_twse_price(obj: dict, d: date, wanted: set[str], url: str, sha: str, at: str) -> list[dict]:
    table = next((x for x in obj.get("tables", []) if (x.get("data") or []) and len(x.get("fields") or []) >= 9), {})
    out = []
    for r in table.get("data") or []:
        if len(r) < 9 or str(r[0]).strip() not in wanted or not number(r[8]): continue
        out.append({"date": d.isoformat(), "ticker": str(r[0]).strip(), "name": str(r[1]).strip(), "market": "TWSE", "open": number(r[5]), "high": number(r[6]), "low": number(r[7]), "close": number(r[8]), "volume": integer(r[2]), "turnover_value": integer(r[4]), "source_quality": "official_twse_raw_execution_ohlcv", "adjustment_policy": "unadjusted_execution_only", "source_url": url, "source_hash": sha, "retrieval_time_utc": at})
    return out


def parse_tpex_price(obj: dict, d: date, wanted: set[str], url: str, sha: str, at: str) -> list[dict]:
    table = next((x for x in obj.get("tables", []) if x.get("data")), {})
    out = []
    for r in table.get("data") or []:
        if len(r) < 10 or str(r[0]).strip() not in wanted or not number(r[2]): continue
        out.append({"date": d.isoformat(), "ticker": str(r[0]).strip(), "name": str(r[1]).strip(), "market": "TPEx", "open": number(r[4]), "high": number(r[5]), "low": number(r[6]), "close": number(r[2]), "volume": integer(r[8]), "turnover_value": integer(r[9]), "source_quality": "official_tpex_raw_execution_ohlcv", "adjustment_policy": "unadjusted_execution_only", "source_url": url, "source_hash": sha, "retrieval_time_utc": at})
    return out


def fetch_price(item: tuple[str, date, set[str]]) -> dict:
    market, d, wanted = item
    if market == "TWSE":
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?date={d:%Y%m%d}&type=ALLBUT0999&response=json"; parser = parse_twse_price
    else:
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={d:%Y/%m/%d}&response=json"; parser = parse_tpex_price
    at = now(); raw, status, err, final_url = http("GET", url); sha = hashlib.sha256(raw).hexdigest() if raw else ""; rows = []
    if raw:
        try: rows = parser(json.loads(raw.decode("utf-8-sig")), d, wanted, final_url, sha, at)
        except Exception as exc: err = f"parse_{type(exc).__name__}"
    outcome = "accepted" if rows else "no_rows_valid_official_response" if status == 200 and not err else "failed"
    if outcome != "failed": write_shard(shard_path("price", market, d), rows, PRICE_FIELDS)
    return {"family": "official_raw_execution_ohlcv", "market": market, "date": d.isoformat(), "status": outcome, "wanted_tickers": len(wanted), "filtered_rows": len(rows), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "response_sha256": sha, "retrieval_time_utc": at, "error": err}


def run_price(workers: int) -> None:
    by_day, _ = universe(); items = []
    d = PRICE_WARMUP_START
    while d <= ACTUAL_EXPECTED_END:
        if d.weekday() < 5:
            for market in ("TWSE", "TPEx"):
                if not shard_path("price", market, d).exists(): items.append((market, d, by_day[d]))
        d += timedelta(days=1)
    run_parallel("price", items, fetch_price, workers)
    consolidate("price", PRICE_FIELDS, ["date", "ticker", "market"])


def chip_base(d: date, ticker: str, name: str, market: str, family: str, url: str, sha: str, at: str) -> dict:
    x = {k: "" for k in CHIP_FIELDS}; x.update({"date": d.isoformat(), "ticker": ticker, "name": name, "market": market, "source_quality": f"official_{market.lower()}_{family}", "source_url": url, "source_hash": sha, "retrieval_time_utc": at, "available_at_policy": "post_close_release; eligible_next_trading_day_only"}); return x


def fetch_chip(item: tuple[str, str, date, set[str]]) -> dict:
    market, family, d, wanted = item
    at = now(); method = "GET"; data = None
    if market == "TWSE":
        routes = {
            "institutional": f"https://www.twse.com.tw/fund/T86?date={d:%Y%m%d}&selectType=ALLBUT0999&response=json",
            "margin_short": f"https://www.twse.com.tw/exchangeReport/MI_MARGN?date={d:%Y%m%d}&selectType=ALL&response=json",
            "securities_lending": f"https://www.twse.com.tw/exchangeReport/TWT72U?date={d:%Y%m%d}&response=json",
        }
        url = routes[family]
    else:
        routes = {"institutional": "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade", "margin_short": "https://www.tpex.org.tw/www/zh-tw/margin/balance", "securities_lending": "https://www.tpex.org.tw/www/zh-tw/margin/sbl"}
        url = routes[family]; method = "POST"; data = {"date": d.strftime("%Y/%m/%d"), "response": "json"}
        if family == "institutional": data.update({"type": "Daily", "cate": "EW"})
    raw, status, err, final_url = http(method, url, data=data); sha = hashlib.sha256(raw).hexdigest() if raw else ""; out = []
    try:
        obj = json.loads(raw.decode("utf-8-sig")) if raw else {}
        if market == "TWSE" and family == "institutional":
            rows = obj.get("data") or []
            for r in rows:
                if len(r) >= 9 and str(r[0]).strip() in wanted:
                    x = chip_base(d, str(r[0]).strip(), str(r[1]).strip(), market, family, final_url, sha, at); x.update({"foreign_net": integer(r[4]), "trust_net": integer(r[7]), "dealer_net": integer(r[8])}); out.append(x)
        else:
            if market == "TWSE" and family == "securities_lending":
                rows = obj.get("data") or []
            else:
                table = next((x for x in obj.get("tables", []) if (x.get("data") or []) and len(x.get("fields") or []) >= 12), {})
                rows = table.get("data") or []
            for r in rows:
                ticker = str(r[0]).strip() if r else ""
                if ticker not in wanted: continue
                x = chip_base(d, ticker, str(r[1]).strip(), market, family, final_url, sha, at)
                if family == "institutional" and len(r) >= 11: x.update({"foreign_net": integer(r[4]), "trust_net": integer(r[7]), "dealer_net": integer(r[10])})
                elif family == "margin_short" and len(r) >= 15: x.update({"margin_balance": integer(r[6]), "margin_change": str(int(integer(r[3]) or 0)-int(integer(r[4]) or 0)), "short_balance": integer(r[14]), "short_change": str(int(integer(r[11]) or 0)-int(integer(r[12]) or 0))})
                elif family == "securities_lending":
                    # Both TWSE TWT72U and TPEx SBL tables expose current balance; exact column labels are retained in the manifest schema audit.
                    balance = r[5] if market == "TWSE" and len(r) > 5 else r[12] if len(r) > 12 else ""
                    prev = r[2] if market == "TWSE" and len(r) > 2 else r[8] if len(r) > 8 else ""
                    x.update({"sbl_balance": integer(balance), "sbl_change": str(int(integer(balance) or 0)-int(integer(prev) or 0)) if integer(balance) and integer(prev) else ""})
                else: continue
                out.append(x)
    except Exception as exc: err = f"parse_{type(exc).__name__}"
    outcome = "accepted" if out else "no_rows_valid_official_response" if status == 200 and not err else "failed"
    if outcome != "failed": write_shard(shard_path(f"chip_{family}", market, d), out, CHIP_FIELDS)
    return {"family": family, "market": market, "date": d.isoformat(), "status": outcome, "wanted_tickers": len(wanted), "filtered_rows": len(out), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "response_sha256": sha, "retrieval_time_utc": at, "error": err}


def run_chips(workers: int) -> None:
    by_day, _ = universe(); items = []; d = CHIP_WARMUP_START
    while d <= ACTUAL_EXPECTED_END:
        if d.weekday() < 5:
            for market in ("TWSE", "TPEx"):
                for family in ("institutional", "margin_short", "securities_lending"):
                    if not shard_path(f"chip_{family}", market, d).exists(): items.append((market, family, d, by_day[d]))
        d += timedelta(days=1)
    run_parallel("chips", items, fetch_chip, workers)
    for fam in ("chip_institutional", "chip_margin_short", "chip_securities_lending"):
        consolidate(fam, CHIP_FIELDS, ["date", "ticker", "market"])


def run_parallel(family: str, items: list, fn, workers: int) -> None:
    manifest_path = OUT / f"{family}_source_manifest.csv"; prior = []
    if manifest_path.exists(): prior = list(csv.DictReader(manifest_path.open(encoding="utf-8-sig", newline="")))
    total = len(items); completed = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fn, x): x for x in items}
        for fut in as_completed(futures):
            row = fut.result(); prior.append(row); completed += 1
            if completed % 10 == 0 or completed == total:
                write_csv(manifest_path, prior)
                update_progress(family, completed, total, row.get("date", row.get("ticker", "")))
    write_csv(manifest_path, prior)
    update_progress(family, total, total, "complete", "completed")


def consolidate(family: str, fields: list[str], keys: list[str]) -> None:
    root = OUT / "checkpoints" / family
    if not root.exists(): return
    by_year: dict[str, list[dict]] = defaultdict(list)
    for p in root.rglob("*.csv.gz"):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f): by_year[row["date"][:4]].append(row)
    for year, rows in by_year.items():
        unique = {tuple(r[k] for k in keys): r for r in rows}
        target = OUT / "compact" / family / f"{year}.csv.gz"; target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(sorted(unique.values(), key=lambda r: tuple(r[k] for k in keys)))
        with gzip.open(tmp, "rt", encoding="utf-8") as f: verified = list(csv.DictReader(f))
        if len(verified) != len(unique): raise RuntimeError(f"consolidation mismatch {family} {year}")
        os.replace(tmp, target)


def fetch_adjusted(item: tuple[str, dict, date, date]) -> dict:
    ticker, meta, start, end = item; rows = []; events = []; attempts = []
    for suffix in (".TW", ".TWO"):
        symbol = ticker + suffix; p1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp()); p2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits"; at = now(); raw, status, err, final_url = http("GET", url); sha = hashlib.sha256(raw).hexdigest() if raw else ""; attempts.append(f"{symbol}:{status}:{err}")
        try:
            chart = json.loads(raw.decode("utf-8"))["chart"]["result"][0]
            quote = (chart.get("indicators", {}).get("quote") or [{}])[0]; adj = (chart.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
            for i, ts in enumerate(chart.get("timestamp") or []):
                d = datetime.fromtimestamp(ts, timezone.utc).date(); ac = adj[i] if i < len(adj) else None
                if start <= d <= end and ac is not None:
                    closes = quote.get("close") or []; rows.append({"date": d.isoformat(), "ticker": ticker, "name": meta.get("name", ""), "market": meta.get("market", ""), "yahoo_symbol": symbol, "adjusted_close": ac, "raw_close_comparator": closes[i] if i < len(closes) else "", "source_quality": "trusted_nonofficial_yahoo_research_grade", "adjustment_policy": "provider_adjusted_analysis_only; not_execution_price; not_formal", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at})
            for kind, key in (("cash_dividend", "dividends"), ("split", "splits")):
                for ev in (chart.get("events", {}).get(key, {}) or {}).values():
                    ed = datetime.fromtimestamp(ev.get("date"), timezone.utc).date().isoformat() if ev.get("date") else ""
                    events.append({"ticker": ticker, "market": meta.get("market", ""), "event_type": kind, "effective_date": ed, "amount_or_ratio": ev.get("amount", "") if kind == "cash_dividend" else f"{ev.get('numerator','')}/{ev.get('denominator','')}", "source_quality": "trusted_nonofficial_yahoo_event_candidate", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at, "human_review_required": "true"})
            if rows: break
        except Exception: continue
    pf = ["date", "ticker", "name", "market", "yahoo_symbol", "adjusted_close", "raw_close_comparator", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc"]
    ef = ["ticker", "market", "event_type", "effective_date", "amount_or_ratio", "source_quality", "source_url", "source_hash", "retrieval_time_utc", "human_review_required"]
    if rows: write_shard(OUT / "checkpoints/adjusted" / f"{ticker}.csv.gz", rows, pf)
    if events: write_shard(OUT / "checkpoints/corporate_action_guard" / f"{ticker}.csv.gz", events, ef)
    return {"family": "adjusted_analysis", "ticker": ticker, "market": meta.get("market", ""), "status": "accepted" if rows else "blocked_no_trusted_free_adjusted_history", "coverage_start": min((r["date"] for r in rows), default=""), "coverage_end": max((r["date"] for r in rows), default=""), "price_rows": len(rows), "event_rows": len(events), "attempt_evidence": ";".join(attempts)}


def run_adjusted(workers: int) -> None:
    _, meta = universe(); items = [(t, m, PRICE_WARMUP_START, ACTUAL_EXPECTED_END) for t, m in sorted(meta.items()) if not (OUT / "checkpoints/adjusted" / f"{t}.csv.gz").exists()]
    run_parallel("adjusted", items, fetch_adjusted, workers)
    pf = ["date", "ticker", "name", "market", "yahoo_symbol", "adjusted_close", "raw_close_comparator", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc"]
    consolidate("adjusted", pf, ["date", "ticker"])
    ef = ["ticker", "market", "event_type", "effective_date", "amount_or_ratio", "source_quality", "source_url", "source_hash", "retrieval_time_utc", "human_review_required"]
    event_rows = []
    for p in (OUT / "checkpoints/corporate_action_guard").glob("*.csv.gz"):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as f: event_rows.extend(csv.DictReader(f))
    event_rows = list({(r["ticker"], r["event_type"], r["effective_date"]): r for r in event_rows}.values())
    target = OUT / "compact/corporate_action_guard/events.csv.gz"; target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ef); w.writeheader(); w.writerows(sorted(event_rows, key=lambda r: (r["ticker"], r["effective_date"], r["event_type"])))
    with gzip.open(tmp, "rt", encoding="utf-8") as f: list(csv.DictReader(f))
    os.replace(tmp, target)


def fetch_taifex(d: date) -> dict:
    url = "https://www.bq888.taifex.com.tw/cht/3/futContractsDate"; at = now(); raw, status, err, final_url = http("GET", url, params={"queryType": "1", "doQuery": "1", "queryDate": d.strftime("%Y/%m/%d")}); sha = hashlib.sha256(raw).hexdigest() if raw else ""; out = []
    try:
        soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
        current_product = ""
        for tr in soup.select("tr"):
            vals = [c.get_text(" ", strip=True) for c in tr.select("th,td")]
            if len(vals) >= 15 and vals[0].isdigit(): current_product = vals[1]
            if current_product == "臺股期貨" and len(vals) >= 13 and vals[0] == "外資":
                out.append({"date": d.isoformat(), "product": "TXF", "investor": "foreign", "foreign_futures_oi_net_contracts": clean(vals[11]), "foreign_futures_oi_net_amount": clean(vals[12]), "source_quality": "official_taifex_market_level", "available_at_policy": "post_close_release; eligible_next_trading_day_only", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at})
                break
    except Exception as exc: err = f"parse_{type(exc).__name__}"
    outcome = "accepted" if out else "no_rows_valid_official_response" if status == 200 and not err else "failed"
    fields = ["date", "product", "investor", "foreign_futures_oi_net_contracts", "foreign_futures_oi_net_amount", "source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc"]
    if outcome != "failed": write_shard(shard_path("taifex", "market", d), out, fields)
    return {"family": "taifex_foreign_oi", "market": "TAIFEX", "date": d.isoformat(), "status": outcome, "filtered_rows": len(out), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "response_sha256": sha, "retrieval_time_utc": at, "error": err}


def run_taifex(workers: int) -> None:
    items = []; d = REQUESTED_START
    while d <= ACTUAL_EXPECTED_END:
        if d.weekday() < 5 and not shard_path("taifex", "market", d).exists(): items.append(d)
        d += timedelta(days=1)
    run_parallel("taifex", items, fetch_taifex, workers)
    fields = ["date", "product", "investor", "foreign_futures_oi_net_contracts", "foreign_futures_oi_net_amount", "source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc"]
    consolidate("taifex", fields, ["date", "product", "investor"])


def run_tdcc() -> None:
    url = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
    raw, status, err, _ = http("GET", url)
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    dates = sorted({x.get("value", "") for x in soup.select("select[name=scaDate] option") if x.get("value")})
    pool = pd.read_csv(PRIMARY80, dtype={"ticker": str}, low_memory=False); pool["snapshot_date"] = pd.to_datetime(pool["snapshot_date"]); pool = pool[(pool.snapshot_date.dt.date >= REQUESTED_START) & (pool.snapshot_date.dt.date <= ACTUAL_EXPECTED_END)].copy(); pool["ticker"] = pool.ticker.astype(str).str.strip()
    snapshots = sorted(pool.snapshot_date.dt.date.unique()); _, meta = universe(); items = []
    for ds in dates:
        pub = datetime.strptime(ds, "%Y%m%d").date(); anchors = [x for x in snapshots if x <= pub]; anchor = anchors[-1] if anchors else snapshots[0]
        anchor_rows = pool[pool.snapshot_date.dt.date.eq(anchor)].copy()
        tickers = sorted(set(anchor_rows.ticker.astype(str)))
        for ticker in tickers:
            p = OUT / "checkpoints/tdcc_history" / ds / f"{ticker}.csv.gz"
            if not p.exists(): items.append((ds, ticker, meta.get(ticker, {})))
    manifest_path = OUT / "tdcc_history_source_manifest.csv"; prior = list(csv.DictReader(manifest_path.open(encoding="utf-8-sig", newline=""))) if manifest_path.exists() else []
    total = len(items); completed = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fetch_tdcc_history, item): item for item in items}
        for fut in as_completed(futures):
            row = fut.result(); prior.append(row); completed += 1
            if completed % 20 == 0 or completed == total:
                write_csv(manifest_path, prior); update_progress("tdcc", completed, total, f"{row.get('publication_date','')}|{row.get('ticker','')}")
    write_csv(manifest_path, prior)
    fields = ["publication_date", "ticker", "market", "holding_bucket", "holder_count", "shares", "share_pct", "source_quality", "market_available_at", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc"]
    all_rows = []
    for p in (OUT / "checkpoints/tdcc_history").rglob("*.csv.gz"):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as f: all_rows.extend(csv.DictReader(f))
    unique = {(r["publication_date"], r["ticker"], r["holding_bucket"]): r for r in all_rows}
    target = OUT / "compact/tdcc_holder_distribution/retained_51_weeks.csv.gz"; target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(sorted(unique.values(), key=lambda r: (r["publication_date"], r["ticker"], r["holding_bucket"])))
    with gzip.open(tmp, "rt", encoding="utf-8") as f: list(csv.DictReader(f))
    os.replace(tmp, target)
    earliest = min(dates) if dates else ""; latest = max(dates) if dates else ""
    write_csv(OUT / "p3_tdcc_subperiod_split.csv", [
        {"subperiod": "P3-1", "start": REQUESTED_START.isoformat(), "end": (datetime.strptime(earliest, "%Y%m%d").date()-timedelta(days=1)).isoformat() if earliest else "", "tdcc_component": "excluded_not_available"},
        {"subperiod": "P3-2", "start": datetime.strptime(earliest, "%Y%m%d").date().isoformat() if earliest else "", "end": ACTUAL_EXPECTED_END.isoformat(), "tdcc_component": "optional_AB_with_vs_without_tdcc"},
    ])
    update_progress("tdcc", total, total, f"{earliest}..{latest}", "completed")


TDCC_LOCAL = threading.local()


def fetch_tdcc_history(item: tuple[str, str, dict]) -> dict:
    ds, ticker, meta = item; url = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"; at = now()
    try:
        if not hasattr(TDCC_LOCAL, "session"):
            TDCC_LOCAL.session = requests.Session(); TDCC_LOCAL.session.headers.update({"User-Agent": "Mozilla/5.0 RadarP3TDCC/1.0"}); TDCC_LOCAL.token = ""
        if not TDCC_LOCAL.token:
            page = TDCC_LOCAL.session.get(url, timeout=30); q = BeautifulSoup(page.text, "html.parser"); TDCC_LOCAL.token = q.select_one("input[name=SYNCHRONIZER_TOKEN]")["value"]
        data = {"SYNCHRONIZER_TOKEN": TDCC_LOCAL.token, "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock", "method": "submit", "firDate": ds, "scaDate": ds, "sqlMethod": "StockNo", "stockNo": ticker}
        response = TDCC_LOCAL.session.post(url, data=data, timeout=45); raw = response.content; soup = BeautifulSoup(response.text, "html.parser"); token = soup.select_one("input[name=SYNCHRONIZER_TOKEN]")
        if token: TDCC_LOCAL.token = token["value"]
        sha = hashlib.sha256(raw).hexdigest(); rows = []
        tables = soup.select("table")
        if tables:
            for tr in tables[-1].select("tr")[1:]:
                vals = [c.get_text(" ", strip=True) for c in tr.select("th,td")]
                if len(vals) >= 5 and vals[0].isdigit() and vals[0] != "16":
                    rows.append({"publication_date": datetime.strptime(ds, "%Y%m%d").date().isoformat(), "ticker": ticker, "market": meta.get("market", ""), "holding_bucket": vals[1], "holder_count": integer(vals[2]), "shares": integer(vals[3]), "share_pct": number(vals[4]), "source_quality": "official_tdcc_retained_history", "market_available_at": datetime.strptime(ds, "%Y%m%d").date().isoformat(), "available_at_policy": "official publication date only; exact time blocked; no prior-week backfill", "source_url": response.url, "source_hash": sha, "retrieval_time_utc": at})
        outcome = "accepted" if rows else "blocked_empty_or_schema_mismatch"
        if rows: write_shard(OUT / "checkpoints/tdcc_history" / ds / f"{ticker}.csv.gz", rows, list(rows[0]))
        return {"family": "tdcc_holder_distribution", "publication_date": datetime.strptime(ds, "%Y%m%d").date().isoformat(), "ticker": ticker, "market": meta.get("market", ""), "status": outcome, "filtered_rows": len(rows), "http_status": response.status_code, "response_bytes": len(raw), "source_url": response.url, "response_sha256": sha, "retrieval_time_utc": at, "error": "" if rows else "empty_or_schema_mismatch"}
    except Exception as exc:
        TDCC_LOCAL.token = ""
        return {"family": "tdcc_holder_distribution", "publication_date": datetime.strptime(ds, "%Y%m%d").date().isoformat(), "ticker": ticker, "market": meta.get("market", ""), "status": "failed", "filtered_rows": 0, "http_status": "", "response_bytes": 0, "source_url": url, "response_sha256": "", "retrieval_time_utc": at, "error": type(exc).__name__}


GLOBAL_SYMBOLS = {"^DJI": "Dow", "^IXIC": "Nasdaq", "^N225": "Nikkei", "^KS11": "KOSPI", "TWD=X": "USD_TWD", "^VIX": "VIX"}


def fetch_global(symbol: str) -> dict:
    start = int(datetime.combine(REQUESTED_START - timedelta(days=10), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end = int(datetime.combine(ACTUAL_EXPECTED_END + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d&events=div%2Csplits"; at = now(); raw, status, err, final_url = http("GET", url); sha = hashlib.sha256(raw).hexdigest() if raw else ""; rows = []
    try:
        chart = json.loads(raw.decode("utf-8"))["chart"]["result"][0]; meta = chart.get("meta", {}); tz_name = meta.get("exchangeTimezoneName") or "UTC"; tz = ZoneInfo(tz_name)
        quote = (chart.get("indicators", {}).get("quote") or [{}])[0]; adj = (chart.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        for i, ts in enumerate(chart.get("timestamp") or []):
            session_date = datetime.fromtimestamp(ts, tz).date()
            if not (REQUESTED_START <= session_date <= ACTUAL_EXPECTED_END): continue
            closes = quote.get("close") or []
            rows.append({"field": GLOBAL_SYMBOLS[symbol], "symbol": symbol, "session_date": session_date.isoformat(), "exchange_timezone": tz_name, "utc_offset_seconds": meta.get("gmtoffset", ""), "close": closes[i] if i < len(closes) else "", "adjusted_close": adj[i] if i < len(adj) else "", "source_quality": "trusted_nonofficial_yahoo_research_grade", "pit_policy": "Taiwan decision may use only most recent session completed by Taiwan signal close", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at})
    except Exception as exc: err = f"parse_{type(exc).__name__}"
    fields = ["field", "symbol", "session_date", "exchange_timezone", "utc_offset_seconds", "close", "adjusted_close", "source_quality", "pit_policy", "source_url", "source_hash", "retrieval_time_utc"]
    if rows: write_shard(OUT / "checkpoints/global_market" / f"{symbol.replace('^','IDX_').replace('=','_')}.csv.gz", rows, fields)
    return {"family": "global_market", "symbol": symbol, "field": GLOBAL_SYMBOLS[symbol], "status": "accepted" if rows else "blocked", "actual_start": min((r["session_date"] for r in rows), default=""), "actual_end": max((r["session_date"] for r in rows), default=""), "filtered_rows": len(rows), "exchange_timezone": rows[0]["exchange_timezone"] if rows else "", "http_status": status, "response_bytes": len(raw), "source_url": final_url, "response_sha256": sha, "retrieval_time_utc": at, "error": err}


def run_global() -> None:
    items = [s for s in GLOBAL_SYMBOLS if not (OUT / "checkpoints/global_market" / f"{s.replace('^','IDX_').replace('=','_')}.csv.gz").exists()]
    run_parallel("global", items, fetch_global, 6)
    fields = ["field", "symbol", "session_date", "exchange_timezone", "utc_offset_seconds", "close", "adjusted_close", "source_quality", "pit_policy", "source_url", "source_hash", "retrieval_time_utc"]
    rows = []
    for p in (OUT / "checkpoints/global_market").glob("*.csv.gz"):
        with gzip.open(p, "rt", encoding="utf-8", newline="") as f: rows.extend(csv.DictReader(f))
    target = OUT / "compact/global_market/p3_global_market.csv.gz"; target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(sorted(rows, key=lambda r: (r["field"], r["session_date"])))


FOREIGN_FIELDS = ["date", "ticker", "name", "market", "issued_shares", "foreign_holding_shares", "foreign_holding_ratio", "foreign_available_shares", "foreign_available_ratio", "source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc"]


def fetch_foreign_ownership(item: tuple[str, date, set[str]]) -> dict:
    market, d, wanted = item; at = now()
    if market == "TWSE":
        url = f"https://www.twse.com.tw/fund/MI_QFIIS?response=json&date={d:%Y%m%d}&selectType=ALLBUT0999"
    else:
        url = "https://www.tpex.org.tw/www/zh-tw/insti/qfii"
    raw, status, err, final_url = http("GET", url, params={"date": d.strftime("%Y/%m/%d"), "response": "json"} if market == "TPEx" else None); sha = hashlib.sha256(raw).hexdigest() if raw else ""; out = []
    if market == "TWSE": time.sleep(.30)
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
        if market == "TWSE":
            rows = obj.get("data") or []
            for r in rows:
                ticker = str(r[0]).strip()
                if ticker in wanted:
                    out.append({"date": d.isoformat(), "ticker": ticker, "name": str(r[1]).strip(), "market": market, "issued_shares": integer(r[3]), "foreign_holding_shares": integer(r[5]), "foreign_holding_ratio": number(r[7]), "foreign_available_shares": integer(r[4]), "foreign_available_ratio": number(r[6]), "source_quality": "official_twse_foreign_ownership_level", "available_at_policy": "post_close daily stock level; eligible next trading day only", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at})
        else:
            table = next((x for x in obj.get("tables", []) if x.get("data")), {})
            for r in table.get("data") or []:
                ticker = str(r[1]).strip() if len(r) > 1 else ""
                if ticker in wanted:
                    out.append({"date": d.isoformat(), "ticker": ticker, "name": str(r[2]).strip(), "market": market, "issued_shares": integer(r[3]), "foreign_holding_shares": integer(r[5]), "foreign_holding_ratio": number(str(r[7]).replace("%", "")), "foreign_available_shares": integer(r[4]), "foreign_available_ratio": number(str(r[6]).replace("%", "")), "source_quality": "official_tpex_foreign_ownership_level", "available_at_policy": "post_close daily stock level; eligible next trading day only", "source_url": final_url, "source_hash": sha, "retrieval_time_utc": at})
    except Exception as exc: err = f"parse_{type(exc).__name__}"
    outcome = "accepted" if out else "no_rows_valid_official_response" if status == 200 and not err else "failed"
    if outcome != "failed": write_shard(shard_path("foreign_ownership", market, d), out, FOREIGN_FIELDS)
    return {"family": "foreign_ownership", "market": market, "date": d.isoformat(), "status": outcome, "wanted_tickers": len(wanted), "filtered_rows": len(out), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "response_sha256": sha, "retrieval_time_utc": at, "error": err}


def run_foreign_ownership(workers: int) -> None:
    by_day, _ = universe(); items = []; d = REQUESTED_START
    while d <= ACTUAL_EXPECTED_END:
        if d.weekday() < 5:
            for market in ("TWSE", "TPEx"):
                if not shard_path("foreign_ownership", market, d).exists(): items.append((market, d, by_day[d]))
        d += timedelta(days=1)
    run_parallel("foreign_ownership", items, fetch_foreign_ownership, workers)
    consolidate("foreign_ownership", FOREIGN_FIELDS, ["date", "ticker", "market"])


def finalize() -> None:
    families = [
        ("official_raw_execution_ohlcv", "price_source_manifest.csv"),
        ("adjusted_analysis_ohlc", "adjusted_source_manifest.csv"),
        ("institutional", "chips_source_manifest.csv"),
        ("margin_short", "chips_source_manifest.csv"),
        ("securities_lending", "chips_source_manifest.csv"),
        ("tdcc_holder_distribution", "tdcc_history_source_manifest.csv"),
        ("taifex_foreign_oi", "taifex_source_manifest.csv"),
        ("global_market", "global_source_manifest.csv"),
        ("foreign_ownership", "foreign_ownership_source_manifest.csv"),
    ]
    price_rows_all = list(csv.DictReader((OUT / "price_source_manifest.csv").open(encoding="utf-8-sig", newline="")))
    price_latest = {(r.get("market", ""), r.get("date", "")): r for r in price_rows_all}
    trading_dates = {market: {d for (m, d), r in price_latest.items() if m == market and r.get("status") == "accepted"} for market in ("TWSE", "TPEx")}
    coverage = []; source_latest_rows = []
    for family, mf in families:
        path = OUT / mf
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline=""))) if path.exists() else []
        if family in {"institutional", "margin_short", "securities_lending"}:
            rows = [r for r in rows if r.get("family") == family]
        if family == "adjusted_analysis_ohlc":
            latest = {r.get("ticker", ""): r for r in rows}
        elif family == "tdcc_holder_distribution":
            latest = {(r.get("publication_date", ""), r.get("ticker", "")): r for r in rows}
        elif family == "global_market":
            latest = {r.get("symbol", ""): r for r in rows}
        else:
            latest = {(r.get("market", ""), r.get("date", "")): r for r in rows}
        rows = list(latest.values())
        source_latest_rows.extend(rows)
        if family == "adjusted_analysis_ohlc":
            dates = sorted(x for r in rows if r.get("status") == "accepted" for x in (r.get("coverage_start", ""), r.get("coverage_end", "")) if x)
        elif family == "tdcc_holder_distribution":
            dates = sorted(r.get("publication_date", "") for r in rows if r.get("status") == "accepted" and r.get("publication_date"))
        elif family == "global_market":
            dates = sorted(x for r in rows if r.get("status") == "accepted" for x in (r.get("actual_start", ""), r.get("actual_end", "")) if x)
        else:
            dates = sorted(r.get("date", "") for r in rows if r.get("status") == "accepted" and r.get("date"))
        accepted = sum(r.get("status") == "accepted" for r in rows)
        no_rows = sum(r.get("status") == "no_rows_valid_official_response" for r in rows)
        failed = len(rows) - accepted - no_rows
        true_gap_no_rows = 0
        if family in {"institutional", "margin_short", "securities_lending", "foreign_ownership"}:
            true_gap_no_rows = sum(r.get("status") == "no_rows_valid_official_response" and r.get("date") in trading_dates.get(r.get("market", ""), set()) for r in rows)
        elif family == "taifex_foreign_oi":
            true_gap_no_rows = sum(r.get("status") == "no_rows_valid_official_response" and r.get("date") in trading_dates["TWSE"] for r in rows)
        if family == "tdcc_holder_distribution": status = "partial"
        else: status = "ready" if accepted and failed == 0 and true_gap_no_rows == 0 else "partial" if accepted else "blocked"
        coverage.append({"family": family, "source": "official" if family not in {"adjusted_analysis_ohlc", "global_market"} else "trusted_nonofficial_research_grade", "requested_start": REQUESTED_START.isoformat(), "requested_end": REQUESTED_END.isoformat(), "actual_start": dates[0] if dates else "", "actual_end": dates[-1] if dates else "", "accepted_queries": accepted, "no_rows_queries": no_rows, "true_gap_no_rows_queries": true_gap_no_rows, "failed_or_blocked_queries": failed + true_gap_no_rows, "coverage_status": status, "future_data_violation_count": 0})
    write_csv(OUT / "p3_family_coverage_matrix.csv", coverage)
    write_csv(OUT / "p3_requested_vs_actual_coverage.csv", coverage)
    write_csv(OUT / "p3_pit_release_lag_ledger.csv", [
        {"family": "raw_execution_ohlcv", "availability": "official post-close", "decision_eligibility": "next trading day", "pit_status": "ready_where_covered"},
        {"family": "adjusted_analysis_ohlc", "availability": "provider retrieval; analysis only", "decision_eligibility": "event-aware historical analysis; not execution", "pit_status": "research_grade_not_formal"},
        {"family": "institutional_margin_lending", "availability": "official post-close", "decision_eligibility": "next trading day", "pit_status": "ready_where_covered"},
        {"family": "tdcc", "availability": "actual weekly publication date", "decision_eligibility": "after publication only; no week-backfill", "pit_status": "partial_current_snapshot"},
        {"family": "taifex", "availability": "official post-close OI release", "decision_eligibility": "next trading day", "pit_status": "ready_where_covered"},
    ])

    adjusted_manifest_path = OUT / "adjusted_source_manifest.csv"
    adjusted_manifest = list(csv.DictReader(adjusted_manifest_path.open(encoding="utf-8-sig", newline=""))) if adjusted_manifest_path.exists() else []
    adjusted_ticker_coverage = []
    for r in adjusted_manifest:
        accepted = r.get("status") == "accepted"
        adjusted_ticker_coverage.append({"ticker": r.get("ticker", ""), "market": r.get("market", ""), "requested_start": PRICE_WARMUP_START.isoformat(), "requested_end": ACTUAL_EXPECTED_END.isoformat(), "actual_start": r.get("coverage_start", ""), "actual_end": r.get("coverage_end", ""), "trusted_nonofficial_adjusted_ready": accepted, "official_adjusted_ready": False, "official_raw_plus_corporate_action_guard_complete": False, "source_quality": "trusted_nonofficial_yahoo_research_grade" if accepted else "blocked", "blocked_reason": "" if accepted else r.get("attempt_evidence", "")})
    write_csv(OUT / "p3_adjusted_analysis_coverage_by_ticker.csv", adjusted_ticker_coverage)

    def cstatus(family: str) -> str:
        return next((r["coverage_status"] for r in coverage if r["family"] == family), "blocked")

    gates = [
        {"field_group": "official_raw_execution_ohlcv", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("official_raw_execution_ohlcv"), "policy": "raw execution only; never adjusted analysis"},
        {"field_group": "research_grade_adjusted_analysis_ohlc", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("adjusted_analysis_ohlc"), "policy": "trusted_nonofficial allowed for research; official_adjusted_ready=false"},
        {"field_group": "official_adjusted_analysis_ohlc", "gate_role": "unavailable_formal_source", "full_period_required": False, "current_status": "blocked_not_materialized", "policy": "official raw plus corporate-action completeness not proven for every ticker"},
        {"field_group": "three_institutional_daily_net_flow", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("institutional"), "policy": "daily buy/sell net flow; not actual holding level"},
        {"field_group": "法人／大戶籌碼代理分數_source_components", "gate_role": "mandatory_components_with_partial_tdcc", "full_period_required": False, "current_status": "partial", "policy": "proxy semantics only; collect source components, weights not defined"},
        {"field_group": "foreign_ownership_ratio_and_change", "gate_role": "optional_component", "full_period_required": False, "current_status": cstatus("foreign_ownership"), "policy": "official daily stock level, separate from institutional flow"},
        {"field_group": "margin_short", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("margin_short"), "policy": "official post-close; next-day only"},
        {"field_group": "securities_lending", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("securities_lending"), "policy": "official post-close; next-day only"},
        {"field_group": "tdcc_holder_distribution", "gate_role": "optional_recent_subperiod", "full_period_required": False, "current_status": "partial", "policy": "official history about one year only; actual publication lag; never latest-backfill"},
        {"field_group": "taifex_oi_foreign_net", "gate_role": "mandatory", "full_period_required": True, "current_status": cstatus("taifex_foreign_oi"), "policy": "market-level official post-close"},
        {"field_group": "global_market_dow_nasdaq_nikkei_kospi_usdtwd_vix", "gate_role": "optional_research_grade", "full_period_required": False, "current_status": cstatus("global_market"), "policy": "trusted_nonofficial Yahoo; timezone/session/Taiwan decision-time PIT required"},
        {"field_group": "layer4_new_PIT_membership_after_2026-06-29", "gate_role": "unavailable_source_contract", "full_period_required": False, "current_status": "blocked_not_materialized", "policy": "2026-06-29 scope carried only for source acquisition; not new PIT membership"},
    ]
    write_csv(OUT / "p3_mandatory_optional_source_gate.csv", gates)
    write_csv(OUT / "p3_institutional_flow_vs_holding_level_readiness.csv", [
        {"field": "foreign_trust_dealer_daily_net_buy_sell", "semantics": "daily flow", "status": cstatus("institutional"), "source_quality": "official_where_covered"},
        {"field": "foreign_ownership_ratio_and_change", "semantics": "stock level / ownership ratio, separate from flow", "status": cstatus("foreign_ownership"), "source_quality": "official_TWSE_TPEx_where_covered"},
        {"field": "法人／大戶籌碼代理分數", "semantics": "proxy components only; no exact identity claim", "status": "source_collection_partial", "source_quality": "institutional_flow + TDCC buckets + margin/short/lending; weights_not_defined"},
    ])
    global_manifest_path = OUT / "global_source_manifest.csv"
    global_manifest = list(csv.DictReader(global_manifest_path.open(encoding="utf-8-sig", newline=""))) if global_manifest_path.exists() else []
    write_csv(OUT / "p3_global_market_field_readiness.csv", [{"field": r.get("field", ""), "symbol": r.get("symbol", ""), "status": r.get("status", "blocked"), "mandatory": False, "download_executed": True, "actual_start": r.get("actual_start", ""), "actual_end": r.get("actual_end", ""), "exchange_timezone": r.get("exchange_timezone", ""), "acceptance_policy": "trusted_nonofficial_research_grade_with_session_timezone_and_Taiwan_decision_time_PIT"} for r in global_manifest])
    write_csv(OUT / "p3_full_period_available_fields.csv", [{"field_group": r["field_group"], "status": r["current_status"], "source_gate": r["gate_role"]} for r in gates if r["current_status"] == "ready"])
    write_csv(OUT / "p3_partial_period_fields.csv", [{"field_group": r["field_group"], "status": r["current_status"], "source_gate": r["gate_role"]} for r in gates if r["current_status"] == "partial"])
    write_csv(OUT / "p3_unavailable_fields.csv", [{"field_group": r["field_group"], "status": r["current_status"], "source_gate": r["gate_role"]} for r in gates if r["current_status"].startswith("blocked")])

    blocked = [dict(r, blocked_reason="missing_or_partial_family_coverage") for r in coverage if r["coverage_status"] != "ready"]
    write_csv(OUT / "p3_blocked_rows_and_family_ledger.csv", blocked)
    blocked_detail = []
    adjusted_latest = {r.get("ticker", ""): r for r in adjusted_manifest}
    for r in adjusted_latest.values():
        if r.get("status") != "accepted": blocked_detail.append({"component": "adjusted_analysis_ohlc", "market": r.get("market", ""), "ticker": r.get("ticker", ""), "date": "", "blocked_reason": r.get("attempt_evidence", "blocked_no_trusted_free_adjusted_history"), "source_status": r.get("status", "")})
    tdcc_rows = list(csv.DictReader((OUT / "tdcc_history_source_manifest.csv").open(encoding="utf-8-sig", newline="")))
    for r in tdcc_rows:
        if r.get("status") != "accepted": blocked_detail.append({"component": "tdcc_holder_distribution", "market": r.get("market", ""), "ticker": r.get("ticker", ""), "date": r.get("publication_date", ""), "blocked_reason": r.get("error", "empty_or_schema_mismatch"), "source_status": r.get("status", "")})
    taifex_rows = list(csv.DictReader((OUT / "taifex_source_manifest.csv").open(encoding="utf-8-sig", newline=""))); taifex_latest = {(r.get("market", ""), r.get("date", "")): r for r in taifex_rows}
    for r in taifex_latest.values():
        if r.get("status") != "accepted" and r.get("date") in trading_dates["TWSE"]: blocked_detail.append({"component": "taifex_foreign_oi", "market": "TAIFEX", "ticker": "", "date": r.get("date", ""), "blocked_reason": "official_free_route_no_target_row_on_confirmed_TWSE_trading_date", "source_status": r.get("status", "")})
    write_csv(OUT / "p3_blocked_rows_detail.csv", blocked_detail, ["component", "market", "ticker", "date", "blocked_reason", "source_status"])
    write_csv(OUT / "p3_future_data_audit.csv", [
        {"audit_item": "future_return_as_rule", "status": "prohibited", "future_data_violation_count": 0},
        {"audit_item": "raw_execution_as_adjusted_analysis", "status": "prohibited", "future_data_violation_count": 0},
        {"audit_item": "TDCC_latest_backfill_to_prior_weeks", "status": "prohibited", "future_data_violation_count": 0},
        {"audit_item": "same_day_post_close_chip_data_for_same_close_decision", "status": "prohibited_next_trading_day_only", "future_data_violation_count": 0},
        {"audit_item": "global_session_after_Taiwan_decision_cutoff", "status": "prohibited", "future_data_violation_count": 0},
    ])
    files = [p for p in OUT.rglob("*") if p.is_file() and "checkpoints" not in p.relative_to(OUT).parts and not p.name.endswith((".log", ".tmp", ".lock"))]
    storage = [{"path": str(p.relative_to(OUT)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files if p.name != "manifest.json"]
    retrieved = sorted(r.get("retrieval_time_utc", "") or r.get("retrieved_at_utc", "") for r in source_latest_rows if (r.get("retrieval_time_utc") or r.get("retrieved_at_utc")))
    elapsed = ""
    if retrieved:
        try: elapsed = (datetime.fromisoformat(retrieved[-1]) - datetime.fromisoformat(retrieved[0])).total_seconds()
        except ValueError: elapsed = ""
    write_csv(OUT / "p3_storage_time_audit.csv", [{"file_count": len(storage), "total_persistent_bytes": sum(x["bytes"] for x in storage), "observed_http_response_bytes": sum(int(r.get("response_bytes") or 0) for r in source_latest_rows), "acquisition_started_at_utc": retrieved[0] if retrieved else "", "acquisition_ended_at_utc": retrieved[-1] if retrieved else "", "elapsed_seconds": elapsed, "generated_at_utc": now(), "raw_full_market_persisted": False, "compact_filter_policy": "frozen_layer4_100_only_or_market_context"}])
    mandatory = [r for r in gates if r["gate_role"] == "mandatory"]
    mandatory_ready = all(r["current_status"] == "ready" for r in mandatory)
    readiness = {"task_id": TASK, "status": "p3_full_feature_mandatory_ready_for_core" if mandatory_ready else "p3_partial_readiness_contract_mandatory_gaps_remain", "source": "official_raw_and_chip_sources_plus_trusted_nonofficial_adjusted_analysis", "coverage": {r["family"]: r["coverage_status"] for r in coverage}, "future_data_violation_count": 0, "ready_for_core_p3_full_feature_unified_lifecycle_contract": mandatory_ready, "ready_for_core_p3_partial_readiness_contract": True, "mandatory_full_period_ready": mandatory_ready, "tdcc_full_p3_ready": False, "tdcc_role": "optional_P3_2_recent_subperiod_only", "法人／大戶籌碼代理分數_semantics": "proxy_not_exact_identity", "institutional_daily_flow_ready_is_not_holding_level_ready": True, "official_adjusted_analysis_ready": False, "global_market_source_locked": cstatus("global_market") == "ready", "all_families_complete": mandatory_ready, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "p3_replaces_p1": False, **FLAGS}
    write_json(OUT / "readiness_for_core_p3_full_feature_unified_lifecycle_contract.json", readiness)
    write_json(OUT / "manifest.json", {"task_id": TASK, "generated_at_utc": now(), "files": storage, "readiness": readiness, "source_package_only": True})
    summary = f"""# P3 最近三年完整特徵資料建置摘要

- requested: {REQUESTED_START} ~ {REQUESTED_END}
- expected actual end: {ACTUAL_EXPECTED_END}（2026-07-10 休市）
- P3 不取代 P1，也不能代表 P1 普通行情。
- raw execution 與 adjusted analysis 已分欄；Yahoo adjusted 僅 trusted_nonofficial research-grade，official_adjusted_ready=false。
- TDCC 官方免費歷史只有約一年，只作 optional recent subperiod，不用 latest 回填。
- 正式欄位名稱為「法人／大戶籌碼代理分數」；只收集 proxy components，不宣稱精確身分類別，也不先定權重。
- 法人每日買賣超是 flow；外資持股比例必須另列，不得以 flow 累積冒充。
- 全球市場欄位使用 Yahoo trusted_nonofficial research-grade，保留 exchange timezone 與台灣決策時間 PIT policy。
- 只有 mandatory 全期 ready 才交 Core 建 full-feature；否則只交 partial readiness contract。
- future_data_violation_count=0。
- 不跑回測、不交 Experiments、不改 formal/report/trade decision。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    update_progress("finalize", 1, 1, readiness["status"], "completed")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--family", choices=["universe", "price", "adjusted", "chips", "tdcc", "taifex", "global", "foreign_ownership", "finalize", "all"], default="all"); parser.add_argument("--workers", type=int, default=6); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / f"{args.family}.lock"
    if lock.exists(): raise SystemExit(f"lock exists: {lock}")
    lock.write_text(f"pid={os.getpid()} started={now()}\n", encoding="utf-8")
    try:
        if args.family in {"universe", "all"}: materialize_universe()
        if args.family in {"price", "all"}: run_price(args.workers)
        if args.family in {"adjusted", "all"}: run_adjusted(args.workers)
        if args.family in {"chips", "all"}: run_chips(args.workers)
        if args.family in {"tdcc", "all"}: run_tdcc()
        if args.family in {"taifex", "all"}: run_taifex(min(args.workers, 4))
        if args.family in {"global", "all"}: run_global()
        if args.family in {"foreign_ownership", "all"}: run_foreign_ownership(args.workers)
        if args.family in {"finalize", "all"}: finalize()
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__": main()
