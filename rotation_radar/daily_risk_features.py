"""Daily compact risk-feature source acquisition for GitHub Actions.

This module collects source data only. It does not calculate strategy weights,
produce trade decisions, or treat trusted non-official analysis prices as raw
execution prices.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import tempfile
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from rotation_radar.schedule_gate import fetch_twse_calendar


TAIPEI = ZoneInfo("Asia/Taipei")
GLOBAL_SYMBOLS = {"^DJI": "Dow", "^IXIC": "Nasdaq", "^N225": "Nikkei", "^KS11": "KOSPI", "TWD=X": "USD_TWD", "^VIX": "VIX"}
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False, "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}


class IncompleteSourceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: object) -> str:
    return str(value).replace(",", "").replace("--", "").strip()


def number(value: object) -> str:
    try:
        x = clean(value).replace("%", "")
        return str(float(x)) if x else ""
    except (TypeError, ValueError):
        return ""


def integer(value: object) -> str:
    try:
        x = clean(value)
        return str(int(float(x))) if x else ""
    except (TypeError, ValueError):
        return ""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def request(method: str, url: str, retries: int = 3, **kwargs) -> tuple[bytes, int, str, str, str]:
    last = (b"", 0, "no_attempt", url, utc_now())
    for attempt in range(retries):
        retrieved = utc_now()
        try:
            response = requests.request(method, url, timeout=45, headers={"User-Agent": "Mozilla/5.0 RadarDailyRisk/1.0", "Accept": "application/json,text/html,*/*"}, **kwargs)
            error = "" if response.ok else f"HTTP_{response.status_code}"
            if response.ok: return response.content, response.status_code, error, response.url, retrieved
            last = (response.content, response.status_code, error, response.url, retrieved)
        except requests.RequestException as exc:
            last = (b"", 0, type(exc).__name__, url, retrieved)
        time.sleep(2 ** attempt)
    return last


def atomic_csv_gz(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd); tmp = Path(tmp_name)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
        with gzip.open(tmp, "rt", encoding="utf-8", newline="") as f: verified = list(csv.DictReader(f))
        if len(verified) != len(rows): raise RuntimeError("gzip row verification failed")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd); tmp = Path(tmp_name)
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8")); os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load_scope(path: Path) -> tuple[set[str], dict[str, dict]]:
    if not path.exists(): raise IncompleteSourceError(f"missing frozen candidate scope: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    meta = {str(r["ticker"]).strip(): r for r in rows if r.get("ticker")}
    if not meta: raise IncompleteSourceError("frozen candidate scope is empty")
    return set(meta), meta


def classify_calendar_day(target: date, open_dates: set[date], closed_dates: set[date] | None) -> str:
    if target in open_dates: return "scheduled_open"
    if closed_dates is not None and target in closed_dates: return "scheduled_closed"
    if target.weekday() >= 5: return "weekend_closed"
    return "calendar_unknown_weekday"


def parse_twse_price(raw: bytes, target: date, wanted: set[str], url: str, retrieved: str) -> list[dict]:
    obj = json.loads(raw.decode("utf-8-sig")); table = next((x for x in obj.get("tables", []) if (x.get("data") or []) and len(x.get("fields") or []) >= 9), {}); rows = []
    for r in table.get("data") or []:
        if len(r) >= 9 and str(r[0]).strip() in wanted and number(r[8]):
            rows.append({"date": target.isoformat(), "ticker": str(r[0]).strip(), "name": str(r[1]).strip(), "market": "TWSE", "open": number(r[5]), "high": number(r[6]), "low": number(r[7]), "close": number(r[8]), "volume": integer(r[2]), "turnover_value": integer(r[4]), "price_basis": "official_raw_execution_unadjusted", "source_url": url, "source_hash": sha(raw), "retrieved_at_utc": retrieved})
    return rows


def parse_tpex_price(raw: bytes, target: date, wanted: set[str], url: str, retrieved: str) -> list[dict]:
    obj = json.loads(raw.decode("utf-8-sig")); table = next((x for x in obj.get("tables", []) if x.get("data")), {}); rows = []
    for r in table.get("data") or []:
        if len(r) >= 10 and str(r[0]).strip() in wanted and number(r[2]):
            rows.append({"date": target.isoformat(), "ticker": str(r[0]).strip(), "name": str(r[1]).strip(), "market": "TPEx", "open": number(r[4]), "high": number(r[5]), "low": number(r[6]), "close": number(r[2]), "volume": integer(r[8]), "turnover_value": integer(r[9]), "price_basis": "official_raw_execution_unadjusted", "source_url": url, "source_hash": sha(raw), "retrieved_at_utc": retrieved})
    return rows


def fetch_price(target: date, wanted: set[str]) -> tuple[list[dict], list[dict]]:
    rows, manifest = [], []
    routes = [("TWSE", f"https://www.twse.com.tw/exchangeReport/MI_INDEX?date={target:%Y%m%d}&type=ALLBUT0999&response=json", parse_twse_price), ("TPEx", f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={target:%Y/%m/%d}&response=json", parse_tpex_price)]
    for market, url, parser in routes:
        raw, status, error, final_url, retrieved = request("GET", url); accepted = []
        if raw and status == 200:
            try: accepted = parser(raw, target, wanted, final_url, retrieved)
            except Exception as exc: error = f"parse_{type(exc).__name__}"
        state = "accepted" if accepted else "no_rows" if status == 200 and not error else "blocked"
        rows.extend(accepted); manifest.append({"family": "official_raw_execution_ohlcv", "market": market, "requested_date": target.isoformat(), "actual_source_date": target.isoformat() if accepted else "", "status": state, "row_count": len(accepted), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error})
    return rows, manifest


def fetch_chip_family(target: date, wanted: set[str]) -> tuple[list[dict], list[dict]]:
    fields = {"institutional": ("foreign_net", "trust_net", "dealer_net"), "margin_short": ("margin_balance", "margin_change", "short_balance", "short_change"), "securities_lending": ("sbl_balance", "sbl_change")}
    rows, manifest = [], []
    for market in ("TWSE", "TPEx"):
        for family in fields:
            if market == "TWSE":
                urls = {"institutional": f"https://www.twse.com.tw/fund/T86?date={target:%Y%m%d}&selectType=ALLBUT0999&response=json", "margin_short": f"https://www.twse.com.tw/exchangeReport/MI_MARGN?date={target:%Y%m%d}&selectType=ALL&response=json", "securities_lending": f"https://www.twse.com.tw/exchangeReport/TWT72U?date={target:%Y%m%d}&response=json"}; method = "GET"; kwargs = {}
            else:
                urls = {"institutional": "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade", "margin_short": "https://www.tpex.org.tw/www/zh-tw/margin/balance", "securities_lending": "https://www.tpex.org.tw/www/zh-tw/margin/sbl"}; method = "POST"; payload = {"date": target.strftime("%Y/%m/%d"), "response": "json"};
                if family == "institutional": payload.update({"type": "Daily", "cate": "EW"})
                kwargs = {"data": payload}
            raw, status, error, final_url, retrieved = request(method, urls[family], **kwargs); accepted = []
            try:
                obj = json.loads(raw.decode("utf-8-sig")) if raw else {}
                if market == "TWSE" and family == "institutional": source_rows = obj.get("data") or []
                elif market == "TWSE" and family == "securities_lending": source_rows = obj.get("data") or []
                else: source_rows = next((x.get("data") or [] for x in obj.get("tables", []) if (x.get("data") or []) and (market == "TPEx" or len(x.get("fields") or []) >= 12)), [])
                for r in source_rows:
                    ticker_index = 0 if not (market == "TPEx" and family == "institutional") else 0; ticker = str(r[ticker_index]).strip()
                    if ticker not in wanted: continue
                    item = {"date": target.isoformat(), "ticker": ticker, "name": str(r[1]).strip(), "market": market, "family": family, "foreign_net": "", "trust_net": "", "dealer_net": "", "margin_balance": "", "margin_change": "", "short_balance": "", "short_change": "", "sbl_balance": "", "sbl_change": "", "available_at_policy": "official post-close; next-trading-day eligible", "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved}
                    if family == "institutional":
                        item.update({"foreign_net": integer(r[4]), "trust_net": integer(r[7]), "dealer_net": integer(r[8] if market == "TWSE" else r[10])})
                    elif family == "margin_short": item.update({"margin_balance": integer(r[6]), "margin_change": str(int(integer(r[3]) or 0)-int(integer(r[4]) or 0)), "short_balance": integer(r[12] if market == "TWSE" else r[14]), "short_change": str(int(integer(r[8] if market == "TWSE" else r[11]) or 0)-int(integer(r[9] if market == "TWSE" else r[12]) or 0))})
                    else:
                        balance, prev = (r[5], r[2]) if market == "TWSE" else (r[12], r[8]); item.update({"sbl_balance": integer(balance), "sbl_change": str(int(integer(balance) or 0)-int(integer(prev) or 0))})
                    accepted.append(item)
            except Exception as exc: error = f"parse_{type(exc).__name__}"
            state = "accepted" if accepted else "no_rows" if status == 200 and not error else "blocked"; rows.extend(accepted); manifest.append({"family": family, "market": market, "requested_date": target.isoformat(), "actual_source_date": target.isoformat() if accepted else "", "status": state, "row_count": len(accepted), "http_status": status, "response_bytes": len(raw), "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error})
    return rows, manifest


def fetch_foreign_ownership(target: date, wanted: set[str]) -> tuple[list[dict], list[dict]]:
    rows, manifest = [], []
    for market in ("TWSE", "TPEx"):
        url = f"https://www.twse.com.tw/fund/MI_QFIIS?response=json&date={target:%Y%m%d}&selectType=ALLBUT0999" if market == "TWSE" else "https://www.tpex.org.tw/www/zh-tw/insti/qfii"
        kwargs = {} if market == "TWSE" else {"params": {"date": target.strftime("%Y/%m/%d"), "response": "json"}}
        raw, status, error, final_url, retrieved = request("GET", url, **kwargs); accepted = []
        try:
            obj = json.loads(raw.decode("utf-8-sig")); source_rows = obj.get("data") or [] if market == "TWSE" else next((x.get("data") or [] for x in obj.get("tables", []) if x.get("data")), [])
            for r in source_rows:
                ticker = str(r[0] if market == "TWSE" else r[1]).strip()
                if ticker in wanted:
                    offset = 0 if market == "TWSE" else 1; accepted.append({"date": target.isoformat(), "ticker": ticker, "name": str(r[1+offset]).strip(), "market": market, "issued_shares": integer(r[3]), "foreign_holding_shares": integer(r[5]), "foreign_holding_ratio": number(r[7]), "foreign_available_shares": integer(r[4]), "foreign_available_ratio": number(r[6]), "field_semantics": "official foreign ownership stock level; separate from institutional flow", "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved})
        except Exception as exc: error = f"parse_{type(exc).__name__}"
        state = "accepted" if accepted else "no_rows" if status == 200 and not error else "blocked"; rows.extend(accepted); manifest.append({"family": "foreign_ownership", "market": market, "requested_date": target.isoformat(), "actual_source_date": target.isoformat() if accepted else "", "status": state, "row_count": len(accepted), "http_status": status, "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error})
    return rows, manifest


def fetch_taifex(target: date) -> tuple[list[dict], dict]:
    url = "https://www.bq888.taifex.com.tw/cht/3/futContractsDate"; raw, status, error, final_url, retrieved = request("GET", url, params={"queryType": "1", "doQuery": "1", "queryDate": target.strftime("%Y/%m/%d")}); rows = []
    try:
        soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser"); product = ""
        for tr in soup.select("tr"):
            vals = [c.get_text(" ", strip=True) for c in tr.select("th,td")]
            if len(vals) >= 15 and vals[0].isdigit(): product = vals[1]
            if product == "臺股期貨" and len(vals) >= 13 and vals[0] == "外資": rows.append({"date": target.isoformat(), "product": "TXF", "investor": "foreign", "oi_net_contracts": clean(vals[11]), "oi_net_amount": clean(vals[12]), "available_at_policy": "official post-close; next-trading-day eligible", "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved}); break
    except Exception as exc: error = f"parse_{type(exc).__name__}"
    state = "accepted" if rows else "no_rows" if status == 200 and not error else "blocked"
    return rows, {"family": "taifex_foreign_oi", "market": "TAIFEX", "requested_date": target.isoformat(), "actual_source_date": target.isoformat() if rows else "", "status": state, "row_count": len(rows), "http_status": status, "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error}


def fetch_global(target: date) -> tuple[list[dict], list[dict]]:
    cutoff = datetime.combine(target, dt_time(21, 30), TAIPEI).astimezone(timezone.utc); rows, manifest = [], []
    start = int((cutoff - timedelta(days=12)).timestamp()); end = int((cutoff + timedelta(days=1)).timestamp())
    for symbol, field in GLOBAL_SYMBOLS.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d"; raw, status, error, final_url, retrieved = request("GET", url); selected = None
        try:
            chart = json.loads(raw.decode("utf-8"))["chart"]["result"][0]; meta = chart.get("meta", {}); tz_name = meta.get("exchangeTimezoneName") or "UTC"; tz = ZoneInfo(tz_name); quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
            for i, ts in enumerate(chart.get("timestamp") or []):
                close = (quote.get("close") or [])[i]
                if close is not None and datetime.fromtimestamp(ts, timezone.utc) <= cutoff: selected = {"field": field, "symbol": symbol, "session_date": datetime.fromtimestamp(ts, tz).date().isoformat(), "exchange_timezone": tz_name, "session_timestamp_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "close": close, "source_quality": "trusted_nonofficial_yahoo_research_grade", "taiwan_decision_cutoff_utc": cutoff.isoformat(), "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved}
        except Exception as exc: error = f"parse_{type(exc).__name__}"
        if selected: rows.append(selected)
        manifest.append({"family": "global_market", "market": field, "requested_date": target.isoformat(), "actual_source_date": selected["session_date"] if selected else "", "status": "accepted" if selected else "blocked", "row_count": 1 if selected else 0, "http_status": status, "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error})
    return rows, manifest


def fetch_corporate_calendar(target: date, wanted: set[str]) -> tuple[list[dict], list[dict]]:
    rows, manifest = [], []
    url = "https://www.twse.com.tw/exchangeReport/TWT48U_ALL?response=json"; raw, status, error, final_url, retrieved = request("GET", url)
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
        for r in obj.get("data") or []:
            if len(r) > 3 and str(r[1]).strip() in wanted: rows.append({"ticker": str(r[1]).strip(), "name": str(r[2]).strip(), "market": "TWSE", "event_type": "cash_or_stock_dividend_candidate", "effective_date": str(r[3]).strip(), "event_terms": json.dumps(r[4:], ensure_ascii=False), "market_available_at": "", "pit_status": "calendar_candidate_market_available_at_blocked", "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved})
    except Exception as exc: error = f"parse_{type(exc).__name__}"
    manifest.append({"family": "corporate_action_guard", "market": "TWSE", "requested_date": target.isoformat(), "actual_source_date": target.isoformat(), "status": "accepted" if status == 200 and not error else "blocked", "row_count": len(rows), "http_status": status, "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error})
    tpex_url = "https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html"; tpex_raw, ts, te, tfinal, tret = request("GET", tpex_url)
    manifest.append({"family": "corporate_action_guard", "market": "TPEx", "requested_date": target.isoformat(), "actual_source_date": target.isoformat() if ts == 200 else "", "status": "accepted_calendar_page_hash_only" if ts == 200 else "blocked", "row_count": 0, "http_status": ts, "source_url": tfinal, "source_hash": sha(tpex_raw) if tpex_raw else "", "retrieved_at_utc": tret, "error": te, "blocked_reason": "browser-equivalent canonical rows not available in direct runner; no silent factor"})
    return rows, manifest


def fetch_tdcc_if_new(output_root: Path, wanted: set[str]) -> tuple[list[dict], dict]:
    url = "https://openapi.tdcc.com.tw/v1/opendata/1-5"; raw, status, error, final_url, retrieved = request("GET", url); rows = []; publication = ""
    try:
        source = json.loads(raw.decode("utf-8-sig")); publication = str(source[0].get("\ufeff資料日期", source[0].get("資料日期", ""))) if source else ""
        existing = output_root / "tdcc" / f"{publication}.csv.gz"
        if tdcc_should_append(publication, output_root):
            for r in source:
                ticker = str(r.get("證券代號", "")).strip()
                if ticker in wanted: rows.append({"publication_date": publication, "ticker": ticker, "holding_bucket": r.get("持股分級", ""), "holder_count": r.get("人數", ""), "shares": r.get("股數", ""), "share_pct": r.get("占集保庫存數比例%", ""), "available_at_policy": "actual weekly publication date; never daily backfill", "source_url": final_url, "source_hash": sha(raw), "retrieved_at_utc": retrieved})
            atomic_csv_gz(existing, rows, list(rows[0]) if rows else ["publication_date"])
        state = "accepted_new_week" if rows else "no_new_release"
    except Exception as exc: error = f"parse_{type(exc).__name__}"; state = "blocked"
    return rows, {"family": "tdcc_holder_distribution", "market": "TDCC", "requested_date": "", "actual_source_date": publication, "status": state, "row_count": len(rows), "http_status": status, "source_url": final_url, "source_hash": sha(raw) if raw else "", "retrieved_at_utc": retrieved, "error": error}


def tdcc_should_append(publication: str, output_root: Path) -> bool:
    return bool(publication) and not (output_root / "tdcc" / f"{publication}.csv.gz").exists()


FAMILY_GROUPS = {
    "price": {"official_raw_execution_ohlcv"},
    "chips": {"institutional", "margin_short", "securities_lending"},
    "foreign_ownership": {"foreign_ownership"},
    "taifex": {"taifex_foreign_oi"},
    "global": {"global_market"},
    "corporate_action": {"corporate_action_guard"},
    "tdcc": {"tdcc_holder_distribution"},
}


def _existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_date(target: date, output_root: Path, scope_path: Path, calendar_state: str | None = None, retry_families: set[str] | None = None) -> dict:
    target_dir = output_root / "daily" / target.strftime("%Y/%m/%d"); manifest_path = target_dir / "manifest.json"
    wanted, _ = load_scope(scope_path)
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if retry_families and manifest_path.exists() else {}
    if retry_families and not previous:
        raise IncompleteSourceError("family-only retry requires an existing manifest")
    selected = set(FAMILY_GROUPS) if not retry_families else retry_families
    unknown = selected - set(FAMILY_GROUPS)
    if unknown:
        raise ValueError(f"unknown retry families: {sorted(unknown)}")
    if calendar_state is None:
        open_dates, closed_dates = fetch_twse_calendar(); calendar_state = classify_calendar_day(target, open_dates, closed_dates)
    if calendar_state in {"scheduled_closed", "weekend_closed"}:
        payload = {"requested_date": target.isoformat(), "status": "skipped_market_closed", "calendar_state": calendar_state, "future_data_violation_count": 0, **FLAGS}; atomic_json(manifest_path, payload); return payload
    old_sources = previous.get("sources", [])
    replaced = set().union(*(FAMILY_GROUPS[name] for name in selected))
    manifests = [row for row in old_sources if row.get("family") not in replaced]
    price_rows = _existing_rows(target_dir / "official_raw_execution_ohlcv.csv.gz")
    if "price" in selected:
        price_rows, price_manifest = fetch_price(target, wanted)
        manifests.extend(price_manifest)
    market_states = {r["market"]: r["status"] for r in manifests}
    if all(market_states.get(x) == "no_rows" for x in ("TWSE", "TPEx")):
        payload = {"requested_date": target.isoformat(), "status": "skipped_market_closed", "calendar_state": "official_market_data_both_no_rows", "sources": manifests, "future_data_violation_count": 0, **FLAGS}; atomic_json(manifest_path, payload); return payload
    if any(market_states.get(x) != "accepted" for x in ("TWSE", "TPEx")):
        payload = {"requested_date": target.isoformat(), "status": "incomplete_source", "calendar_state": calendar_state, "sources": manifests, "future_data_violation_count": 0, **FLAGS}; atomic_json(manifest_path, payload); raise IncompleteSourceError("official price markets incomplete")
    chip_rows = _existing_rows(target_dir / "institutional_margin_lending.csv.gz")
    ownership_rows = _existing_rows(target_dir / "foreign_ownership.csv.gz")
    taifex_rows = _existing_rows(target_dir / "taifex_market_context.csv.gz")
    global_rows = _existing_rows(target_dir / "global_market_context.csv.gz")
    action_rows = _existing_rows(target_dir / "corporate_action_guard.csv.gz")
    global_manifest = [r for r in manifests if r.get("family") == "global_market"]
    if "chips" in selected:
        chip_rows, rows = fetch_chip_family(target, wanted); manifests.extend(rows)
    if "foreign_ownership" in selected:
        ownership_rows, rows = fetch_foreign_ownership(target, wanted); manifests.extend(rows)
    if "taifex" in selected:
        taifex_rows, row = fetch_taifex(target); manifests.append(row)
    if "global" in selected:
        global_rows, global_manifest = fetch_global(target); manifests.extend(global_manifest)
    if "corporate_action" in selected:
        action_rows, rows = fetch_corporate_calendar(target, wanted); manifests.extend(rows)
    if "tdcc" in selected:
        _, row = fetch_tdcc_if_new(output_root, wanted); manifests.append(row)
    mandatory = [r for r in manifests if r["family"] in {"official_raw_execution_ohlcv", "institutional", "margin_short", "securities_lending", "foreign_ownership", "taifex_foreign_oi"}]
    for row in mandatory:
        if row["status"] == "accepted" and row.get("actual_source_date") != target.isoformat():
            row["status"] = "blocked"; row["error"] = "stale_actual_source_date_rejected"
    # Once TWSE and TPEx prices prove the market was open, every mandatory
    # family must contain that date. A no_rows response is source-incomplete,
    # not a market-closed signal.
    blocked = [r for r in mandatory if r["status"] != "accepted"]
    fields = {
        "official_raw_execution_ohlcv.csv.gz": price_rows,
        "institutional_margin_lending.csv.gz": chip_rows,
        "foreign_ownership.csv.gz": ownership_rows,
        "taifex_market_context.csv.gz": taifex_rows,
        "global_market_context.csv.gz": global_rows,
        "corporate_action_guard.csv.gz": action_rows,
    }
    file_groups = {"official_raw_execution_ohlcv.csv.gz": "price", "institutional_margin_lending.csv.gz": "chips", "foreign_ownership.csv.gz": "foreign_ownership", "taifex_market_context.csv.gz": "taifex", "global_market_context.csv.gz": "global", "corporate_action_guard.csv.gz": "corporate_action"}
    for name, rows in fields.items():
        if file_groups[name] in selected:
            atomic_csv_gz(target_dir / name, rows, list(rows[0]) if rows else ["date"])
    payload = {"requested_date": target.isoformat(), "actual_market_date": target.isoformat(), "status": "incomplete_source" if blocked else "accepted", "calendar_state": calendar_state, "candidate_scope_count": len(wanted), "retry_families": sorted(retry_families or []), "actual_source_dates": {r["family"] + ":" + r.get("market", ""): r.get("actual_source_date", "") for r in manifests}, "latest_completed_global_sessions": {r["market"]: r.get("actual_source_date", "") for r in global_manifest}, "source_counts": {"accepted": sum(str(r["status"]).startswith("accepted") for r in manifests), "no_rows": sum(r["status"] in {"no_rows", "no_new_release"} for r in manifests), "blocked": sum(r["status"] == "blocked" for r in manifests)}, "sources": manifests, "future_data_violation_count": 0, "法人／大戶籌碼代理分數": "source_components_only_weights_not_defined", "raw_execution_and_adjusted_analysis_separate": True, **FLAGS}
    atomic_json(manifest_path, payload)
    if blocked: raise IncompleteSourceError(f"mandatory source incomplete: {[(r['family'], r.get('market')) for r in blocked]}")
    return payload


def date_range(start: date, end: date) -> list[date]:
    out = []; d = start
    while d <= end: out.append(d); d += timedelta(days=1)
    return out


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--date"); p.add_argument("--backfill-start"); p.add_argument("--backfill-end"); p.add_argument("--retry-families", default=""); p.add_argument("--output-root", type=Path, default=Path("data/risk_features")); p.add_argument("--scope", type=Path, default=Path("data/risk_features/frozen_candidate_scope.csv")); args = p.parse_args()
    if args.backfill_start or args.backfill_end:
        if not (args.backfill_start and args.backfill_end): raise SystemExit("both backfill dates required")
        targets = date_range(date.fromisoformat(args.backfill_start), date.fromisoformat(args.backfill_end))
    else: targets = [date.fromisoformat(args.date) if args.date else datetime.now(TAIPEI).date()]
    failed = False
    for target in targets:
        retry_families = {x.strip() for x in args.retry_families.split(",") if x.strip()} or None
        try: run_date(target, args.output_root, args.scope, retry_families=retry_families)
        except IncompleteSourceError as exc: print(f"incomplete_source {target}: {exc}"); failed = True
    raise SystemExit(2 if failed else 0)


if __name__ == "__main__": main()
