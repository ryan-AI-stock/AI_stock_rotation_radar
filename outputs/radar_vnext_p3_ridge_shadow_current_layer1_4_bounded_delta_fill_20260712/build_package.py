import csv
import gzip
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "cache"
CACHE.mkdir(exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
SNAPSHOT = pd.Timestamp("2026-07-09")
LOOKBACK_START = pd.Timestamp("2025-06-01")
TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-RIDGE-SHADOW-CURRENT-LAYER1-4-BOUNDED-DELTA-FILL-001"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p3_ridge_shadow_current_exact_layer0_4_recompute_20260712")
P3 = OUT.parents[0] / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
CURRENT = OUT.parents[0] / "radar_vnext_p3_ridge_shadow_current_exact_layer0_4_source_package_20260712"
MONTHLY = OUT.parents[0] / "radar_dynamic_pool1_mops_monthly_revenue_full_universe_pit_20260703"
QUARTERLY = OUT.parents[0] / "radar_dynamic_pool1_quarterly_fundamentals_full_sweep_20260703"

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
NEW_TICKERS = {"4989", "2493", "7828", "3149", "6919", "7799", "5475", "6907"}
MOPS_METRICS = {
    "OperatingCashflow": "operating_cash_flow",
    "InvestingCashflow": "investing_cash_flow",
    "DebtRatio": "debt_ratio_percent",
    "CurrentRatio": "current_ratio_percent",
}
MOPS_URL = "https://mopsfin.twse.com.tw/compare/data"
MOPS_INDEX = "https://mopsfin.twse.com.tw/compare.html"


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False, encoding="utf-8-sig", compression="gzip" if str(path).endswith(".gz") else None)
        return
    fields = fields or (list(rows[0]) if rows else ["empty"])
    opener = gzip.open if str(path).endswith(".gz") else open
    kwargs = {"mode": "wt", "encoding": "utf-8-sig", "newline": ""} if str(path).endswith(".gz") else {"mode": "w", "encoding": "utf-8-sig", "newline": ""}
    with opener(path, **kwargs) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_many(pattern, tickers, start=None, end=None):
    frames = []
    for path in sorted(OUT.parents[0].glob(pattern)):
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame["ticker"] = frame["ticker"].str.zfill(4)
        frame = frame[frame["ticker"].isin(tickers)]
        if "date" in frame:
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            if start is not None:
                frame = frame[frame["date"] >= start]
            if end is not None:
                frame = frame[frame["date"] <= end]
        if len(frame):
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_yahoo(ticker, preferred_market):
    cache_path = CACHE / f"yahoo_{ticker}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    suffixes = ["TW", "TWO"] if preferred_market == "TWSE" else ["TWO", "TW"]
    last_error = ""
    for suffix in suffixes:
        symbol = f"{ticker}.{suffix}"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"period1": 1748736000, "period2": 1783728000, "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"}
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
                response.raise_for_status()
                payload = response.json()
                result = ((payload.get("chart") or {}).get("result") or [None])[0]
                if not result or not result.get("timestamp"):
                    raise ValueError("chart result has no timestamps")
                record = {
                    "ticker": ticker,
                    "symbol": symbol,
                    "source_url": response.url,
                    "source_hash": sha256_bytes(response.content),
                    "response_bytes": len(response.content),
                    "retrieved_at": now(),
                    "attempt_count": attempt + 1,
                    "status": "accepted",
                    "result": result,
                }
                cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                return record
            except Exception as exc:
                last_error = repr(exc)
                time.sleep(1 + attempt)
    record = {"ticker": ticker, "status": "blocked", "error": last_error, "retrieved_at": now()}
    cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record


