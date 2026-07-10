import csv
import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-PATH-HOLDING-MONTH-CORPORATE-ACTION-NO-EVENT-PROOF-001"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
LEDGER_CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_stock_total_return_corporate_action_ledger_20260710")
PRIOR_ROUTE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_selected_stock_exact_exdate_capital_change_route_unlock_20260710")
PRIOR_ARCHIVE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_selected_stock_corporate_action_distribution_source_package_20260710")
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False,
         "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False,
         "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}
TYPES = ["cash_dividend_exdiv", "stock_dividend_exright", "capital_reduction_refund", "split_reverse_split_par_change", "merger_share_conversion"]

def load_base():
    spec = importlib.util.spec_from_file_location("mops_base", PRIOR_ROUTE / "build_package.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    mod.OUT, mod.RAW = OUT, RAW
    return mod

def rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))

def write_csv(path, data):
    keys, seen = [], set()
    for row in data:
        for key in row:
            if key not in seen: seen.add(key); keys.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(data)

def roc_month(date_text):
    d = datetime.strptime(date_text[:10], "%Y-%m-%d")
    return str(d.year - 1911), f"{d.month:02d}"

def ad_date(text):
    m = re.search(r"(\d{2,3})[年/]\s*(\d{1,2})[月/]\s*(\d{1,2})", text or "")
    if not m: return ""
    return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

def classify(text):
    t = text or ""
    result = set()
    if any(x in t for x in ["除息", "現金股利", "現金股息", "現金股利發放"]): result.add("cash_dividend_exdiv")
    if any(x in t for x in ["除權", "股票股利", "配股", "盈餘轉增資"]): result.add("stock_dividend_exright")
    if any(x in t for x in ["減資", "退還股款", "退還股東"]): result.add("capital_reduction_refund")
    if any(x in t for x in ["股票分割", "反分割", "併股", "股份合併", "面額變更", "變更面額"]): result.add("split_reverse_split_par_change")
    if any(x in t for x in ["股份轉換", "換股比例", "合併基準日", "吸收合併", "簡易合併"]): result.add("merger_share_conversion")
    if "合併" in t and not any(x in t for x in ["合併營收", "合併營業額", "合併財報", "合併財務報告", "合併損益"]): result.add("merger_share_conversion")
    return sorted(result)

def detail_effective_dates(text, base):
    fields = base.parse_detail_fields(text)
    if not fields.get("share_adjustment_effective_date"):
        for label in ["減資換發股票基準日", "新股換發基準日"]:
            m = re.search(label + r"[:：]?\s*([^。；;\n]+)", text or "")
            if m: fields["share_adjustment_effective_date"] = ad_date(m.group(1)); break
    if not fields.get("trading_resumption_date"):
        for label in ["新股票上市暨舊股票停止流通日期", "新股上市買賣日", "新股上櫃買賣日", "恢復買賣日期"]:
            m = re.search(label + r"[:：]?\s*([^。；;\n]+)", text or "")
            if m: fields["trading_resumption_date"] = ad_date(m.group(1)); break
    return fields

def within(date, legs):
    return bool(date and any(r["hold_start"] <= date < r["hold_end_exclusive"] for r in legs))

