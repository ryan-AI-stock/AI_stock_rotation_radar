from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-DYNAMIC80-INCUMBENT-HOLD-SELECTED-STOCK-DAILY-OHLC-GAP-FILL-001"
OUT = Path(__file__).resolve().parent
CORE_LEDGER = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_dynamic80_incumbent_hold_comparator_contract_20260710\p1_dynamic80_incumbent_hold_selected_stock_ohlc_gap_ledger.csv")
OLD = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_p1_legacy_regime_selected_stock_unadjusted_ohlc_source_package_20260708")
RAW = OUT / "raw_sources"
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False, "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}
FIELDS = ["date", "ticker", "name", "market", "open", "high", "low", "close", "volume", "turnover_value", "source_quality", "adjustment_policy", "source_url", "source_route", "raw_sha256", "raw_cache_path", "retrieval_time_utc"]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(v: object) -> str:
    return str(v).replace(",", "").replace("--", "").strip()


def num(v: object, integer: bool = False) -> str:
    v = clean(v)
    if not v: return ""
    try: return str(int(float(v))) if integer else str(float(v))
    except ValueError: return ""


def roc(v: object) -> str:
    p = str(v).strip().split("/")
    try: return f"{int(p[0])+1911:04d}-{int(p[1]):02d}-{int(p[2]):02d}" if len(p) == 3 else ""
    except ValueError: return ""


def idx(fields: list, *names: str) -> int:
    compact = ["".join(str(x).split()) for x in fields]
    for name in names:
        name = "".join(name.split())
        for i, field in enumerate(compact):
            if name in field: return i
    return -1


def url_for(market: str, ticker: str, month: str) -> str:
    if market == "TWSE":
        # The legacy exchangeReport route can return an incorrect calendar year
        # for older months. RWD returns the requested historical month.
        return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + urlencode({"date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json"})
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?" + urlencode({"code": ticker, "date": month.replace("-", "/") + "/01", "response": "json"})


def parse(payload: dict, market: str, ticker: str, url: str, raw_hash: str, cache_path: str, retrieval: str) -> list[dict]:
    if market == "TWSE":
        if payload.get("stat") != "OK": return []
        fields, data = payload.get("fields") or [], payload.get("data") or []
    else:
        if str(payload.get("stat", "")).lower() != "ok": return []
        table = next((x for x in payload.get("tables") or [] if x.get("fields") and x.get("data")), {})
        fields, data = table.get("fields") or [], table.get("data") or []
    ids = [idx(fields, "日 期", "日期"), idx(fields, "成交股數", "成交仟股"), idx(fields, "成交金額", "成交仟元"), idx(fields, "開盤"), idx(fields, "最高"), idx(fields, "最低"), idx(fields, "收盤")]
    if min(ids) < 0: return []
    date_i, vol_i, turnover_i, open_i, high_i, low_i, close_i = ids
    thousand_vol = market == "TPEx" and "仟股" in "".join(fields)
    thousand_money = market == "TPEx" and "仟元" in "".join(fields)
    out = []
    for row in data:
        if not isinstance(row, list): continue
        day, close = roc(row[date_i]), num(row[close_i])
        if not day or not close: continue
        volume, turnover = num(row[vol_i], True), num(row[turnover_i], True)
        if thousand_vol and volume: volume = str(int(volume) * 1000)
        if thousand_money and turnover: turnover = str(int(turnover) * 1000)
        out.append({"date": day, "ticker": ticker, "name": "", "market": market, "open": num(row[open_i]), "high": num(row[high_i]), "low": num(row[low_i]), "close": close, "volume": volume, "turnover_value": turnover, "source_quality": f"official_unadjusted_ohlcv_{'twse_rwd_stock_day' if market == 'TWSE' else 'tpex_trading_stock'}", "adjustment_policy": "official_unadjusted_ohlcv; adjusted_close_blocked_not_fabricated", "source_url": url, "source_route": "TWSE_RWD_STOCK_DAY" if market == "TWSE" else "TPEX_TRADING_STOCK", "raw_sha256": raw_hash, "raw_cache_path": cache_path, "retrieval_time_utc": retrieval})
    return out


def load_raw(path: Path, market: str, ticker: str, url: str) -> list[dict]:
    raw = path.read_bytes(); stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
    try: return parse(json.loads(raw.decode("utf-8-sig")), market, ticker, url, hashlib.sha256(raw).hexdigest(), str(path), stamp)
    except (UnicodeDecodeError, json.JSONDecodeError): return []


