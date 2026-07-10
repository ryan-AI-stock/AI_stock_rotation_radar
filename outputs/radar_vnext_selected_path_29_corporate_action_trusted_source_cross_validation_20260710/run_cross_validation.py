import calendar
import csv
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-PATH-29-CORPORATE-ACTION-TRUSTED-SOURCE-CROSS-VALIDATION-001"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_path_34_effective_date_route_absorption_20260710")
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False,
         "report_changed": False, "portfolio_replay_executed": False, "ready_for_strategy_replay": False,
         "ready_for_formal": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}

def load(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))

def write(path, data):
    fields, seen = [], set()
    for row in data:
        for key in row:
            if key not in seen: seen.add(key); fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(data)

def fetch(url, name):
    RAW.mkdir(parents=True, exist_ok=True); path = RAW / name
    if path.exists(): text, status, error = path.read_text(encoding="utf-8"), "cache_hit", ""
    else:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RadarDataSourcePackage/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r: text = r.read().decode("utf-8")
            path.write_text(text, encoding="utf-8"); status, error = "fetched", ""
        except Exception as exc:
            text, status, error = json.dumps({"error": str(exc)}), "route_error", str(exc)
            path.write_text(text, encoding="utf-8")
        time.sleep(0.05)
    return text, {"source_url": url, "raw_cache_path": str(path.relative_to(OUT)), "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(), "response_bytes": len(text.encode("utf-8")), "route_status": status, "route_error": error, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "future_data_violation_count": 0, **FLAGS}

def ad_year(roc): return int(roc) + 1911
def epoch(s): return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
def date_from_epoch(v): return datetime.fromtimestamp(v, timezone.utc).strftime("%Y-%m-%d")
def amount_close(a, b):
    try: return abs(float(a) - float(b)) <= max(0.01, abs(float(a)) * 0.015)
    except Exception: return False

def suffix(market): return ".TW" if market == "TWSE" else ".TWO"

def finmind_url(ticker, start, end):
    return "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode({"dataset": "TaiwanStockDividend", "data_id": ticker, "start_date": start, "end_date": end})

def yahoo_url(symbol, start, end):
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?" + urllib.parse.urlencode({"period1": epoch(start), "period2": epoch(end), "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})