def main():
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("01_load_core_actual_holding_intervals\n", encoding="utf-8")
    base = load_base()
    intervals = [r for r in rows(LEDGER_CORE / "selected_stock_actual_holding_legs.csv") if r["asset_type"] == "stock"]
    universe = {r["ticker"]: r for r in rows(LEDGER_CORE / "selected_stock_total_return_universe.csv") if r["instrument_type"] == "ordinary_stock"}
    event_market = {r["ticker"]: r.get("market", "unknown") for r in rows(LEDGER_CORE / "selected_stock_total_return_event_ledger_template.csv")}
    by_ticker = defaultdict(list)
    for row in intervals: by_ticker[row["ticker"]].append(row)
    query_scopes = sorted({(r["ticker"],) + roc_month(r["hold_start"]) for r in intervals})

    cache, events, query_rows = [], [], []
    for i, (ticker, year, month) in enumerate(query_scopes, 1):
        (OUT / "current_step.txt").write_text(f"02_query {i}/{len(query_scopes)} {ticker} {year}-{month}\n", encoding="utf-8")
        payload = {"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""}
        data, meta = base.post_json("t05st01", payload, f"no_event_{ticker}_{year}_{month}_list")
        cache.append(meta)
        list_rows = (((data or {}).get("result") or {}).get("data") or [])
        mops_kind = next((str(v.get("parameters", {}).get("marketKind", "")) for raw in list_rows for v in raw if isinstance(v, dict) and v.get("parameters", {}).get("marketKind")), "")
        market = event_market.get(ticker, "unknown")
        if market == "unknown": market = {"sii": "TWSE", "otc": "TPEx"}.get(mops_kind, "unknown")
        query_rows.append({"ticker": ticker, "market": market, "year_roc": year, "month": month,
            "query_scope": f"{ticker} ROC{year}/{month}", "holding_legs_in_month": sum(roc_month(x["hold_start"]) == (year, month) for x in by_ticker[ticker]),
            "official_route": "MOPS t05st01", "response_status": meta["route_status"], "response_rows": len(list_rows),
            "payload": meta["payload"], "payload_hash": meta["payload_hash"], "response_hash": meta["response_hash"], "raw_cache_path": meta["raw_cache_path"],
            "retrieved_at_utc": meta["retrieved_at_utc"], "future_data_violation_count": 0, **FLAGS})
        for pos, raw in enumerate(list_rows):
            ref = next((v for v in raw if isinstance(v, dict) and v.get("apiName")), None)
            if not ref: continue
            _, detail, detail_status = base.detail_from_ref(ref, {"event_key": f"{ticker}_{year}_{month}"}, f"{pos}", cache)
            subject = str(raw[4] if len(raw) > 4 else "")
            text = subject + "\n" + detail
            kinds = classify(text)
            if not kinds: continue
            fields = detail_effective_dates(text, base)
            effective = fields.get("ex_date") or fields.get("share_adjustment_effective_date") or fields.get("trading_resumption_date")
            events.append({"ticker": ticker, "market": market, "year_roc": year, "month": month,
                "announcement_date_roc": str(raw[2] if len(raw) > 2 else ""), "announcement_time": str(raw[3] if len(raw) > 3 else ""),
                "subject": subject, "event_types": "|".join(kinds), "detail_status": detail_status, "detail_text_excerpt": re.sub(r"\s+", " ", detail)[:1200],
                "ex_date": fields.get("ex_date", ""), "payment_date": fields.get("payment_date", ""),
                "share_adjustment_effective_date": fields.get("share_adjustment_effective_date", ""), "trading_resumption_date": fields.get("trading_resumption_date", ""),
                "effective_date_for_holding_test": effective, "official_holding_overlap": within(effective, by_ticker[ticker]),
                "source_route": "MOPS t05st01/t05st01_detail", "source_url": "https://mops.twse.com.tw/mops/#/web/t05st01",
                "future_data_violation_count": 0, **FLAGS})

    (OUT / "current_step.txt").write_text("03_classify_no_event_proof\n", encoding="utf-8")
    proof, blocked, entitled = [], [], []
    for query in query_rows:
        relevant = [e for e in events if e["ticker"] == query["ticker"] and e["year_roc"] == query["year_roc"] and e["month"] == query["month"]]
        for kind in TYPES:
            matches = [e for e in relevant if kind in e["event_types"].split("|")]
            overlap = [e for e in matches if str(e["official_holding_overlap"]) == "True"]
            date_missing = [e for e in matches if not e["effective_date_for_holding_test"]]
            if query["response_status"] not in ("fetched", "cache_hit"):
                status, reason = "blocked_query_failure", "official_mops_month_query_not_successful"
            elif overlap:
                status, reason = "entitled_event_candidate", "official_event_effective_date_overlaps_selected_holding"
            elif date_missing:
                status, reason = "blocked_event_candidate_missing_effective_date", "official_event_candidate_requires_exact_effective_date_before_no_event_proof"
            elif not matches:
                status, reason = "no_event_proven", "official_mops_month_response_success_and_zero_classified_event_rows"
            else:
                status, reason = "event_outside_held_dates_proven", "official_event_has_explicit_effective_date_outside_actual_holding_intervals"
            row = {**query, "event_type": kind, "classified_event_rows": len(matches), "overlap_event_rows": len(overlap), "missing_effective_date_rows": len(date_missing),
                   "proof_status": status, "proof_reason": reason, "future_data_violation_count": 0, **FLAGS}
            proof.append(row)
            if status.startswith("blocked"): blocked.append(row)
            if status == "entitled_event_candidate": entitled.extend(overlap)

    # Existing exchange archives are official but expressly partial historical coverage. Retain the
    # manifest evidence and do not use their missing rows as a no-event conclusion.
    archive_manifest = rows(PRIOR_ARCHIVE / "selected_stock_event_source_manifest.csv")
    for row in archive_manifest:
        row["archive_coverage_policy"] = "historical_partial_not_accepted_for_no_event_proof_without_date_scoped_response"
        row["used_for_no_event_proof"] = False
        row["future_data_violation_count"] = 0
        row.update(FLAGS)
    manifest = cache + archive_manifest
    future = [
        {"audit_item": "board_or_shareholder_date_as_exdate", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "query_response_datetime_as_market_available", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "zero_text_search_as_no_event_proof", "status": "prohibited_only_successful_structured_response_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "adjusted_close_or_performance", "status": "not_calculated", "future_data_violation_count": 0, **FLAGS}]

    (OUT / "current_step.txt").write_text("04_write_outputs\n", encoding="utf-8")
    write_csv(OUT / "selected_path_holding_intervals.csv", intervals)
    write_csv(OUT / "selected_path_holding_month_event_query_ledger.csv", query_rows)
    write_csv(OUT / "selected_path_holding_month_no_event_proof.csv", proof)
    write_csv(OUT / "selected_path_entitled_event_candidates.csv", entitled)
    write_csv(OUT / "selected_path_no_event_proof_blocked_ledger.csv", blocked)
    write_csv(OUT / "selected_path_official_archive_source_manifest.csv", manifest)
    write_csv(OUT / "selected_path_future_data_audit.csv", future)
    counts = defaultdict(int)
    for r in proof: counts[r["proof_status"]] += 1
    readiness = {"task_id": TASK_ID, "status": "bounded_selected_path_holding_month_official_no_event_proof_completed",
        "source": "MOPS date-scoped t05st01/t05st01_detail plus TWSE/TPEx official historical-partial archive coverage audit",
        "coverage": {"actual_holding_intervals": len(intervals), "ticker_month_queries": len(query_rows), "event_type_proof_rows": len(proof),
            "no_event_proven_rows": counts["no_event_proven"], "event_outside_held_dates_proven_rows": counts["event_outside_held_dates_proven"],
            "entitled_event_candidate_rows": counts["entitled_event_candidate"], "blocked_rows": len(blocked), "mops_route_error_count": sum(x["response_status"] == "route_error" for x in query_rows)},
        "ready_for_core_selected_path_total_return_completeness_absorption": True,
        "selected_path_total_return_complete": len(blocked) == 0 and counts["entitled_event_candidate"] == 0,
        "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "future_data_violation_count": 0,
        "blocked_reason": "Only event types with a successful official date-scoped query and explicit zero classified rows are no_event_proven; partial exchange archives do not prove absence.", **FLAGS}
    (OUT / "readiness_for_core_selected_path_total_return_completeness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(f"# {TASK_ID}\n\n完成 actual selected holding ticker-month 的官方 no-event proof package。\n\n- holding intervals: {len(intervals)}\n- ticker-month queries: {len(query_rows)}\n- proof rows: {len(proof)}\n- no_event_proven: {counts['no_event_proven']}\n- event_outside_held_dates_proven: {counts['event_outside_held_dates_proven']}\n- entitled_event_candidates: {counts['entitled_event_candidate']}\n- blocked: {len(blocked)}\n- future_data_violation_count: 0\n\n未計 adjusted close、total-return factor 或策略績效。\n", encoding="utf-8")
    files = [{"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob("*")) if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files, "readiness": readiness, **FLAGS}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("complete\n", encoding="utf-8")

if __name__ == "__main__": main()