def yahoo_rows(record, scope_row):
    if record.get("status") != "accepted":
        return []
    result = record["result"]
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    timestamps = result.get("timestamp") or []
    rows = []
    for index, stamp in enumerate(timestamps):
        values = {key: (quote.get(key) or [None] * len(timestamps))[index] for key in ("open", "high", "low", "close", "volume")}
        adjusted_close = adj[index] if index < len(adj) else None
        if values["close"] in (None, 0) or adjusted_close is None:
            continue
        day = pd.Timestamp(stamp, unit="s", tz="UTC").tz_convert("Asia/Taipei").tz_localize(None).normalize()
        if day < LOOKBACK_START or day > SNAPSHOT:
            continue
        factor = float(adjusted_close) / float(values["close"])
        rows.append({
            "date": day.date().isoformat(), "ticker": scope_row["ticker"], "name": scope_row["name"], "market": scope_row["market"],
            "raw_open_comparator": values["open"], "raw_high_comparator": values["high"], "raw_low_comparator": values["low"], "raw_close_comparator": values["close"],
            "adjustment_factor": factor, "adjusted_open": None if values["open"] is None else float(values["open"]) * factor,
            "adjusted_high": None if values["high"] is None else float(values["high"]) * factor,
            "adjusted_low": None if values["low"] is None else float(values["low"]) * factor,
            "adjusted_close": float(adjusted_close), "source_quality": "trusted_nonofficial_yahoo_research_grade",
            "adjustment_policy": "Yahoo adjusted close factor applied to same-provider raw O/H/L/C; analysis only, never execution price",
            "source_url": record["source_url"], "source_hash": record["source_hash"], "retrieved_at": record["retrieved_at"],
            "available_at_policy": "provider EOD series; current 2026-07-09 shadow snapshot only; not historical formal PIT replay",
            "accepted_for_formal": False, "human_review_required": True, "future_data_violation_count": 0, **FLAGS,
        })
    return rows


def fetch_mops_indicators(tickers):
    cache_path = CACHE / "mops_new_tickers_indicators.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh;q=0.9"})
    session.get(MOPS_INDEX, timeout=30)
    results = []
    for metric in MOPS_METRICS:
        form = [("compareItem", metric), ("quarter", "true"), ("ys", "20261"), ("revenue", "false")]
        form.extend(("companyId", ticker) for ticker in tickers)
        error = ""
        for attempt in range(3):
            try:
                response = session.post(MOPS_URL, data=form, timeout=60)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("xaxisList") or not payload.get("graphData"):
                    raise ValueError("MOPS indicator response missing graph data")
                results.append({"metric": metric, "status": "accepted", "payload": payload, "source_hash": sha256_bytes(response.content), "response_bytes": len(response.content), "attempt_count": attempt + 1, "retrieved_at": now()})
                break
            except Exception as exc:
                error = repr(exc)
                time.sleep(1 + attempt)
        else:
            results.append({"metric": metric, "status": "blocked", "error": error, "retrieved_at": now()})
    cache_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    return results


def conservative_available(period):
    year, quarter = int(period[:4]), int(period[-1])
    return {1: f"{year}-05-15", 2: f"{year}-08-14", 3: f"{year}-11-14", 4: f"{year + 1}-03-31"}[quarter]


