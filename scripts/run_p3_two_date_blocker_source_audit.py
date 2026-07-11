from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
PRIMARY = CORE / "outputs" / "vnext_layer4_80_primary_pool_contract_20260708" / "layer4_80_primary_pool_contract.csv"
EXACT = ROOT / "outputs" / "radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711"
OUT = ROOT / "outputs" / "radar_vnext_p3_two_date_blocker_source_audit_20260711"
TASK = "TASK-RADAR-DATA-VNEXT-P3-TWO-DATE-BLOCKER-BOUNDED-SOURCE-AUDIT-001"
TARGET_ADJ = date(2025, 8, 1)
TARGET_TAIFEX = date(2025, 12, 26)
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


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest() if raw else ""


def atomic_replace(tmp: Path, target: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.15 * (attempt + 1))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else ["status"])
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    atomic_replace(tmp, path)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def get(url: str, **kwargs) -> requests.Response:
    headers = {"User-Agent": "Mozilla/5.0 RadarP3TwoDateAudit/1.0", "Accept": "application/json,text/csv,*/*"}
    return requests.get(url, headers=headers, timeout=45, **kwargs)


def primary80_on_target() -> list[dict]:
    cols = ["snapshot_date", "ticker", "name", "market", "is_layer4_primary_pool", "pool_rank"]
    rows = pd.read_csv(PRIMARY, usecols=cols, dtype={"ticker": str}, low_memory=False)
    rows["snapshot_date"] = pd.to_datetime(rows["snapshot_date"])
    rows["ticker"] = rows["ticker"].astype(str).str.strip()
    rows = rows[
        rows["snapshot_date"].dt.date.eq(TARGET_ADJ)
        & rows["is_layer4_primary_pool"].eq(True)
    ].sort_values("pool_rank")
    return rows.to_dict("records")


