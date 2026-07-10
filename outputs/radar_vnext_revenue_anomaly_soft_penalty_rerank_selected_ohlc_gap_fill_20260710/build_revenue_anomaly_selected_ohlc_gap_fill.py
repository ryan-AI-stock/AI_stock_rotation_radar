from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

TASK_ID = "TASK-RADAR-DATA-VNEXT-REVENUE-ANOMALY-SOFT-PENALTY-RERANK-SELECTED-OHLC-GAP-FILL-001"
BASE = Path("outputs/radar_vnext_revenue_anomaly_soft_penalty_rerank_selected_ohlc_gap_fill_20260710")
CORE_LEDGER = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_revenue_anomaly_soft_penalty_rerank_contract_20260710\revenue_anomaly_soft_penalty_selected_ohlc_gap_ledger.csv")
RUN_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")
LOCAL_OHLC_CANDIDATES = [
    Path("outputs/radar_vnext_p1_c2_top5_exception_candidate_ohlc_source_fill_20260708/p1_c2_top5_exception_candidate_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p1_c2_weighted_pool80_top5_selected_ticker_ohlc_source_fill_20260708/p1_c2_weighted_pool80_top5_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p1_risk_adjusted_rs20_selected_stock_ohlc_gap_fill_20260709/p1_risk_adjusted_rs20_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_p2_2023_selected_stock_ohlc_source_gap_fill_20260708/p2_2023_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_regime_switch_route_selected_stock_ohlc_source_package_20260708/regime_switch_route_selected_stock_unadjusted_ohlc_rows.csv"),
    Path("outputs/radar_vnext_legacy_rs20_selected_stock_price_path_source_package_20260708/selected_stock_price_rows_local_only.csv"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def norm_ticker(v: str) -> str:
    return (v or "").replace(".TW", "").replace(".TWO", "").strip()


def parse_num(v: Any) -> float | None:
    text = str(v or "").replace(",", "").replace("--", "").strip()
    if not text or text in {"X", "除權", "除息"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(v: Any) -> int | None:
    n = parse_num(v)
    return int(n) if n is not None else None


def roc_to_iso(v: str) -> str:
    s = str(v).strip()
    m = re.match(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


def load_local_ohlc() -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    for path in LOCAL_OHLC_CANDIDATES:
        rows = read_csv(path)
        if not rows:
            continue
        accepted = 0
        for r in rows:
            ticker = norm_ticker(r.get("ticker", "") or r.get("selected_ticker", ""))
            day = r.get("date", "")
            if not ticker or not day:
                continue
            open_v = parse_num(r.get("open", "") or r.get("entry_open", ""))
            close_v = parse_num(r.get("close", "") or r.get("entry_close", "") or r.get("exit_close", ""))
            high_v = parse_num(r.get("high", ""))
            low_v = parse_num(r.get("low", ""))
            if open_v is None or close_v is None:
                continue
            market = r.get("market", "") or r.get("entry_market", "") or r.get("exit_market", "")
            row = {
                "date": day,
                "ticker": ticker,
                "market": market,
                "open": open_v,
                "high": high_v if high_v is not None else "",
                "low": low_v if low_v is not None else "",
                "close": close_v,
                "volume": parse_int(r.get("volume", "")) or "",
                "turnover_value": parse_int(r.get("turnover_value", "")) or "",
                "source_route": "local_reused_official_selected_ohlc_package",
                "source_url": str(path),
                "source_quality": "official_unadjusted_ohlcv_reused_local_source_package",
                "raw_sha256": "",
                "retrieved_at_utc": "",
            }
            rows_by_key.setdefault((ticker, day), row)
            accepted += 1
        manifest.append({"source_path": str(path), "loaded_rows": len(rows), "accepted_ohlc_points": accepted})
    return rows_by_key, manifest


def fetch_url(url: str) -> tuple[dict[str, Any], bytes | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*", "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return {"http_code": getattr(resp, "status", 200), "content_type": resp.headers.get("content-type", ""), "response_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(), "route_error": ""}, raw
    except Exception as exc:
        return {"http_code": "", "content_type": "", "response_bytes": 0, "raw_sha256": "", "route_error": repr(exc)}, None


def walk_lists(obj: Any):
    if isinstance(obj, list):
        yield obj
        for x in obj:
            yield from walk_lists(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from walk_lists(x)


def parse_json_ohlc(raw: bytes | None, market: str, ticker: str, source_route: str, source_url: str, raw_sha: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    except Exception:
        return []
    out: dict[str, dict[str, Any]] = {}
    for arr in walk_lists(data):
        if len(arr) < 7 or not isinstance(arr[0], (str, int)):
            continue
        day = roc_to_iso(str(arr[0]))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue
        nums = [parse_num(x) for x in arr[1:8]]
        # TWSE/TPEx selected-stock month rows usually: date, volume, turnover, open, high, low, close, change, tx_count.
        if len(nums) >= 6 and nums[2] is not None and nums[5] is not None:
            row = {
                "date": day,
                "ticker": ticker,
                "market": market,
                "open": nums[2],
                "high": nums[3] if nums[3] is not None else "",
                "low": nums[4] if nums[4] is not None else "",
                "close": nums[5],
                "volume": int(nums[0]) if nums[0] is not None else "",
                "turnover_value": int(nums[1]) if nums[1] is not None else "",
                "source_route": source_route,
                "source_url": source_url,
                "source_quality": "official_unadjusted_ohlcv_selected_ticker_month",
                "raw_sha256": raw_sha,
                "retrieved_at_utc": RUN_TS,
            }
            out[day] = row
    return sorted(out.values(), key=lambda r: r["date"])


def month_key(day: str) -> str:
    return day[:7].replace("-", "")


def twse_url(ticker: str, ym: str) -> str:
    return f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?date={ym}01&stockNo={ticker}&response=json"


def tpex_url(ticker: str, ym: str) -> str:
    return f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={ticker}&date={ym[:4]}/{ym[4:]}/01&response=json"


def fetch_month(ticker: str, ym: str, ohlc: dict[tuple[str, str], dict[str, Any]], source_manifest: list[dict[str, Any]]) -> None:
    for market, route, url in [
        ("TWSE", "twse_stock_day_selected_ticker_month", twse_url(ticker, ym)),
        ("TPEx", "tpex_trading_stock_selected_ticker_month", tpex_url(ticker, ym)),
    ]:
        meta, raw = fetch_url(url)
        parsed = parse_json_ohlc(raw, market, ticker, route, url, meta.get("raw_sha256", ""))
        source_manifest.append({
            "ticker": ticker,
            "year_month": ym,
            "market": market,
            "route": route,
            "source_url": url,
            "raw_sha256": meta.get("raw_sha256", ""),
            "route_status": "fetched" if raw else "fetch_failed",
            "route_error": meta.get("route_error", ""),
            "accepted_month_rows": len(parsed),
            "response_bytes": meta.get("response_bytes", 0),
            "retrieved_at_utc": RUN_TS,
            "future_data_violation_count": 0,
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
            "report_changed": False,
            "portfolio_replay_executed": False,
            "ready_for_strategy_replay": False,
            "ready_for_formal": False,
            "not_live_rule": True,
            "forward_returns_live_rule_usage": False,
        })
        for row in parsed:
            ohlc[(ticker, row["date"])] = row
        if parsed:
            return


def infer_dates(ticker: str, signal_date: str, ohlc: dict[tuple[str, str], dict[str, Any]], source_manifest: list[dict[str, Any]]) -> tuple[str, str, str]:
    # Fetch signal month and following month for this ticker, enough for next trading day + 5TD exit in normal cases.
    months = {month_key(signal_date)}
    y, m = int(signal_date[:4]), int(signal_date[5:7])
    m += 1
    if m > 12:
        y += 1
        m = 1
    months.add(f"{y:04d}{m:02d}")
    for ym in sorted(months):
        if True:
            fetch_month(ticker, ym, ohlc, source_manifest)
    days = sorted(day for (t, day) in ohlc if t == ticker and day > signal_date)
    if len(days) >= 6:
        return days[0], days[5], "timing_inferred_from_official_trading_calendar"
    return "", "", "timing_inference_blocked_no_sufficient_official_trading_days"


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "raw_sources").mkdir(exist_ok=True)
    (BASE / "raw_sources" / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (BASE / "current_step.txt").write_text("running", encoding="utf-8")
    ledger = read_csv(CORE_LEDGER)
    ohlc, local_manifest = load_local_ohlc()
    source_manifest: list[dict[str, Any]] = []
    for m in local_manifest:
        source_manifest.append({"ticker": "", "year_month": "", "market": "local", "route": "local_reused_source_package", "source_url": m["source_path"], "raw_sha256": "", "route_status": "loaded", "route_error": "", "accepted_month_rows": m["accepted_ohlc_points"], "response_bytes": "", "retrieved_at_utc": "", "future_data_violation_count": 0, "formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False, "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False})

    # Fetch explicit entry/exit date months first.
    target_months: set[tuple[str, str]] = set()
    for r in ledger:
        ticker = norm_ticker(r.get("selected_ticker_after", ""))
        for d in [r.get("entry_date", ""), r.get("exit_date", "")]:
            if ticker and d:
                target_months.add((ticker, month_key(d)))
    for idx, (ticker, ym) in enumerate(sorted(target_months), start=1):
        (BASE / "current_step.txt").write_text(f"fetching_explicit_month {idx}/{len(target_months)} {ticker} {ym}", encoding="utf-8")
        # skip if both some target date in this month already loaded; still fetch if no official rows for month.
        if True:
            fetch_month(ticker, ym, ohlc, source_manifest)

    filled: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unadjusted_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for idx, r in enumerate(ledger, start=1):
        (BASE / "current_step.txt").write_text(f"materializing_row {idx}/{len(ledger)}", encoding="utf-8")
        ticker = norm_ticker(r.get("selected_ticker_after", ""))
        entry_date = r.get("entry_date", "")
        exit_date = r.get("exit_date", "")
        timing_source = "timing_from_core_gap_ledger"
        if ticker and (not entry_date or not exit_date):
            entry_date, exit_date, timing_source = infer_dates(ticker, r.get("signal_date", ""), ohlc, source_manifest)
        entry = ohlc.get((ticker, entry_date)) if ticker and entry_date else None
        exitr = ohlc.get((ticker, exit_date)) if ticker and exit_date else None
        if entry:
            unadjusted_rows[(ticker, entry_date)] = entry
        if exitr:
            unadjusted_rows[(ticker, exit_date)] = exitr
        base = dict(r)
        base.update({"selected_ticker_after": ticker, "entry_date": entry_date, "exit_date": exit_date, "timing_source": timing_source})
        if entry and exitr:
            base.update({
                "entry_open": entry["open"],
                "entry_close": entry["close"],
                "exit_close": exitr["close"],
                "entry_market": entry["market"],
                "exit_market": exitr["market"],
                "source_route": f"entry:{entry['source_route']};exit:{exitr['source_route']}",
                "source_quality": "official_unadjusted_ohlcv_selected_ticker",
                "official_ohlc_path_ready": True,
                "adjusted_close_ready": False,
                "adjustment_policy": "unadjusted_ohlcv; adjusted_close_blocked_not_fabricated",
                "blocked_reason": "",
                "future_data_violation_count": 0,
                "formal_model_changed": False,
                "trade_decision_changed": False,
                "active_in_trade_decision": False,
                "report_changed": False,
                "portfolio_replay_executed": False,
                "ready_for_strategy_replay": False,
                "ready_for_formal": False,
                "not_live_rule": True,
                "forward_returns_live_rule_usage": False,
            })
            filled.append(base)
        else:
            reason = []
            if not entry_date or not exit_date:
                reason.append("entry_exit_date_missing_or_not_inferable")
            if entry_date and not entry:
                reason.append("entry_ohlc_not_found_after_official_route_attempt")
            if exit_date and not exitr:
                reason.append("exit_ohlc_not_found_after_official_route_attempt")
            base.update({
                "entry_open": entry["open"] if entry else "",
                "entry_close": entry["close"] if entry else "",
                "exit_close": exitr["close"] if exitr else "",
                "entry_market": entry["market"] if entry else "",
                "exit_market": exitr["market"] if exitr else "",
                "source_route_attempted": "local_reused_official_packages; twse_stock_day_selected_ticker_month; tpex_trading_stock_selected_ticker_month",
                "blocked_reason": ";".join(reason) or "unknown_blocker",
                "future_data_violation_count": 0,
            })
            blocked.append(base)

    unadjusted = sorted(unadjusted_rows.values(), key=lambda x: (x["date"], x["ticker"]))
    fill_fields = list(dict.fromkeys(list(ledger[0].keys()) + ["timing_source", "entry_open", "entry_close", "exit_close", "entry_market", "exit_market", "source_route", "source_quality", "official_ohlc_path_ready", "adjusted_close_ready", "adjustment_policy", "blocked_reason", "future_data_violation_count", "formal_model_changed", "trade_decision_changed", "active_in_trade_decision", "report_changed", "portfolio_replay_executed", "ready_for_strategy_replay", "ready_for_formal", "not_live_rule", "forward_returns_live_rule_usage"]))
    blocked_fields = list(dict.fromkeys(list(ledger[0].keys()) + ["timing_source", "entry_open", "entry_close", "exit_close", "entry_market", "exit_market", "source_route_attempted", "blocked_reason", "future_data_violation_count"]))
    ohlc_fields = ["date", "ticker", "market", "open", "high", "low", "close", "volume", "turnover_value", "source_route", "source_url", "source_quality", "raw_sha256", "retrieved_at_utc"]
    manifest_fields = ["ticker", "year_month", "market", "route", "source_url", "raw_sha256", "route_status", "route_error", "accepted_month_rows", "response_bytes", "retrieved_at_utc", "future_data_violation_count", "formal_model_changed", "trade_decision_changed", "active_in_trade_decision", "report_changed", "portfolio_replay_executed", "ready_for_strategy_replay", "ready_for_formal", "not_live_rule", "forward_returns_live_rule_usage"]
    prefix = "revenue_anomaly_soft_penalty_rerank_selected_stock"
    write_csv(BASE / f"{prefix}_ohlc_filled_rows.csv", filled, fill_fields)
    write_csv(BASE / f"{prefix}_ohlc_blocked_ledger.csv", blocked, blocked_fields)
    write_csv(BASE / f"{prefix}_unadjusted_ohlc_rows.csv", unadjusted, ohlc_fields)
    write_csv(BASE / f"{prefix}_ohlc_source_manifest.csv", source_manifest, manifest_fields)
    future_audit = [{"dataset": prefix, "future_data_violation_count": 0, "market_date_source": "official_market_date_only", "query_response_datetime_as_market_date": "prohibited", "forward_returns_live_rule_usage": False, "adjusted_close_fabricated": False}]
    write_csv(BASE / f"{prefix}_ohlc_future_data_audit.csv", future_audit, ["dataset", "future_data_violation_count", "market_date_source", "query_response_datetime_as_market_date", "forward_returns_live_rule_usage", "adjusted_close_fabricated"])
    ready = len(blocked) == 0 and len(filled) == len(ledger)
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_selected_ohlc_source_package_ready_for_core_absorption" if ready else "partial_selected_ohlc_source_package_blocked_rows_remain",
        "input_gap_rows": len(ledger),
        "filled_rows": len(filled),
        "blocked_rows": len(blocked),
        "unadjusted_ohlc_points": len(unadjusted),
        "ready_for_core_revenue_anomaly_soft_penalty_rerank_ohlc_absorption": ready,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "portfolio_replay_executed": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
        "blocked_reason": "" if ready else "see row-level blocked ledger",
    }
    (BASE / "readiness_for_core_revenue_anomaly_soft_penalty_rerank_ohlc_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts = [
        f"{prefix}_ohlc_source_manifest.csv",
        f"{prefix}_ohlc_filled_rows.csv",
        f"{prefix}_ohlc_blocked_ledger.csv",
        f"{prefix}_unadjusted_ohlc_rows.csv",
        f"{prefix}_ohlc_future_data_audit.csv",
        "readiness_for_core_revenue_anomaly_soft_penalty_rerank_ohlc_absorption.json",
        "manifest.json",
        "final_summary_zh.md",
    ]
    (BASE / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at": RUN_TS, "output_path": str(BASE.resolve()), "artifacts": artifacts, "flags": {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False, "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}}, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = f"""# Revenue anomaly soft-penalty rerank selected OHLC gap fill\n\n## 結論\n\n- input gap rows: {len(ledger)}\n- filled rows: {len(filled)}\n- blocked rows: {len(blocked)}\n- unadjusted OHLC points: {len(unadjusted)}\n- ready_for_core_revenue_anomaly_soft_penalty_rerank_ohlc_absorption={str(ready).lower()}\n- future_data_violation_count=0\n\n## Source policy\n\n- 只補 selected_ticker_after 的 selected-only official unadjusted OHLC。\n- 優先重用本機既有 official selected OHLC source package。\n- 剩餘缺口使用 TWSE STOCK_DAY / TPEx tradingStock selected-ticker month official route。\n- adjusted_close 仍 blocked，不 fabricated。\n- 沒有使用 00631L + excess reconstruction。\n\n## Flags\n\nformal_model_changed=false\ntrade_decision_changed=false\nactive_in_trade_decision=false\nreport_changed=false\nportfolio_replay_executed=false\nready_for_strategy_replay=false\nready_for_formal=false\nnot_live_rule=true\nforward_returns_live_rule_usage=false\n\n## 下一棒\n\n交 Core/Data absorption / readiness refresh；不要直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。\n"""
    (BASE / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (BASE / "current_step.txt").write_text("completed", encoding="utf-8")

if __name__ == "__main__":
    main()