def main():
    CURRENT_STEP.write_text("load_scope_and_local_sources", encoding="utf-8")
    scope = pd.read_csv(CORE / "p3_ridge_shadow_current_layer1_4_bounded_gap_ledger.csv", dtype={"ticker": str})
    scope["ticker"] = scope["ticker"].str.zfill(4)
    tickers = set(scope["ticker"])
    scope.to_csv(OUT / "ridge_shadow_current_active_ticker_scope.csv", index=False, encoding="utf-8-sig")

    adjusted = read_many("radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711/compact/adjusted/*.csv.gz", tickers, LOOKBACK_START, SNAPSHOT)
    raw = read_many("radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711/compact/price/*.csv.gz", tickers, LOOKBACK_START, SNAPSHOT)
    current_raw = pd.read_csv(CURRENT / "ridge_shadow_current_full_market_official_ohlcv.csv.gz", dtype={"ticker": str})
    current_raw["ticker"] = current_raw["ticker"].str.zfill(4)
    current_raw["date"] = pd.to_datetime(current_raw["date"], errors="coerce")
    current_raw = current_raw[current_raw["ticker"].isin(tickers)]
    raw = pd.concat([raw, current_raw], ignore_index=True).sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")

    existing = adjusted.merge(raw[["date", "ticker", "open", "high", "low", "close"]], on=["date", "ticker"], how="left", suffixes=("", "_official"))
    existing["adjustment_factor"] = pd.to_numeric(existing["adjusted_close"], errors="coerce") / pd.to_numeric(existing["raw_close_comparator"], errors="coerce")
    for field in ("open", "high", "low", "close"):
        existing[f"adjusted_{field}"] = pd.to_numeric(existing[field], errors="coerce") * existing["adjustment_factor"]
    existing["raw_open_comparator"] = existing["open"]
    existing["raw_high_comparator"] = existing["high"]
    existing["raw_low_comparator"] = existing["low"]
    existing["available_at_policy"] = "trusted adjusted series joined to official raw same-date HLC; current shadow analysis only"
    existing["accepted_for_formal"] = False
    existing["human_review_required"] = True
    existing["future_data_violation_count"] = 0
    for key, value in FLAGS.items():
        existing[key] = value

    yahoo_targets = sorted(tickers)
    CURRENT_STEP.write_text(f"fetch_bounded_yahoo_active_candidates 0/{len(yahoo_targets)}", encoding="utf-8")
    yahoo = []
    source_manifest = []
    scope_by_ticker = {row["ticker"]: row for row in scope.to_dict("records")}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch_yahoo, ticker, scope_by_ticker[ticker]["market"]): ticker for ticker in yahoo_targets}
        for count, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            record = future.result()
            yahoo.extend(yahoo_rows(record, scope_by_ticker[ticker]))
            source_manifest.append({"family": "trusted_adjusted_analysis", "ticker": ticker, "status": record.get("status"), "source_url": record.get("source_url", ""), "source_hash": record.get("source_hash", ""), "response_bytes": record.get("response_bytes", 0), "retrieved_at": record.get("retrieved_at", ""), "blocked_reason": record.get("error", ""), **FLAGS})
            CURRENT_STEP.write_text(f"fetch_bounded_yahoo_active_candidates {count}/{len(yahoo_targets)}", encoding="utf-8")

    columns = ["date", "ticker", "name", "market", "raw_open_comparator", "raw_high_comparator", "raw_low_comparator", "raw_close_comparator", "adjustment_factor", "adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieved_at", "available_at_policy", "accepted_for_formal", "human_review_required", "future_data_violation_count", *FLAGS]
    existing = existing.rename(columns={"retrieval_time_utc": "retrieved_at"})
    all_adjusted = pd.concat([existing.reindex(columns=columns), pd.DataFrame(yahoo).reindex(columns=columns)], ignore_index=True)
    all_adjusted["date"] = pd.to_datetime(all_adjusted["date"], errors="coerce").dt.date.astype(str)
    all_adjusted = all_adjusted.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    write_csv(OUT / "ridge_shadow_current_adjusted_analysis_ohlc_factor_rows.csv.gz", all_adjusted)
    sample = pd.concat([all_adjusted.groupby("ticker", as_index=False).head(1), all_adjusted.groupby("ticker", as_index=False).tail(1)], ignore_index=True)
    sample.sort_values(["ticker", "date"]).to_csv(OUT / "ridge_shadow_current_adjusted_analysis_sample.csv", index=False, encoding="utf-8-sig")

    coverage = []
    blocked = []
    for row in scope.to_dict("records"):
        part = all_adjusted[all_adjusted["ticker"] == row["ticker"]]
        latest = part["date"].max() if len(part) else ""
        hlc_ready = int(part[["adjusted_high", "adjusted_low", "adjusted_close"]].notna().all(axis=1).sum()) if len(part) else 0
        ready = latest == SNAPSHOT.date().isoformat() and hlc_ready >= 60
        coverage.append({"ticker": row["ticker"], "name": row["name"], "market": row["market"], "required_start": LOOKBACK_START.date().isoformat(), "required_end": SNAPSHOT.date().isoformat(), "row_count": len(part), "hlc_ready_rows": hlc_ready, "actual_start": part["date"].min() if len(part) else "", "actual_end": latest, "current_date_ready": latest == SNAPSHOT.date().isoformat(), "minimum_60td_hlc_ready": hlc_ready >= 60, "status": "ready_research_grade" if ready else "blocked_or_partial", **FLAGS})
        if not ready:
            blocked.append({"ticker": row["ticker"], "name": row["name"], "market": row["market"], "blocked_component": "trusted_adjusted_analysis_ohlc_continuity", "blocked_reason": "no trusted free series" if not len(part) else f"latest={latest};hlc_ready_rows={hlc_ready}", "free_route_exhausted": not len(part), "silent_fill_used": False, **FLAGS})
    write_csv(OUT / "ridge_shadow_current_adjusted_coverage_by_ticker.csv", coverage)
    write_csv(OUT / "ridge_shadow_current_adjusted_blocked_ledger.csv", blocked, fields=["ticker", "name", "market", "blocked_component", "blocked_reason", "free_route_exhausted", "silent_fill_used", *FLAGS])

    CURRENT_STEP.write_text("corporate_action_review_61", encoding="utf-8")
    review_scope = scope[scope["corporate_action_adjusted_analysis_review_required"].astype(str).str.lower() == "true"]
    events = pd.read_csv(P3 / "compact" / "corporate_action_guard" / "events.csv.gz", dtype={"ticker": str})
    events["ticker"] = events["ticker"].str.zfill(4)
    events = events[events["ticker"].isin(set(review_scope["ticker"]))].copy()
    events.to_csv(OUT / "ridge_shadow_current_corporate_action_event_rows.csv", index=False, encoding="utf-8-sig")
    corp_review = []
    for row in review_scope.to_dict("records"):
        part = events[events["ticker"] == row["ticker"]]
        price = all_adjusted[all_adjusted["ticker"] == row["ticker"]]
        factor_changes = pd.to_numeric(price["adjustment_factor"], errors="coerce").round(10).nunique() if len(price) else 0
        corp_review.append({"ticker": row["ticker"], "name": row["name"], "market": row["market"], "official_event_inventory_rows": len(part), "event_types": "|".join(sorted(set(part.get("event_type", pd.Series(dtype=str)).dropna().astype(str)))), "exact_effective_date_rows": int(part.get("effective_date", pd.Series(dtype=str)).notna().sum()), "trusted_adjustment_factor_distinct_values": factor_changes, "current_adjusted_analysis_ready": bool(price["date"].max() == SNAPSHOT.date().isoformat()) if len(price) else False, "review_status": "source_evidence_ready_core_factor_policy_review_required" if len(part) and len(price) else "blocked_missing_event_or_price_source", "accepted_for_formal": False, "human_review_required": True, **FLAGS})
    write_csv(OUT / "ridge_shadow_current_corporate_action_review_ledger.csv", corp_review)

    CURRENT_STEP.write_text("materialize_new_ticker_fundamental_pit", encoding="utf-8")
    monthly_frames = []
    for path in sorted((MONTHLY / "accepted_monthly_revenue_rows_shards").glob("*.csv")):
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame = frame[frame["ticker"].isin(NEW_TICKERS)]
        if len(frame): monthly_frames.append(frame)
    monthly = pd.concat(monthly_frames, ignore_index=True)
    monthly = monthly[pd.to_datetime(monthly["available_date"], errors="coerce") <= SNAPSHOT]
    monthly["fundamental_family"] = "monthly_revenue"
    quarterly_frames = []
    for path in sorted((QUARTERLY / "shards").glob("*.csv")):
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame = frame[frame["ticker"].isin(NEW_TICKERS)]
        if len(frame): quarterly_frames.append(frame)
    quarterly = pd.concat(quarterly_frames, ignore_index=True)
    quarterly = quarterly[pd.to_datetime(quarterly["available_date"], errors="coerce") <= SNAPSHOT]
    quarterly["report_period"] = quarterly["fiscal_year"].astype(str) + "Q" + quarterly["quarter"].astype(str)
    quarterly["fundamental_family"] = "quarterly_income_profitability_margin"
    write_csv(OUT / "ridge_shadow_current_new_ticker_monthly_revenue_pit_rows.csv.gz", monthly)
    write_csv(OUT / "ridge_shadow_current_new_ticker_quarterly_fundamental_pit_rows.csv.gz", quarterly)

    indicator_results = fetch_mops_indicators(sorted(NEW_TICKERS))
    indicator_rows = []
    for result in indicator_results:
        source_manifest.append({"family": "new_ticker_mops_indicator", "metric": result["metric"], "status": result["status"], "source_url": MOPS_URL, "source_hash": result.get("source_hash", ""), "response_bytes": result.get("response_bytes", 0), "retrieved_at": result.get("retrieved_at", ""), "blocked_reason": result.get("error", ""), **FLAGS})
        if result["status"] != "accepted": continue
        payload = result["payload"]
        periods = payload.get("xaxisList") or []
        for index, header in enumerate(payload.get("showNameList") or []):
            match = re.match(r"(\d{4})", str(header))
            if not match or index >= len(payload.get("graphData") or []): continue
            ticker = match.group(1)
            if ticker not in NEW_TICKERS: continue
            for point in payload["graphData"][index].get("data") or []:
                if len(point) < 2 or point[1] is None or int(point[0]) >= len(periods): continue
                period = periods[int(point[0])]
                if not re.match(r"202[3-6]Q[1-4]", period): continue
                available = conservative_available(period)
                if pd.Timestamp(available) > SNAPSHOT: continue
                indicator_rows.append({"ticker": ticker, "report_period": period, "field": MOPS_METRICS[result["metric"]], "value": point[1], "available_date": available, "available_date_quality": "conservative_statutory_deadline_proxy_diagnostic", "source_quality": "official_period_specific_diagnostic_pit_proxy", "source_url": MOPS_URL, "source_hash": result["source_hash"], "accepted_for_formal": False, "human_review_required": True, "future_data_violation_count": 0, **FLAGS})
    write_csv(OUT / "ridge_shadow_current_new_ticker_balance_cashflow_pit_rows.csv", indicator_rows)

    fundamental_coverage = []
    for ticker in sorted(NEW_TICKERS):
        m = monthly[monthly["ticker"] == ticker]
        q = quarterly[quarterly["ticker"] == ticker]
        ind = [r for r in indicator_rows if r["ticker"] == ticker]
        fundamental_coverage.append({"ticker": ticker, "monthly_revenue_rows": len(m), "monthly_latest_available_date": m["available_date"].max() if len(m) else "", "quarterly_income_rows": len(q), "quarterly_latest_report_period": q["report_period"].max() if len(q) else "", "balance_cashflow_indicator_rows": len(ind), "balance_cashflow_fields": "|".join(sorted({r["field"] for r in ind})), "exact_pit_asof_2026_07_09_ready": bool(len(m) and len(q) and len(ind)), "current_snapshot_backfill_used": False, "future_data_violation_count": 0, **FLAGS})
    write_csv(OUT / "ridge_shadow_current_new_ticker_fundamental_coverage.csv", fundamental_coverage)

    source_manifest.extend([
        {"family": "existing_adjusted_compact", "status": "reused", "source_path": str(P3 / "compact" / "adjusted"), "source_hash": "per annual gzip manifest", "row_count": len(existing), **FLAGS},
        {"family": "official_corporate_action_inventory", "status": "reused", "source_path": str(P3 / "compact" / "corporate_action_guard" / "events.csv.gz"), "source_hash": sha256_file(P3 / "compact" / "corporate_action_guard" / "events.csv.gz"), "row_count": len(events), **FLAGS},
        {"family": "official_mops_monthly_revenue", "status": "reused", "source_path": str(MONTHLY / "accepted_monthly_revenue_rows_shards"), "source_hash": "per shard source manifest", "row_count": len(monthly), **FLAGS},
        {"family": "official_mops_quarterly_fundamentals", "status": "reused", "source_path": str(QUARTERLY / "shards"), "source_hash": "per shard source manifest", "row_count": len(quarterly), **FLAGS},
    ])
    source_manifest = sorted(source_manifest, key=lambda row: (str(row.get("family", "")), str(row.get("ticker", "")), str(row.get("metric", ""))))
    write_csv(OUT / "ridge_shadow_current_source_manifest.csv", source_manifest)
    write_csv(OUT / "ridge_shadow_current_future_data_audit.csv", [{"check": "snapshot_asof_filter", "status": "pass", "violation_count": 0, "notes": "All price rows <= 2026-07-09; MOPS rows require available_date <= 2026-07-09; period-end and retrieval time are never available_date.", **FLAGS}])

    adjusted_ready = sum(r["status"] == "ready_research_grade" for r in coverage)
    new_fund_ready = sum(r["exact_pit_asof_2026_07_09_ready"] for r in fundamental_coverage)
    readiness = {
        "task_id": TASK_ID,
        "status": "candidate_scoped_delta_ready_for_core_layer1_4_recompute" if adjusted_ready == len(scope) and new_fund_ready == 8 else "partial_candidate_scoped_delta_with_explicit_blockers",
        "source": "local official MOPS/corporate-action compacts plus bounded trusted-nonofficial Yahoo adjusted analysis",
        "coverage": {"active_tickers": len(scope), "adjusted_analysis_ready_tickers": adjusted_ready, "adjusted_analysis_blocked_tickers": len(scope) - adjusted_ready, "corporate_action_review_tickers": len(review_scope), "corporate_action_event_rows": len(events), "new_context_tickers": 8, "new_context_fundamental_ready_tickers": new_fund_ready, "price_rows": len(all_adjusted)},
        "future_data_violation_count": 0,
        "ready_for_core_layer1_4_recompute": adjusted_ready == len(scope) and new_fund_ready == 8,
        "ready_for_core_rerun": adjusted_ready == len(scope) and new_fund_ready == 8,
        "ready_for_strategy_replay": False,
        "ready_for_experiments": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "portfolio_replay_executed": False,
        "ready_for_formal": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
    }
    write_json(OUT / "readiness_for_core_p3_ridge_shadow_current_layer1_4_delta.json", readiness)
    CURRENT_STEP.write_text("completed_ready_for_core_layer1_4_recompute" if readiness["ready_for_core_layer1_4_recompute"] else "completed_partial_with_explicit_blockers", encoding="utf-8")
    write_json(OUT / "checkpoint.json", {"task_id": TASK_ID, "current_step": CURRENT_STEP.read_text(encoding="utf-8"), "resume_command": "python -X utf8 build_package.py", "updated_at": now()})
    summary = f"""# P3 Ridge shadow current Layer1-4 bounded delta source package\n\n- Status: {readiness['status']}\n- Active candidate scope: {len(scope)} tickers。\n- Trusted adjusted-analysis continuity: {adjusted_ready}/{len(scope)} tickers；blocked {len(scope)-adjusted_ready}。\n- Corporate-action review: {len(review_scope)} tickers / {len(events)} official event inventory rows。\n- New Layer1-3 context: {new_fund_ready}/8 tickers have PIT monthly revenue, quarterly fundamentals and MOPS balance/cashflow indicators。\n- Raw execution prices are not used as adjusted analysis prices。\n- Core must run the frozen Layer1-4 pipeline; Radar does not select primary80 or calculate Ridge predictions。\n- future_data_violation_count=0。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    artifacts = []
    for path in sorted(OUT.iterdir()):
        if not path.is_file() or path.name == "manifest.json": continue
        artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_json(OUT / "manifest.json", {"task_id": TASK_ID, "generated_at": now(), "artifacts": artifacts, "readiness": readiness, **FLAGS})


if __name__ == "__main__":
    main()
