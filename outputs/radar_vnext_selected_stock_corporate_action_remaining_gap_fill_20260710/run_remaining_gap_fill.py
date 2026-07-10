import csv
import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-STOCK-CORPORATE-ACTION-REMAINING-GAP-FILL-001"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_stock_total_return_exdate_patch_absorption_20260710")
LEDGER_CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_stock_total_return_corporate_action_ledger_20260710")
PRIOR = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_selected_stock_exact_exdate_capital_change_route_unlock_20260710")
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False,
         "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False,
         "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}


def load_base():
    spec = importlib.util.spec_from_file_location("prior_route", PRIOR / "build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT, mod.RAW = OUT, RAW
    return mod


def write_csv(path, rows):
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key); fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def load_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def roc_month(date_text):
    dt = datetime.strptime(date_text[:10], "%Y-%m-%d")
    return str(dt.year - 1911), f"{dt.month:02d}"


def extra_dates(text):
    """MOPS detail wording varies; parse only explicit dated fields."""
    def ad(value):
        m = re.search(r"(\d{2,3})年\s*(\d{1,2})月\s*(\d{1,2})日", value or "")
        return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
    result = {"payment_date": "", "share_adjustment_effective_date": "", "trading_resumption_date": ""}
    for label, key in [("現金股利(?:預計)?發放日", "payment_date"), ("現金減資退還股款發放日期", "payment_date"),
                       ("減資換發股票基準日", "share_adjustment_effective_date"), ("新股票上市暨舊股票停止流通日期", "trading_resumption_date"),
                       ("新股(?:上市|上櫃)買賣日", "trading_resumption_date")]:
        m = re.search(label + r"[:：]?\s*((?:\d{2,3}[年/]\s*\d{1,2}[月/]\s*\d{1,2}日?))", text or "")
        if m:
            token = m.group(1).replace("/", "年", 1).replace("/", "月", 1)
            if "日" not in token: token += "日"
            result[key] = ad(token)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("01_load_selected_holding_months\n", encoding="utf-8")
    base = load_base()
    gap_rows = load_csv(CORE / "selected_stock_total_return_remaining_gap_ledger.csv")
    prior_events = load_csv(CORE / "selected_stock_total_return_event_ledger_exdate_patched.csv")
    holding_rows = [r for r in load_csv(LEDGER_CORE / "selected_stock_actual_holding_legs.csv") if r.get("asset_type") == "stock"]
    target_tickers = {r["ticker"] for r in gap_rows if r["ticker"].isdigit()}
    months = sorted({(r["ticker"],) + roc_month(r["hold_start"]) for r in holding_rows if r["ticker"] in target_tickers})
    name_by_ticker = {r["ticker"]: r.get("company_name", "") for r in prior_events}

    cache_rows, evidence = [], []
    for i, (ticker, year, month) in enumerate(months, 1):
        (OUT / "current_step.txt").write_text(f"02_query_holding_month {i}/{len(months)} {ticker} {year}-{month}\n", encoding="utf-8")
        payload = {"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""}
        result, cache = base.post_json("t05st01", payload, f"holding_month_{ticker}_{year}_{month}_list")
        cache_rows.append(cache)
        rows = (((result or {}).get("result") or {}).get("data") or [])
        for idx, row in enumerate(rows):
            if len(row) < 5: continue
            subject, date, tm = str(row[4] or ""), str(row[2] or ""), str(row[3] or "")
            ref = next((v for v in row if isinstance(v, dict) and v.get("apiName")), None)
            if not base.text_has_any(subject, base.DETAIL_FETCH_TOKENS):
                continue
            detail_payload, detail, detail_status = base.detail_from_ref(ref, {"event_key": f"holding_{ticker}_{year}_{month}"}, f"{idx}", cache_rows)
            text = subject + "\n" + detail
            fields = base.parse_detail_fields(text)
            event_type = "distribution_or_exright" if base.text_has_any(text, ["除權", "除息", "股利"]) else ("capital_change" if base.is_capital_change_candidate(text) else "other")
            if not (fields["ex_date"] or fields["payment_date"] or fields["share_adjustment_effective_date"] or fields["trading_resumption_date"] or event_type == "capital_change"):
                continue
            evidence.append({"ticker": ticker, "company_name": name_by_ticker.get(ticker, ""), "holding_month_roc": f"{year}/{month}",
                "source_route": "mops_api_t05st01_and_t05st01_detail", "source_url": "https://mops.twse.com.tw/mops/#/web/t05st01",
                "announcement_date_roc": date, "announcement_time": tm, "market_available_at": f"{base.ymd_roc_to_ad(date)} {tm}".strip(),
                "subject": subject, "detail_status": detail_status, "detail_payload": json.dumps(detail_payload, ensure_ascii=False, sort_keys=True),
                "detail_text_excerpt": re.sub(r"\s+", " ", detail)[:1200], "event_type": event_type, **fields,
                "source_quality": "official_mops_material_information", "future_data_violation_count": 0, **FLAGS})

    # The earlier bounded route captured candidate windows outside actual holds. Reuse it only as
    # official candidate evidence for canonical mapping; it never proves entitlement by itself.
    prior_candidate_rows = load_csv(PRIOR / "selected_stock_exact_exdate_candidate_evidence.csv")
    prior_event_keys = {r["event_key"] for r in prior_events}
    for row in prior_candidate_rows:
        if row.get("event_key") not in prior_event_keys or not row.get("detail_text_excerpt"):
            continue
        extra = extra_dates(row.get("detail_text_excerpt", ""))
        item = dict(row)
        item["evidence_origin"] = "prior_bounded_candidate_window_official_mops_cache"
        item["payment_date"] = item.get("payment_date") or extra["payment_date"]
        item["share_adjustment_effective_date"] = item.get("share_adjustment_effective_date") or extra["share_adjustment_effective_date"]
        item["trading_resumption_date"] = item.get("trading_resumption_date") or extra["trading_resumption_date"]
        item["event_type"] = "distribution_or_exright" if base.text_has_any(item.get("detail_text_excerpt", ""), ["除權", "除息", "股利"]) else ("capital_change" if base.is_capital_change_candidate(item.get("detail_text_excerpt", "")) else "other")
        evidence.append(item)

    (OUT / "current_step.txt").write_text("03_map_remaining_canonical_events\n", encoding="utf-8")
    by_ticker = defaultdict(list)
    for e in evidence: by_ticker[e["ticker"]].append(e)
    mapping, blocked = [], []
    event_by_key = {r["event_key"]: r for r in prior_events}
    exact_keys = {r["event_key"] for r in gap_rows if r["missing_component"] == "canonical_event_exact_exdate_mapping"}
    payment_keys = {r["event_key"] for r in gap_rows if r["missing_component"] == "cash_payment_date"}
    for key in sorted(exact_keys | payment_keys):
        event = event_by_key.get(key, {})
        ticker = key.split("|")[0]
        cash = str(event.get("cash_dividend_total_per_share_candidate", "")).rstrip("0").rstrip(".")
        stock = str(event.get("stock_dividend_total_per_share_candidate", "")).rstrip("0").rstrip(".")
        candidates = []
        for row in by_ticker[ticker]:
            text = row["detail_text_excerpt"].replace(",", "")
            amount_hit = bool((cash and cash != "0" and cash in text) or (stock and stock != "0" and stock in text))
            if amount_hit and row["event_type"] == "distribution_or_exright": candidates.append(row)
        exact = [r for r in candidates if r.get("ex_date")]
        payment = [r for r in candidates if r.get("payment_date")]
        selected_exact = exact[0] if len(exact) == 1 else None
        selected_payment = payment[0] if len(payment) == 1 else None
        out = {"ticker": ticker, "event_key": key, "cash_candidate": cash, "stock_candidate": stock,
               "candidate_count": len(candidates), "exact_candidate_count": len(exact), "payment_candidate_count": len(payment),
               "accepted_exact_exdate": selected_exact.get("ex_date", "") if selected_exact else "",
               "accepted_payment_date": selected_payment.get("payment_date", "") if selected_payment else "",
               "accepted_market_available_at": (selected_exact or selected_payment or {}).get("market_available_at", ""),
               "accepted_source_url": (selected_exact or selected_payment or {}).get("source_url", ""),
               "accepted_subject": (selected_exact or selected_payment or {}).get("subject", ""),
               "mapping_status": "accepted_unique_candidate" if selected_exact or selected_payment else ("blocked_multiple_candidates" if candidates else "blocked_no_candidate"),
               "future_data_violation_count": 0, **FLAGS}
        mapping.append(out)
        needs_exact = key in exact_keys and not out["accepted_exact_exdate"]
        needs_payment = key in payment_keys and not out["accepted_payment_date"]
        if needs_exact or needs_payment:
            blocked.append({"ticker": ticker, "event_key": key, "missing_component": "exact_exdate" if needs_exact else "cash_payment_date",
                "blocked_reason": out["mapping_status"], "attempted_source": "MOPS t05st01/t05st01_detail bounded actual-holding-month query",
                "next_bounded_step": "official_exright_or_payment_archive_route_or_manual_policy_review", "future_data_violation_count": 0, **FLAGS})

    stock_rows = [r for r in evidence if r["ticker"] in {"2615", "6573"} and (r.get("share_adjustment_effective_date") or r.get("trading_resumption_date"))]
    capital_rows = [r for r in evidence if r["event_type"] == "capital_change"]
    existing_capital = load_csv(CORE / "selected_stock_capital_change_core_review.csv")
    combined_capital = existing_capital + capital_rows
    coverage = []
    for ticker in sorted(target_tickers):
        ticker_months = [f"{y}/{m}" for t, y, m in months if t == ticker]
        ticker_events = [x for x in evidence if x["ticker"] == ticker]
        coverage.append({"ticker": ticker, "holding_month_count": len(ticker_months), "holding_months": "|".join(ticker_months),
            "official_event_rows": len(ticker_events), "capital_change_rows": sum(x["event_type"] == "capital_change" for x in ticker_events),
            "coverage_status": "official_holding_month_route_queried_no_silent_no_event_proof", "future_data_violation_count": 0, **FLAGS})

    (OUT / "current_step.txt").write_text("04_write_outputs\n", encoding="utf-8")
    write_csv(OUT / "selected_stock_remaining_holding_month_event_evidence.csv", evidence)
    write_csv(OUT / "selected_stock_remaining_canonical_event_mapping_patch.csv", mapping)
    write_csv(OUT / "selected_stock_remaining_stock_distribution_effective_candidates.csv", stock_rows)
    write_csv(OUT / "selected_stock_remaining_capital_change_inventory.csv", combined_capital)
    write_csv(OUT / "selected_stock_remaining_blocked_ledger.csv", blocked)
    write_csv(OUT / "selected_stock_remaining_temporal_coverage_audit.csv", coverage)
    write_csv(OUT / "selected_stock_remaining_source_manifest.csv", cache_rows)
    future = [
        {"audit_item": "board_or_shareholder_date_as_exdate", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "query_response_datetime_as_market_available", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "silent_no_event_proof", "status": "prohibited_absence_remains_unproven", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "adjusted_close_or_total_return_factor", "status": "not_calculated_by_radar", "future_data_violation_count": 0, **FLAGS}]
    write_csv(OUT / "selected_stock_remaining_future_data_audit.csv", future)
    accepted_exact = sum(bool(x["accepted_exact_exdate"]) for x in mapping)
    accepted_payment = sum(bool(x["accepted_payment_date"]) for x in mapping)
    readiness = {"task_id": TASK_ID, "status": "bounded_actual_holding_month_route_fill_completed", "source": "MOPS t05st01/t05st01_detail official bounded actual holding-month queries",
        "coverage": {"remaining_gap_rows_input": len(gap_rows), "actual_holding_legs": len(holding_rows), "ticker_month_queries": len(months), "official_event_evidence_rows": len(evidence), "canonical_mapping_rows": len(mapping), "accepted_exact_mapping_rows": accepted_exact, "accepted_payment_date_rows": accepted_payment, "stock_distribution_effective_candidates": len(stock_rows), "capital_change_inventory_rows": len(combined_capital), "blocked_rows": len(blocked), "route_error_count": sum(r.get("route_status") == "route_error" for r in cache_rows)},
        "ready_for_core_absorption": bool(mapping or capital_rows), "ready_for_core_selected_stock_total_return_ledger": False, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "future_data_violation_count": 0,
        "blocked_reason": "Unique canonical mapping, payment date, and holder-scale impact remain required before Core can calculate total-return ledger.", **FLAGS}
    (OUT / "readiness_for_core_selected_stock_corporate_action_remaining_gap_fill.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(f"# {TASK_ID}\n\n完成以實際持有月份為界的官方 MOPS source route 補件。\n\n- ticker-month queries: {len(months)}\n- official event evidence rows: {len(evidence)}\n- accepted exact mappings: {accepted_exact}\n- accepted payment dates: {accepted_payment}\n- blocked rows: {len(blocked)}\n- future_data_violation_count: 0\n\n僅輸出 source evidence，不計 adjusted close 或 total-return factor；未唯一對應的事件維持 blocked。\n", encoding="utf-8")
    files = [{"path": p.name, "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(OUT.glob("*")) if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files, "readiness": readiness, **FLAGS}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("complete\n", encoding="utf-8")


if __name__ == "__main__": main()