def fetch(url: str) -> tuple[bytes | None, str]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r: return r.read(), ""
    except urllib.error.HTTPError as e: return e.read(), f"HTTPError:{e.code}"
    except Exception as e: return None, type(e).__name__


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(exist_ok=True)
    (OUT / ".gitignore").write_text("raw_sources/\n", encoding="utf-8")
    ledger = read_csv(CORE_LEDGER)
    needed = {(r["ticker"], r["price_date"]) for r in ledger}
    field_counts = Counter((r["ticker"], r["price_date"]) for r in ledger)
    old_attempts = {(r["ticker"], r["month"]): r for r in read_csv(OLD / "completed_route_attempts.csv") if r.get("status") == "accepted"}
    rows: dict[tuple[str, str], dict] = {}
    routes: list[dict] = []
    # First reuse only raw files whose ticker/month are needed.
    months = {(ticker, date[:7]) for ticker, date in needed}
    for ticker, month in sorted(months):
        old = old_attempts.get((ticker, month))
        if not old: continue
        path = Path(old["raw_path"])
        market = old["accepted_market"]
        if not path.exists() or market not in {"TWSE", "TPEx"}: continue
        url = old["source_url"] or url_for(market, ticker, month)
        parsed = load_raw(path, market, ticker, url)
        selected = [r for r in parsed if (ticker, r["date"]) in needed]
        for r in selected: rows[(ticker, r["date"])] = r
        routes.append({"ticker": ticker, "month": month, "market": market, "route_status": "reused_local_official_raw", "needed_pair_count": sum(1 for x in needed if x[0] == ticker and x[1].startswith(month)), "filled_pair_count": len(selected), "source_url": url, "raw_sha256": old.get("raw_sha256", ""), "raw_cache_path": str(path), "retrieval_time_utc": old.get("timestamp_utc", ""), "route_error": ""})
    checkpoint = OUT / "checkpoint_state.json"
    prior = read_csv(OUT / "source_route_attempts.csv") if (OUT / "source_route_attempts.csv").exists() else []
    # A resumed run must reconstruct values from already accepted local raw files.
    # Do not rely on in-memory rows from the interrupted process.
    for route in prior:
        if route.get("route_status") not in {"accepted_new_official_raw", "accepted_rwd_retry"}:
            continue
        path = Path(route.get("raw_cache_path", ""))
        market, ticker = route.get("market", ""), route.get("ticker", "")
        if not path.exists() or market not in {"TWSE", "TPEx"}:
            continue
        for record in load_raw(path, market, ticker, route.get("source_url", "")):
            if (ticker, record["date"]) in needed:
                rows[(ticker, record["date"])] = record
    pending = {(t, d) for t, d in needed if (t, d) not in rows}
    work = sorted({(ticker, date[:7]) for ticker, date in pending})
    # Retry previously unmatched months once through the RWD historical route.
    done = {(r["ticker"], r["month"]) for r in prior if r.get("route_status") == "accepted_rwd_retry"}
    # Keep the persistent route ledger canonical on resume; old-cache reuse rows
    # are already represented in it after the first checkpoint.
    routes = prior if prior else routes
    (OUT / "current_step.txt").write_text(f"running_pending_ticker_month_routes 0/{len(work)}\n", encoding="utf-8")
    for n, (ticker, month) in enumerate(work, 1):
        if (ticker, month) in done: continue
        accepted = False; attempted = []; selected = []
        for market in ("TWSE", "TPEx"):
            url = url_for(market, ticker, month); cache = RAW / f"{ticker}_{month}_{market}{'_RWD' if market == 'TWSE' else ''}.json"
            raw, error = (cache.read_bytes(), "") if cache.exists() else fetch(url)
            if raw is None:
                attempted.append(f"{market}:{error}"); continue
            if not cache.exists(): cache.write_bytes(raw)
            parsed = load_raw(cache, market, ticker, url)
            selected = [r for r in parsed if (ticker, r["date"]) in pending]
            attempted.append(f"{market}:{'rows='+str(len(selected)) if selected else error or 'no_target_rows'}")
            if selected:
                for r in selected: rows[(ticker, r["date"])] = r
                raw_hash = hashlib.sha256(cache.read_bytes()).hexdigest()
                routes.append({"ticker": ticker, "month": month, "market": market, "route_status": "accepted_rwd_retry" if market == "TWSE" else "accepted_new_official_raw", "needed_pair_count": sum(1 for x in pending if x[0] == ticker and x[1].startswith(month)), "filled_pair_count": len(selected), "source_url": url, "raw_sha256": raw_hash, "raw_cache_path": str(cache), "retrieval_time_utc": now(), "route_error": ""})
                accepted = True; break
        if not accepted:
            routes.append({"ticker": ticker, "month": month, "market": "", "route_status": "blocked_no_target_official_row", "needed_pair_count": sum(1 for x in pending if x[0] == ticker and x[1].startswith(month)), "filled_pair_count": 0, "source_url": "", "raw_sha256": "", "raw_cache_path": "", "retrieval_time_utc": now(), "route_error": " | ".join(attempted)})
        write_csv(OUT / "source_route_attempts.csv", routes, list(routes[0]))
        write_json(checkpoint, {"task_id": TASK_ID, "current_step": "running_pending_ticker_month_routes", "completed_pending_routes": n, "pending_route_total": len(work), "filled_unique_pairs_so_far": len(rows), "updated_at_utc": now()})
        (OUT / "current_step.txt").write_text(f"running_pending_ticker_month_routes {n}/{len(work)}\n", encoding="utf-8")
        time.sleep(0.12)
    filled = [rows[k] for k in sorted(rows)]
    blocked_pairs = sorted(needed - set(rows))
    filled_ledger = []
    blocked = []
    for record in ledger:
        key = (record["ticker"], record["price_date"]); source = rows.get(key)
        base = {**record, "official_unadjusted_ohlc_ready": str(bool(source)).lower(), "adjusted_close_ready": "false"}
        if source: filled_ledger.append({**base, **{f"official_{k}": source.get(k, "") for k in FIELDS}})
        else: blocked.append({**base, "blocked_reason": "official_response_has_no_exact_trading_close_for_requested_ticker_date", "attempted_source": "TWSE_RWD_STOCK_DAY_then_TPEX_TRADING_STOCK; no_neighbour_date_substitution"})
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_filled_rows.csv", filled_ledger, list(filled_ledger[0]) if filled_ledger else list(ledger[0]) + ["official_unadjusted_ohlc_ready", "adjusted_close_ready"])
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_blocked_ledger.csv", blocked, list(blocked[0]) if blocked else list(ledger[0]) + ["official_unadjusted_ohlc_ready", "adjusted_close_ready", "blocked_reason", "attempted_source"])
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_unadjusted_ohlc_rows.csv", filled, FIELDS)
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_source_manifest.csv", routes, list(routes[0]) if routes else ["ticker", "month"])
    coverage = [{"input_field_level_rows": len(ledger), "unique_ticker_date_pairs": len(needed), "unique_tickers": len({x[0] for x in needed}), "filled_unique_pairs": len(rows), "blocked_unique_pairs": len(blocked_pairs), "filled_field_level_rows": len(filled_ledger), "blocked_field_level_rows": len(blocked), "official_unadjusted_ohlc_ready_share": round(len(rows) / len(needed), 10), "adjusted_close_ready": "false", "future_data_violation_count": 0}]
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_coverage_audit.csv", coverage, list(coverage[0]))
    audit = [{"check": "official_market_date_rows_only", "status": "pass", "future_data_violation_count": 0, "notes": "Only exact Core ticker/date requirements were matched."}, {"check": "no_00631l_excess_reconstruction", "status": "pass", "future_data_violation_count": 0, "notes": "Not used."}, {"check": "no_adjusted_close_fabrication", "status": "pass", "future_data_violation_count": 0, "notes": "Adjusted close is intentionally blocked."}]
    write_csv(OUT / "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_future_data_audit.csv", audit, list(audit[0]))
    ready = len(rows) == len(needed)
    readiness = {"task_id": TASK_ID, "status": "official_selected_stock_daily_ohlc_source_ready" if ready else "official_selected_stock_daily_ohlc_source_partial_blocked", "source": "local official raw reuse plus TWSE STOCK_DAY / TPEx tradingStock selected ticker-month routes", "coverage": coverage[0], "ready_for_core_p1_dynamic80_incumbent_hold_ohlc_absorption": ready, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "future_data_violation_count": 0, **FLAGS}
    write_json(OUT / "readiness_for_core_p1_dynamic80_incumbent_hold_ohlc_absorption.json", readiness)
    manifest = {"task_id": TASK_ID, "output_path": str(OUT), "core_input_ledger": str(CORE_LEDGER), "core_commit": "8643f8d", "raw_cache_ignored": True, "artifacts": ["p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_filled_rows.csv", "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_blocked_ledger.csv", "p1_dynamic80_incumbent_hold_selected_stock_daily_unadjusted_ohlc_rows.csv", "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_source_manifest.csv", "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_coverage_audit.csv", "p1_dynamic80_incumbent_hold_selected_stock_daily_ohlc_future_data_audit.csv", "source_route_attempts.csv", "checkpoint_state.json", "current_step.txt", "readiness_for_core_p1_dynamic80_incumbent_hold_ohlc_absorption.json", "final_summary_zh.md"], "future_data_violation_count": 0, **FLAGS}
    write_json(OUT / "manifest.json", manifest)
    (OUT / "final_summary_zh.md").write_text(f"# P1 Dynamic80 incumbent-hold selected-stock daily OHLC gap fill\n\n- input field-level rows: {len(ledger)}\n- unique ticker/date pairs: {len(needed)}\n- filled pairs: {len(rows)}\n- blocked pairs: {len(blocked_pairs)}\n- ready_for_core_absorption: {str(ready).lower()}\n- adjusted_close_ready=false\n- future_data_violation_count=0\n\n本包僅為官方未還原 OHLC source package；不做策略計算、replay 或 formal。\n", encoding="utf-8")
    write_json(checkpoint, {"task_id": TASK_ID, "current_step": "completed", "filled_unique_pairs": len(rows), "blocked_unique_pairs": len(blocked_pairs), "updated_at_utc": now()})
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