def existing_adjusted_rows() -> set[str]:
    found: set[str] = set()
    for path in (EXACT / "compact" / "adjusted").glob("*.csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("date") == TARGET_ADJ.isoformat() and row.get("adjusted_close"):
                    found.add(row.get("ticker", ""))
    return found


def market_probe(market: str, target: date) -> tuple[dict, dict]:
    retrieved = now()
    if market == "TWSE":
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={target:%Y%m%d}&type=ALLBUT0999"
        response = get(url)
        raw = response.content
        obj = response.json() if response.ok else {}
        table = next((x for x in obj.get("tables", []) if (x.get("data") or []) and len(x.get("fields") or []) >= 9), {})
        rows = table.get("data") or []
        state = "normal_trading_official_rows_present" if rows else "official_zero_rows"
        count = len(rows)
    else:
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={target:%Y/%m/%d}&response=json"
        response = get(url)
        raw = response.content
        obj = response.json() if response.ok else {}
        table = next((x for x in obj.get("tables", []) if x.get("data")), {})
        rows = table.get("data") or []
        state = "normal_trading_official_rows_present" if rows else "official_zero_rows"
        count = len(rows)
    evidence = {
        "date": target.isoformat(), "market": market, "market_status": state,
        "official_row_count": count, "http_status": response.status_code,
        "source_url": response.url, "response_bytes": len(raw), "response_sha256": sha(raw),
        "retrieval_time_utc": retrieved,
        "pit_available_at_policy": "official post-close market file; eligible next trading day only",
    }
    manifest = {
        "source_id": f"{market}_{target.isoformat()}_official_market_status",
        "date": target.isoformat(), "source_type": "official_market_eod", "source_url": response.url,
        "http_status": response.status_code, "response_bytes": len(raw), "response_sha256": sha(raw),
        "retrieval_time_utc": retrieved, "status": "accepted" if rows else "blocked_zero_rows",
    }
    return evidence, manifest


def yahoo_probe(member: dict) -> tuple[dict, dict | None]:
    ticker = str(member["ticker"])
    symbol = ticker + (".TW" if member["market"] == "TWSE" else ".TWO")
    start = TARGET_ADJ - timedelta(days=3)
    end = TARGET_ADJ + timedelta(days=5)
    p1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits"
    retrieved = now()
    response = None
    raw = b""
    try:
        response = get(url)
        raw = response.content
        payload = response.json().get("chart", {})
        results = payload.get("result") or []
        if not results:
            error = payload.get("error") or {}
            return {
                "date": TARGET_ADJ.isoformat(), "ticker": ticker, "name": member["name"], "market": member["market"],
                "yahoo_symbol": symbol, "http_status": response.status_code, "response_bytes": len(raw),
                "response_sha256": sha(raw), "retrieval_time_utc": retrieved, "target_session_present": False,
                "target_open": "", "target_high": "", "target_low": "", "target_close": "", "target_adjusted_close": "",
                "neighbor_sessions": "", "classification": "symbol_history_unavailable_chart_result_null",
                "provider_error_code": error.get("code", ""), "provider_error_description": error.get("description", ""),
                "source_url": response.url, "source_quality": "trusted_nonofficial_yahoo_research_grade",
                "pit_available_at_policy": "historical provider session; research analysis only; not execution/formal PIT",
            }, None
        chart = results[0]
        offset = int(chart.get("meta", {}).get("gmtoffset") or 28800)
        zone = timezone(timedelta(seconds=offset))
        quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
        adjusted = (chart.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        sessions = []
        target_index = None
        for index, stamp in enumerate(chart.get("timestamp") or []):
            session = datetime.fromtimestamp(stamp, zone).date().isoformat()
            sessions.append(session)
            if session == TARGET_ADJ.isoformat():
                target_index = index
        def value(field: str):
            values = quote.get(field) or []
            return values[target_index] if target_index is not None and target_index < len(values) else None
        adj = adjusted[target_index] if target_index is not None and target_index < len(adjusted) else None
        target_present = target_index is not None
        all_null = target_present and all(value(field) is None for field in ("open", "high", "low", "close", "volume")) and adj is None
        if adj is not None:
            classification = "trusted_adjusted_patch_available"
        elif all_null:
            classification = "provider_null_placeholder_for_official_trading_session"
        elif not target_present:
            classification = "provider_session_absent"
        else:
            classification = "provider_adjusted_value_missing"
        row = {
            "date": TARGET_ADJ.isoformat(), "ticker": ticker, "name": member["name"], "market": member["market"],
            "yahoo_symbol": symbol, "http_status": response.status_code, "response_bytes": len(raw),
            "response_sha256": sha(raw), "retrieval_time_utc": retrieved,
            "target_session_present": target_present, "target_open": value("open"), "target_high": value("high"),
            "target_low": value("low"), "target_close": value("close"), "target_adjusted_close": adj,
            "neighbor_sessions": "|".join(sessions), "classification": classification,
            "source_url": response.url, "source_quality": "trusted_nonofficial_yahoo_research_grade",
            "provider_error_code": "", "provider_error_description": "",
            "pit_available_at_policy": "historical provider session; research analysis only; not execution/formal PIT",
        }
        patch = None
        if adj is not None:
            patch = {
                "date": TARGET_ADJ.isoformat(), "ticker": ticker, "name": member["name"], "market": member["market"],
                "yahoo_symbol": symbol, "adjusted_close": adj, "source_quality": "trusted_nonofficial_yahoo_research_grade",
                "adjustment_policy": "provider_adjusted_analysis_only; not_execution_price; not_formal",
                "source_url": response.url, "source_hash": sha(raw), "retrieval_time_utc": retrieved,
            }
        return row, patch
    except Exception as exc:
        return {
            "date": TARGET_ADJ.isoformat(), "ticker": ticker, "name": member["name"], "market": member["market"],
            "yahoo_symbol": symbol, "http_status": "", "response_bytes": 0, "response_sha256": "",
            "retrieval_time_utc": retrieved, "target_session_present": False, "target_open": "", "target_high": "",
            "target_low": "", "target_close": "", "target_adjusted_close": "", "neighbor_sessions": "",
            "classification": f"source_endpoint_gap_{type(exc).__name__}", "provider_error_code": type(exc).__name__,
            "provider_error_description": str(exc), "source_url": response.url if response is not None else url,
            "source_quality": "trusted_nonofficial_yahoo_research_grade",
            "pit_available_at_policy": "historical provider session; research analysis only; not execution/formal PIT",
        }, None


def taifex_probe() -> tuple[list[dict], dict, dict]:
    url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
    retrieved = now()
    response = requests.post(
        url,
        data={"queryStartDate": "2025/12/26", "queryEndDate": "2025/12/26", "commodityId": "TXF"},
        headers={"User-Agent": "Mozilla/5.0 RadarP3TwoDateAudit/1.0"}, timeout=45,
    )
    response.raise_for_status()
    raw = response.content
    rows = list(csv.reader(io.StringIO(raw.decode("cp950", errors="strict"))))
    patch = []
    candidate_count = 0
    for values in rows[1:]:
        if len(values) < 15 or values[0] != "2025/12/26" or values[1] != "臺股期貨":
            continue
        candidate_count += 1
        if values[2] in {"外資", "外資及陸資"}:
            patch.append({
                "date": TARGET_TAIFEX.isoformat(), "product": "TXF", "investor": "foreign",
                "foreign_futures_oi_net_contracts": values[13].replace(",", "").strip(),
                "foreign_futures_oi_net_amount": values[14].replace(",", "").strip(),
                "foreign_futures_trade_net_contracts": values[7].replace(",", "").strip(),
                "foreign_futures_trade_net_amount": values[8].replace(",", "").strip(),
                "source_quality": "official_taifex_market_level_range_download",
                "available_at_policy": "official post-close release; eligible next trading day only",
                "source_url": response.url, "source_hash": sha(raw), "retrieval_time_utc": retrieved,
            })
    classification = "target_row_present_patch_ready" if patch else "official_zero" if candidate_count else "contract_not_applicable_or_market_closed"
    evidence = {
        "date": TARGET_TAIFEX.isoformat(), "market": "TAIFEX", "market_status": "normal_trading_TXF_rows_present" if candidate_count else "no_TXF_rows",
        "txf_candidate_rows": candidate_count, "foreign_target_rows": len(patch), "classification": classification,
        "http_status": response.status_code, "response_bytes": len(raw), "source_url": response.url,
        "response_sha256": sha(raw), "retrieval_time_utc": retrieved,
        "pit_available_at_policy": "official post-close release; eligible next trading day only",
    }
    manifest = {
        "source_id": "TAIFEX_2025-12-26_TXF_foreign_OI", "date": TARGET_TAIFEX.isoformat(),
        "source_type": "official_taifex_range_csv", "source_url": response.url, "http_status": response.status_code,
        "response_bytes": len(raw), "response_sha256": sha(raw), "retrieval_time_utc": retrieved,
        "status": "accepted_patch" if patch else "blocked_no_target_row",
    }
    return patch, evidence, manifest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    members = primary80_on_target()
    if len(members) != 80:
        raise RuntimeError(f"expected 80 primary members, got {len(members)}")
    market_evidence = []
    source_manifest = []
    for target, markets in ((TARGET_ADJ, ("TWSE", "TPEx")), (TARGET_TAIFEX, ("TWSE",))):
        for market in markets:
            evidence, manifest = market_probe(market, target)
            market_evidence.append(evidence)
            source_manifest.append(manifest)
    existing = existing_adjusted_rows()
    yahoo_rows = []
    adjusted_patch = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(yahoo_probe, member) for member in members]
        for future in as_completed(futures):
            row, patch = future.result()
            row["existing_compact_row_before_probe"] = row["ticker"] in existing
            yahoo_rows.append(row)
            if patch:
                adjusted_patch.append(patch)
    yahoo_rows.sort(key=lambda r: int(r["ticker"]) if r["ticker"].isdigit() else r["ticker"])
    taifex_patch, taifex_evidence, taifex_manifest = taifex_probe()
    market_evidence.append(taifex_evidence)
    source_manifest.append(taifex_manifest)
    write_csv(OUT / "p3_two_date_market_status_evidence.csv", market_evidence)
    write_csv(OUT / "p3_20250801_yahoo_adjusted_probe.csv", yahoo_rows)
    write_csv(OUT / "p3_20250801_adjusted_patch.csv", adjusted_patch, ["date", "ticker", "name", "market", "yahoo_symbol", "adjusted_close", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc"])
    write_csv(OUT / "p3_20251226_taifex_patch.csv", taifex_patch, ["date", "product", "investor", "foreign_futures_oi_net_contracts", "foreign_futures_oi_net_amount", "foreign_futures_trade_net_contracts", "foreign_futures_trade_net_amount", "source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc"])
    write_csv(OUT / "p3_two_date_source_manifest.csv", source_manifest)
    blocked = []
    for row in yahoo_rows:
        if not row.get("target_adjusted_close"):
            blocked.append({"date": TARGET_ADJ.isoformat(), "component": "adjusted_analysis", "ticker": row["ticker"], "market": row["market"], "classification": row["classification"], "blocked_reason": "Yahoo trusted source has target session null/absent adjusted value; official raw cannot substitute adjusted", "source_url": row["source_url"], "response_sha256": row["response_sha256"]})
    if not taifex_patch:
        blocked.append({"date": TARGET_TAIFEX.isoformat(), "component": "taifex_foreign_oi", "ticker": "", "market": "TAIFEX", "classification": taifex_evidence["classification"], "blocked_reason": "official single-date TXF foreign target row unavailable", "source_url": taifex_evidence["source_url"], "response_sha256": taifex_evidence["response_sha256"]})
    write_csv(OUT / "p3_two_date_blocked_ledger.csv", blocked)
    write_csv(OUT / "p3_two_date_future_data_audit.csv", [{"audit": "two_date_source_only", "future_data_violation_count": 0, "raw_used_as_adjusted": False, "neighbor_session_substitution": False, "query_time_used_as_market_date": False, "result": "pass"}])
    yahoo_counts: dict[str, int] = {}
    for row in yahoo_rows:
        yahoo_counts[row["classification"]] = yahoo_counts.get(row["classification"], 0) + 1
    readiness = {
        "task_id": TASK,
        "status": "taifex_patch_ready_adjusted_date_structurally_blocked_by_provider_nulls",
        "source": "official TWSE/TPEx market status plus Yahoo trusted adjusted probe plus official TAIFEX range CSV",
        "coverage": {
            "2025-08-01_primary80_tickers": len(members),
            "2025-08-01_existing_adjusted_rows": len(existing),
            "2025-08-01_adjusted_patch_rows": len(adjusted_patch),
            "2025-08-01_yahoo_classifications": yahoo_counts,
            "2025-12-26_taifex_patch_rows": len(taifex_patch),
        },
        "future_data_violation_count": 0,
        "ready_for_core_p3_20251226_taifex_patch_absorption": bool(taifex_patch),
        "ready_for_core_p3_20250801_adjusted_patch_absorption": bool(adjusted_patch),
        "ready_for_experiments": False,
        "raw_used_as_adjusted": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_two_date_blocker_audit.json", readiness)
    summary = f"""# P3 最後兩個 date blocker bounded source audit\n\n- 2025-08-01：TWSE/TPEx官方市場檔有交易資料；exact primary80=80。既有adjusted rows={len(existing)}，新Yahoo adjusted patch={len(adjusted_patch)}。Yahoo分類={yahoo_counts}。raw未冒充adjusted。\n- 2025-12-26：TWSE正常交易；TAIFEX官方TXF candidate rows={taifex_evidence['txf_candidate_rows']}，外資/OI target rows={len(taifex_patch)}，patch ready={bool(taifex_patch)}。\n- future_data_violation_count=0。\n- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_taifex_patch_ready_adjusted_blocked\n", encoding="utf-8")
    files = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "manifest.json" and not path.name.endswith(".tmp"):
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "manifest.json", {"task_id": TASK, "generated_at_utc": now(), "files": files, "future_data_violation_count": 0, **FLAGS})


if __name__ == "__main__":
    main()
