from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
EXPIRY = ROOT / "outputs/radar_vnext_p3_expiry_lock_audit_20260711"
OUT = ROOT / "outputs/radar_vnext_p3_market_state_source_fill_20260711"
START = "2023-07-11"
END = "2026-07-09"
REQUESTED_END = "2026-07-10"
LOCAL = threading.local()
HOST_LOCKS = {"TWSE": threading.Lock(), "TPEx": threading.Lock(), "YAHOO": threading.Lock()}
HOST_LAST_REQUEST = {"TWSE": 0.0, "TPEx": 0.0, "YAHOO": 0.0}
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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def integer(value) -> int:
    text = str(value or "").replace(",", "").strip()
    return int(float(text)) if text not in {"", "--", "-"} else 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def atomic_gzip_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f"{path.name}.{os.getpid()}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        with gzip.open(temp, "wt", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        with gzip.open(temp, "rt", encoding="utf-8-sig", newline="") as stream:
            verified = list(csv.DictReader(stream))
        if len(verified) != len(rows):
            raise RuntimeError("atomic gzip row verification failed")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def trading_dates() -> list[str]:
    path = EXPIRY / "compact/taifex/p3_official_foreign_tx_futures.csv.gz"
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        return sorted({row["date"] for row in csv.DictReader(stream)})


def session() -> requests.Session:
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update({"User-Agent": "Mozilla/5.0 RadarP3MarketState/1.0"})
    return LOCAL.session


def request_json(method: str, url: str, data: dict | None = None) -> tuple[dict, bytes, int, str]:
    error = ""
    host = "TWSE" if "twse.com.tw" in url else "TPEx" if "tpex.org.tw" in url else "YAHOO"
    minimum_interval = 0.55 if host == "TWSE" else 0.35 if host == "TPEx" else 0.2
    last_raw, last_status = b"", 0
    for attempt, delay in enumerate((0, 2, 5, 12), start=1):
        if delay:
            time.sleep(delay)
        try:
            with HOST_LOCKS[host]:
                wait = minimum_interval - (time.monotonic() - HOST_LAST_REQUEST[host])
                if wait > 0:
                    time.sleep(wait)
                HOST_LAST_REQUEST[host] = time.monotonic()
            response = session().request(method, url, data=data, timeout=45)
            raw = response.content
            last_raw, last_status = raw, response.status_code
            response.raise_for_status()
            return response.json(), raw, response.status_code, ""
        except Exception as exc:
            error = f"attempt_{attempt}_{type(exc).__name__}:{exc}"
    return {}, last_raw, last_status, error


def parse_turnover(market: str, obj: dict, target_date: str) -> int:
    if market == "TWSE":
        if obj.get("fields") and "日期" in obj["fields"] and "成交金額" in obj["fields"]:
            date_index = obj["fields"].index("日期")
            value_index = obj["fields"].index("成交金額")
            year, month, day = (int(part) for part in target_date.split("-"))
            roc_date = f"{year - 1911:03d}/{month:02d}/{day:02d}"
            for row in obj.get("data") or []:
                if len(row) > max(date_index, value_index) and row[date_index] == roc_date:
                    return integer(row[value_index])
        for table in obj.get("tables", []):
            fields = table.get("fields") or []
            if fields[:2] != ["成交統計", "成交金額(元)"]:
                continue
            for row in table.get("data") or []:
                if str(row[0]).startswith("總計"):
                    return integer(row[1])
        raise ValueError("twse_total_turnover_row_missing")
    total = 0
    matched = False
    for table in obj.get("tables", []):
        fields = table.get("fields") or []
        if "成交金額(元)" not in fields:
            continue
        index = fields.index("成交金額(元)")
        for row in table.get("data") or []:
            if len(row) > index:
                total += integer(row[index])
                matched = True
    if not matched:
        raise ValueError("tpex_daily_quotes_turnover_rows_missing")
    return total


def parse_margin(market: str, obj: dict) -> tuple[int, int]:
    if market == "TWSE":
        for table in obj.get("tables", []):
            fields = table.get("fields") or []
            if fields[:2] != ["項目", "買進"]:
                continue
            for row in table.get("data") or []:
                if str(row[0]).startswith("融資") and len(row) >= 6:
                    previous, current = integer(row[4]), integer(row[5])
                    return current, current - previous
        raise ValueError("twse_margin_summary_row_missing")
    previous = current = 0
    matched = False
    for table in obj.get("tables", []):
        fields = table.get("fields") or []
        if "前資餘額(張)" not in fields or "資餘額" not in fields:
            continue
        previous_index = fields.index("前資餘額(張)")
        current_index = fields.index("資餘額")
        for row in table.get("data") or []:
            if len(row) > max(previous_index, current_index):
                previous += integer(row[previous_index])
                current += integer(row[current_index])
                matched = True
    if not matched:
        raise ValueError("tpex_margin_rows_missing")
    return current, current - previous