def main():
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("01_load_29_structural_rows\n", encoding="utf-8")
    targets = load(CORE / "selected_path_remaining_29_structural_source_exhausted_ledger.csv")
    inventory = []
    for ticker in sorted({r["ticker"] for r in targets}):
        subset = [r for r in targets if r["ticker"] == ticker]
        inventory.append({"ticker": ticker, "market": subset[0]["market"], "target_rows": len(subset), "providers": "local_official_unadjusted_ohlc|Yahoo Finance chart events/adjusted close|FinMind TaiwanStockDividend", "local_adjusted_close_found": False, "source_inventory_status": "local_price_rows_unadjusted_only; trusted_nonofficial_cross_validation_required", "future_data_violation_count": 0, **FLAGS})

    candidates, reconciliation, agreement, manifest = [], [], [], []
    results = []
    for n, row in enumerate(targets, 1):
        (OUT / "current_step.txt").write_text(f"02_cross_validate {n}/{len(targets)} {row['ticker']} ROC{row['year_roc']}/{row['month']} {row['event_type']}\n", encoding="utf-8")
        year, month = ad_year(row["year_roc"]), int(row["month"])
        start = f"{year:04d}-{month:02d}-01"
        # Future ex-date can follow a board/announcement month; one-year bounded look-ahead is source matching, not a trading rule.
        end = f"{year+1:04d}-{month:02d}-{min(calendar.monthrange(year+1, month)[1], 28):02d}"
        fm_text, fm_meta = fetch(finmind_url(row["ticker"], start, end), f"finmind_dividend_{row['ticker']}_{year}_{month:02d}.json")
        yh_text, yh_meta = fetch(yahoo_url(row["ticker"] + suffix(row["market"]), start, end), f"yahoo_chart_{row['ticker']}_{row['market']}_{year}_{month:02d}.json")
        fm_meta.update({"provider": "FinMind", "source_quality": "trusted_nonofficial_structured_free_access_observed", "ticker": row["ticker"], "target_scope": row["ticker_month_key"]})
        yh_meta.update({"provider": "Yahoo Finance", "source_quality": "trusted_nonofficial_structured_chart_events", "ticker": row["ticker"], "target_scope": row["ticker_month_key"]})
        manifest.extend([fm_meta, yh_meta])
        try: fm_rows = json.loads(fm_text).get("data", [])
        except Exception: fm_rows = []
        try: chart = (json.loads(yh_text).get("chart", {}).get("result") or [])[0] or {}
        except Exception: chart = {}
        events = chart.get("events", {}) or {}
        y_div = [{"date": date_from_epoch(int(k)), "amount": v.get("amount")} for k, v in (events.get("dividends") or {}).items()]
        y_split = [{"date": date_from_epoch(int(k)), "numerator": v.get("numerator"), "denominator": v.get("denominator")} for k, v in (events.get("splits") or {}).items()]
        ts = chart.get("timestamp") or []
        quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
        adj = ((chart.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        closes = quote.get("close") or []
        raw_adj = {date_from_epoch(t): {"close": closes[i] if i < len(closes) else None, "adjclose": adj[i] if i < len(adj) else None} for i, t in enumerate(ts)}

        fm_candidates = []
        for item in fm_rows:
            ann = str(item.get("AnnouncementDate") or "")
            if not ann.startswith(f"{year:04d}-{month:02d}"): continue
            cash = float(item.get("CashEarningsDistribution") or 0) + float(item.get("CashStatutorySurplus") or 0)
            stock = float(item.get("StockEarningsDistribution") or 0) + float(item.get("StockStatutorySurplus") or 0)
            if row["event_type"] == "cash_dividend_exdiv" and cash > 0 and item.get("CashExDividendTradingDate"):
                fm_candidates.append({"date": item["CashExDividendTradingDate"], "amount": cash, "payment_date": item.get("CashDividendPaymentDate", ""), "kind": "cash"})
            elif row["event_type"] == "stock_dividend_exright" and stock > 0 and item.get("StockExDividendTradingDate"):
                fm_candidates.append({"date": item["StockExDividendTradingDate"], "amount": stock, "payment_date": "", "kind": "stock"})
        selected = fm_candidates[0] if len(fm_candidates) == 1 else None
        yahoo_type_events = y_div if row["event_type"] == "cash_dividend_exdiv" else y_split
        yahoo_matches = []
        if selected:
            source_events = y_div if selected["kind"] == "cash" else y_split
            for item in source_events:
                same_date = item["date"] == selected["date"]
                same_amount = selected["kind"] != "cash" or amount_close(item.get("amount"), selected["amount"])
                if same_date and same_amount: yahoo_matches.append(item)
        price = raw_adj.get(selected["date"], {}) if selected else {}
        previous = raw_adj.get(date_from_epoch(epoch(selected["date"]) - 86400), {}) if selected else {}
        # Yahoo adjustment ratio is a reconciliation clue only; it is not an adjusted-close contract.
        factor = ""
        if price.get("close") and price.get("adjclose"):
            factor = round(float(price["adjclose"]) / float(price["close"]), 8)
        reconciliation.append({"ticker": row["ticker"], "ticker_month_key": row["ticker_month_key"], "event_type": row["event_type"], "candidate_effective_date": selected["date"] if selected else "", "yahoo_close": price.get("close", ""), "yahoo_adjusted_close": price.get("adjclose", ""), "yahoo_adjustment_ratio": factor, "prior_day_close": previous.get("close", ""), "reconciliation_status": "supporting_same_provider_adjusted_raw_reconciliation" if factor else "unavailable_no_selected_event", "future_data_violation_count": 0, **FLAGS})
        source_status = "blocked"
        if selected and len(yahoo_matches) == 1:
            source_status = "trusted_cross_source_agreement"
        elif selected:
            source_status = "trusted_structured_candidate_no_independent_agreement"
        elif len(yahoo_type_events) == 1:
            source_status = "trusted_nonofficial_inferred_yahoo_only"
        candidates.append({"ticker": row["ticker"], "market": row["market"], "ticker_month_key": row["ticker_month_key"], "event_type": row["event_type"], "finmind_candidate_count": len(fm_candidates), "finmind_effective_date": selected["date"] if selected else "", "finmind_amount_or_ratio": selected["amount"] if selected else "", "finmind_payment_date": selected["payment_date"] if selected else "", "yahoo_matching_event_count": len(yahoo_matches), "yahoo_match": json.dumps(yahoo_matches, ensure_ascii=False), "yahoo_type_event_count": len(yahoo_type_events), "yahoo_inferred_event": json.dumps(yahoo_type_events[0] if len(yahoo_type_events) == 1 else {}, ensure_ascii=False), "source_status": source_status, "future_data_violation_count": 0, **FLAGS})
        agreement.append({"ticker": row["ticker"], "ticker_month_key": row["ticker_month_key"], "event_type": row["event_type"], "source_a": "FinMind TaiwanStockDividend", "source_b": "Yahoo Finance chart dividends/splits", "agreement_status": source_status, "accepted_for_formal": False, "human_review_required": source_status != "trusted_cross_source_agreement", "future_data_violation_count": 0, **FLAGS})
        if source_status == "trusted_cross_source_agreement":
            resolution = "resolved_trusted_nonofficial_cross_validated"
            reason = "structured FinMind exact event agrees with independent Yahoo event date/amount"
        elif row["event_type"] in ("merger_share_conversion", "capital_reduction_refund"):
            resolution = "blocked_missing_holder_ratio_effective_date"
            reason = "FinMind dividend dataset/Yahoo chart does not establish required holder conversion ratio and effective date"
        elif source_status == "trusted_structured_candidate_no_independent_agreement":
            resolution = "blocked_single_trusted_source_only"
            reason = "exact event from one trusted nonofficial source lacks independent agreement"
        elif source_status == "trusted_nonofficial_inferred_yahoo_only":
            resolution = "blocked_yahoo_only_inferred"
            reason = "Yahoo event/adjusted-price clue lacks independent structured confirmation"
        else:
            resolution = "blocked_no_trusted_structured_candidate"
            reason = "bounded FinMind/Yahoo query found no candidate satisfying requested event type"
        results.append({**row, "resolution_status": resolution, "resolution_reason": reason, "trusted_effective_date": selected["date"] if selected else "", "trusted_payment_date": selected["payment_date"] if selected else "", "trusted_amount_or_ratio": selected["amount"] if selected else "", "future_data_violation_count": 0, **FLAGS})

    (OUT / "current_step.txt").write_text("03_write_outputs\n", encoding="utf-8")
    write(OUT / "selected_path_29_source_inventory.csv", inventory)
    write(OUT / "selected_path_29_trusted_event_candidates.csv", candidates)
    write(OUT / "selected_path_29_adjusted_raw_reconciliation.csv", reconciliation)
    write(OUT / "selected_path_29_cross_source_agreement.csv", agreement)
    write(OUT / "selected_path_29_resolved_rows.csv", [r for r in results if r["resolution_status"].startswith("resolved")])
    write(OUT / "selected_path_29_remaining_blocked.csv", [r for r in results if r["resolution_status"].startswith("blocked")])
    options = [
        {"provider": "Yahoo Finance chart", "source_type": "trusted_nonofficial_structured", "access": "public endpoint observed; no account used", "cost": "no purchase made", "coverage_or_limit": "dividend/split events and adjusted/raw prices; not authoritative for merger/capital-reduction holder terms", "use_status": "cross_validation_only", "future_data_violation_count": 0, **FLAGS},
        {"provider": "FinMind API", "source_type": "trusted_nonofficial_structured", "access": "TaiwanStockDividend endpoint returned data without token in this bounded check", "cost": "no purchase made", "coverage_or_limit": "cash/stock dividend fields including ex-date/payment date where supplied; no complete holder conversion/capital-reduction contract", "use_status": "cross_validation_only", "future_data_violation_count": 0, **FLAGS},
        {"provider": "TWSE Data E-Shop T48", "source_type": "licensed_official", "access": "not purchased/not accessed", "cost": "TWSE website states NT$5,000 per month for internal use", "coverage_or_limit": "effective date/right-interest fields; starts 2019-12-23 per website, so cannot cover all 2015-2019 rows", "use_status": "user_decision_required", "future_data_violation_count": 0, **FLAGS},
        {"provider": "TPEx T48 historical file", "source_type": "licensed_official", "access": "not purchased/not accessed", "cost": "inquire with TPEx", "coverage_or_limit": "candidate for TPEx effective-date/historical corporate-action coverage; terms and exact period require provider confirmation", "use_status": "user_decision_required", "future_data_violation_count": 0, **FLAGS}]
    write(OUT / "selected_path_29_provider_terms_and_cost_options.csv", options)
    write(OUT / "selected_path_29_future_data_audit.csv", [{"audit_item": "future_return_as_rule", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS}, {"audit_item": "trusted_source_as_formal", "status": "prohibited_trusted_nonofficial_only", "future_data_violation_count": 0, **FLAGS}, {"audit_item": "cash_dividend_reinvestment", "status": "not_assumed_payment_date_separate", "future_data_violation_count": 0, **FLAGS}])
    counts = {key: sum(r["resolution_status"] == key for r in results) for key in sorted({r["resolution_status"] for r in results})}
    readiness = {"task_id": TASK_ID, "status": "bounded_trusted_source_cross_validation_completed", "coverage": {"input_rows": len(targets), "resolved_trusted_nonofficial_rows": counts.get("resolved_trusted_nonofficial_cross_validated", 0), "remaining_blocked_rows": len(targets) - counts.get("resolved_trusted_nonofficial_cross_validated", 0), "route_error_count": sum(x["route_status"] == "route_error" for x in manifest)}, "ready_for_core_selected_path_trusted_source_absorption": True, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "future_data_violation_count": 0, "blocked_reason": "Trusted nonofficial evidence is diagnostic-only; unresolved merger/capital-reduction rows require holder terms, and all formal use remains blocked.", **FLAGS}
    (OUT / "readiness_for_core_selected_path_trusted_source_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(f"# {TASK_ID}\n\n完成 29 筆 bounded trusted-source cross-validation。\n\n- input rows: {len(targets)}\n- resolution: {json.dumps(counts, ensure_ascii=False)}\n- future_data_violation_count: 0\n\nYahoo Finance 與 FinMind 均標 trusted_nonofficial；未計 adjusted close、total-return factor 或績效，未購買或建立付費帳號。\n", encoding="utf-8")
    files = [{"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob("*")) if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files, "readiness": readiness, **FLAGS}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("complete\n", encoding="utf-8")

if __name__ == "__main__": main()