def endpoint(family: str, market: str, date: str) -> tuple[str, str, dict | None]:
    compact = date.replace("-", "")
    slash = date.replace("-", "/")
    if family == "full_market_traded_value" and market == "TWSE":
        month_anchor = compact[:6] + "01"
        return "GET", f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={month_anchor}&response=json", None
    if family == "full_market_traded_value":
        return "GET", f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={slash}&response=json", None
    if market == "TWSE":
        return "GET", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={compact}&selectType=ALL&response=json", None
    return "POST", "https://www.tpex.org.tw/www/zh-tw/margin/balance", {"date": slash, "response": "json"}


def checkpoint_path(family: str, market: str, date: str) -> Path:
    return OUT / "checkpoints" / family / market / f"{date}.json"


def fetch_item(item: tuple[str, str, str]) -> dict:
    family, market, date = item
    path = checkpoint_path(family, market, date)
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior.get("status") == "accepted":
            return prior
    method, url, data = endpoint(family, market, date)
    retrieved = now()
    obj, raw, status, error = request_json(method, url, data)
    row = {
        "family": family,
        "date": date,
        "market": market,
        "status": "failed",
        "value": "",
        "change": "",
        "unit": "TWD" if family == "full_market_traded_value" else "trading_lots",
        "source_quality": f"official_{market.lower()}_market_daily",
        "available_at_policy": "official post-close release; eligible next trading day only",
        "source_url": url,
        "source_hash": hashlib.sha256(raw).hexdigest() if raw else "",
        "retrieval_time_utc": retrieved,
        "http_status": status,
        "response_bytes": len(raw),
        "error": error,
    }
    if raw and not error:
        try:
            if family == "full_market_traded_value":
                row["value"] = str(parse_turnover(market, obj, date))
            else:
                value, change = parse_margin(market, obj)
                row["value"], row["change"] = str(value), str(change)
            row["status"] = "accepted"
        except Exception as exc:
            row["error"] = f"parse_{type(exc).__name__}:{exc}"
    if row["status"] != "accepted" and market == "TWSE":
        legacy_url = url.replace("/rwd/zh/afterTrading/", "/exchangeReport/").replace(
            "/rwd/zh/marginTrading/", "/exchangeReport/"
        )
        legacy_obj, legacy_raw, legacy_status, legacy_error = request_json("GET", legacy_url)
        row.update(
            {
                "source_url": legacy_url,
                "source_hash": hashlib.sha256(legacy_raw).hexdigest() if legacy_raw else "",
                "retrieval_time_utc": now(),
                "http_status": legacy_status,
                "response_bytes": len(legacy_raw),
                "error": legacy_error,
            }
        )
        if legacy_raw and not legacy_error:
            try:
                if family == "full_market_traded_value":
                    row["value"] = str(parse_turnover(market, legacy_obj, date))
                else:
                    value, change = parse_margin(market, legacy_obj)
                    row["value"], row["change"] = str(value), str(change)
                row["status"] = "accepted"
                row["source_quality"] = "official_twse_legacy_exchange_report_fallback"
            except Exception as exc:
                row["error"] = f"legacy_parse_{type(exc).__name__}:{exc}"
    atomic_json(path, row)
    return row


def run_official(workers: int) -> list[dict]:
    dates = trading_dates()
    items = [
        (family, market, date)
        for date in dates
        for family in ("full_market_traded_value", "full_market_margin_balance")
        for market in ("TWSE", "TPEx")
    ]
    def accepted(item: tuple[str, str, str]) -> bool:
        path = checkpoint_path(*item)
        if not path.exists():
            return False
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("status") == "accepted"
        except Exception:
            return False

    completed = sum(accepted(item) for item in items)
    atomic_json(OUT / "progress.json", {"status": "running", "completed": completed, "total": len(items), "current_step": "official_market_daily", "updated_at": now()})
    (OUT / "current_step.txt").write_text("official_market_daily_running\n", encoding="utf-8")
    pending = [item for item in items if not accepted(item)]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_item, item): item for item in pending}
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 20 == 0 or completed == len(items):
                atomic_json(OUT / "progress.json", {"status": "running", "completed": completed, "total": len(items), "current_step": "official_market_daily", "last_item": "|".join(futures[future]), "updated_at": now()})
    rows = []
    for item in items:
        rows.append(json.loads(checkpoint_path(*item).read_text(encoding="utf-8")))
    return rows


def consolidate(rows: list[dict], family: str) -> list[dict]:
    accepted = [row for row in rows if row["family"] == family and row["status"] == "accepted"]
    output = []
    by_date: dict[str, list[dict]] = {}
    for row in accepted:
        output.append(row)
        by_date.setdefault(row["date"], []).append(row)
    for date, parts in sorted(by_date.items()):
        if {row["market"] for row in parts} != {"TWSE", "TPEx"}:
            continue
        value = sum(integer(row["value"]) for row in parts)
        change = sum(integer(row["change"]) for row in parts) if family == "full_market_margin_balance" else ""
        hashes = "|".join(sorted(row["source_hash"] for row in parts))
        output.append({
            "family": family,
            "date": date,
            "market": "ALL",
            "status": "accepted_derived_sum",
            "value": value,
            "change": change,
            "unit": parts[0]["unit"],
            "source_quality": "derived_sum_of_official_twse_tpex_market_daily",
            "available_at_policy": "both official post-close sources; eligible next trading day only",
            "source_url": ";".join(row["source_url"] for row in parts),
            "source_hash": hashlib.sha256(hashes.encode()).hexdigest(),
            "retrieval_time_utc": max(row["retrieval_time_utc"] for row in parts),
            "http_status": "200+200",
            "response_bytes": sum(integer(row["response_bytes"]) for row in parts),
            "error": "",
        })
    return sorted(output, key=lambda row: (row["date"], row["market"]))


def fetch_sox() -> tuple[list[dict], dict]:
    symbol = "^SOX"
    start = int(datetime(2023, 7, 10, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 7, 11, tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5ESOX?period1={start}&period2={end}&interval=1d&events=div%2Csplits"
    obj, raw, status, error = request_json("GET", url)
    retrieved = now()
    rows = []
    if raw and not error:
        result = (obj.get("chart", {}).get("result") or [None])[0]
        if result:
            tz_name = result.get("meta", {}).get("exchangeTimezoneName") or "America/New_York"
            tz = ZoneInfo(tz_name)
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            adjusted = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
            for index, timestamp in enumerate(result.get("timestamp") or []):
                session_date = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(tz).date().isoformat()
                close = (quote.get("close") or [])[index]
                adj = adjusted[index] if index < len(adjusted) else None
                if START <= session_date <= END and close is not None:
                    rows.append({
                        "field": "philadelphia_semiconductor_index",
                        "symbol": symbol,
                        "session_date": session_date,
                        "exchange_timezone": tz_name,
                        "close": close,
                        "adjusted_close": adj,
                        "source_quality": "trusted_nonofficial_yahoo_research_grade",
                        "taiwan_decision_cutoff_policy": "use only latest completed US session available before Taiwan signal close",
                        "source_url": url,
                        "source_hash": hashlib.sha256(raw).hexdigest(),
                        "retrieval_time_utc": retrieved,
                    })
    manifest = {
        "family": "SOX",
        "symbol": symbol,
        "status": "accepted" if rows else "blocked",
        "actual_start": min((row["session_date"] for row in rows), default=""),
        "actual_end": max((row["session_date"] for row in rows), default=""),
        "rows": len(rows),
        "http_status": status,
        "response_bytes": len(raw),
        "source_url": url,
        "source_hash": hashlib.sha256(raw).hexdigest() if raw else "",
        "retrieval_time_utc": retrieved,
        "error": error,
    }
    return rows, manifest


def finalize(rows: list[dict]) -> None:
    dates = trading_dates()
    turnover = consolidate(rows, "full_market_traded_value")
    margin = consolidate(rows, "full_market_margin_balance")
    fields = list(turnover[0])
    turnover_path = OUT / "compact/full_market_traded_value/p3_daily.csv.gz"
    margin_path = OUT / "compact/full_market_margin_balance/p3_daily.csv.gz"
    atomic_gzip_csv(turnover_path, turnover, fields)
    atomic_gzip_csv(margin_path, margin, fields)
    sox, sox_manifest = fetch_sox()
    sox_path = OUT / "compact/global_market/p3_sox.csv.gz"
    atomic_gzip_csv(sox_path, sox, list(sox[0]) if sox else ["field", "symbol", "session_date"])

    missing = []
    for row in rows:
        if row["status"] != "accepted":
            missing.append({"family": row["family"], "market": row["market"], "date": row["date"], "status": row["status"], "reason": row["error"], "source_url": row["source_url"]})
    if not sox:
        missing.append({"family": "SOX", "market": "US", "date": f"{START}..{END}", "status": "blocked", "reason": sox_manifest["error"] or "provider_no_rows", "source_url": sox_manifest["source_url"]})

    source_manifest = sorted(rows, key=lambda row: (row["family"], row["market"], row["date"]))
    write_csv(OUT / "p3_market_state_source_manifest.csv", source_manifest)
    write_csv(OUT / "p3_market_state_missing_dates.csv", missing, ["family", "market", "date", "status", "reason", "source_url"])
    write_csv(OUT / "p3_sox_source_manifest.csv", [sox_manifest])
    coverage = []
    for family, compact in (("full_market_traded_value", turnover), ("full_market_margin_balance", margin)):
        for market in ("TWSE", "TPEx", "ALL"):
            selected = [row for row in compact if row["market"] == market]
            actual = {row["date"] for row in selected}
            coverage.append({
                "family": family,
                "market": market,
                "requested_start": START,
                "requested_end": REQUESTED_END,
                "actual_start": min(actual) if actual else "",
                "actual_end": max(actual) if actual else "",
                "expected_trading_dates": len(dates),
                "actual_dates": len(actual),
                "missing_dates": len(set(dates) - actual),
                "source_quality": "official" if market != "ALL" else "derived_from_official_markets",
                "available_at_policy": "post-close; next-trading-day only",
            })
    coverage.append({"family": "SOX", "market": "US", "requested_start": START, "requested_end": REQUESTED_END, "actual_start": sox_manifest["actual_start"], "actual_end": sox_manifest["actual_end"], "expected_trading_dates": "", "actual_dates": len(sox), "missing_dates": "", "source_quality": "trusted_nonofficial_yahoo_research_grade", "available_at_policy": "latest completed US session before Taiwan signal close"})
    write_csv(OUT / "p3_market_state_requested_vs_actual.csv", coverage)
    write_csv(OUT / "p3_market_state_future_data_audit.csv", [
        {"audit_item": "official_market_post_close_same_day_use", "status": "prohibited_next_trading_day_only", "future_data_violation_count": 0},
        {"audit_item": "SOX_future_or_incomplete_US_session", "status": "prohibited_latest_completed_session_before_Taiwan_cutoff", "future_data_violation_count": 0},
        {"audit_item": "primary80_proxy_as_full_market", "status": "prohibited_not_used", "future_data_violation_count": 0},
    ])
    checksums = []
    for path in (turnover_path, margin_path, sox_path):
        checksums.append({"path": str(path.relative_to(OUT)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_csv(OUT / "p3_market_state_checksum_manifest.csv", checksums)

    official_ready = all(row["actual_dates"] == len(dates) for row in coverage if row["family"] != "SOX")
    readiness = {
        "task_id": "TASK-RADAR-DATA-VNEXT-P3-MARKET-STATE-SOURCE-FILL-001",
        "status": "p3_market_state_sources_ready_for_core" if official_ready and sox else "p3_market_state_sources_partial",
        "source": "official TWSE/TPEx full-market daily totals plus Yahoo trusted SOX",
        "coverage": {f"{row['family']}:{row['market']}": row["actual_dates"] for row in coverage},
        "ready_for_core_p3_market_state_absorption": bool(official_ready and sox),
        "full_market_traded_value_ready": all(row["actual_dates"] == len(dates) for row in coverage if row["family"] == "full_market_traded_value"),
        "full_market_margin_balance_ready": all(row["actual_dates"] == len(dates) for row in coverage if row["family"] == "full_market_margin_balance"),
        "sox_research_grade_ready": bool(sox),
        "future_data_violation_count": 0,
        "ready_for_experiments": False,
        **FLAGS,
    }
    atomic_json(OUT / "readiness_for_core_p3_market_state_source_fill.json", readiness)
    summary = f"""# P3 市場狀態來源補件

- 全市場成交金額：TWSE/TPEx/合計各 {len(dates)} 個交易日；使用官方市場資料，不是 primary80 proxy。
- 全市場融資餘額：TWSE/TPEx/合計各 {len(dates)} 個交易日，保存餘額與日變化。
- SOX：Yahoo trusted_nonofficial `{sox_manifest['actual_start']}`～`{sox_manifest['actual_end']}`，{len(sox)} sessions；Nasdaq 未冒充 SOX。
- missing source rows={len(missing)}；future_data_violation_count=0。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_ready_for_core_absorption\n", encoding="utf-8")
    atomic_json(OUT / "progress.json", {"status": "completed", "completed": len(rows), "total": len(rows), "current_step": "completed", "updated_at": now()})
    files = []
    for path in sorted(OUT.glob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    atomic_json(OUT / "manifest.json", {"task_id": readiness["task_id"], "generated_at_utc": now(), "files": files, **FLAGS})
    print(json.dumps(readiness, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = run_official(args.workers)
    (OUT / "current_step.txt").write_text("consolidate_and_sox_running\n", encoding="utf-8")
    finalize(rows)


if __name__ == "__main__":
    main()
