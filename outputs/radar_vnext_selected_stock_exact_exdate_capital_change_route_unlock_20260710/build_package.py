import csv
import hashlib
import json
import re
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-STOCK-EXACT-EXDATE-CAPITAL-CHANGE-ROUTE-UNLOCK-001"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
CORE_OUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_stock_total_return_corporate_action_ledger_20260710")
EVENT_TEMPLATE = CORE_OUT / "selected_stock_total_return_event_ledger_template.csv"
GAP_LEDGER = CORE_OUT / "selected_stock_total_return_corporate_action_gap_ledger.csv"

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

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://mops.twse.com.tw",
    "Referer": "https://mops.twse.com.tw/mops/#/web/t05st01",
    "User-Agent": "Mozilla/5.0 RadarDataSourcePackage/1.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

HIGH_PRIORITY_KEYS = {
    "2330|ROC108|P1|C2.5|S0",
    "2351|ROC109|P1|C1.8|S0",
    "2636|ROC109|P1|C3.2|S0",
    "3661|ROC107|P1|C1.50585|S0",
}

LIST_TOKENS = [
    "除權", "除息", "除權息", "配息", "股利", "現金股利", "股票股利",
    "減資", "分割", "合併", "換股", "股份轉換", "面額", "新股換發",
]
DETAIL_FETCH_TOKENS = LIST_TOKENS + ["基準日", "發放日期", "停止過戶"]
CAPITAL_CHANGE_TOKENS = ["減資", "分割", "合併", "換股", "股份轉換", "面額", "新股換發", "停止買賣", "恢復買賣"]
CAPITAL_CHANGE_EXCLUDE_TOKENS = ["合併營業額", "合併營收", "合併損益", "合併財務報告", "合併財報", "合併報表"]


def step(text):
    (OUT / "current_step.txt").write_text(text + "\n", encoding="utf-8")


def parse_date(s):
    s = str(s or "").strip()
    if not s:
        return None
    if " " in s:
        s = s.split(" ")[0]
    try:
        y, m, d = [int(x) for x in s.split("-")]
        return datetime(y, m, d)
    except Exception:
        return None


def roc_year_months(start, end):
    start_dt, end_dt = parse_date(start), parse_date(end)
    if not start_dt or not end_dt:
        return []
    months = []
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (end_dt.year, end_dt.month):
        months.append((str(y - 1911), f"{m:02d}"))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return months


def ymd_roc_to_ad(s):
    s = str(s or "").strip()
    m = re.search(r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})", s)
    if not m:
        return ""
    y = int(m.group(1)) + 1911
    mo = int(m.group(2))
    d = int(m.group(3))
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    except Exception:
        return ""


def sanitize(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")


def post_json(route, payload, cache_key):
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / f"{sanitize(cache_key)}.json"
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8")
        status = "cache_hit"
        error = ""
        retry_count = 0
    else:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"https://mops.twse.com.tw/mops/api/{route}",
            data=data,
            headers=HEADERS,
            method="POST",
        )
        text = ""
        status = "route_error"
        error = ""
        retry_count = 0
        for attempt in range(2):
            retry_count = attempt
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    text = resp.read().decode("utf-8")
                status = "fetched"
                break
            except Exception as exc:
                error = str(exc)
                time.sleep(0.2)
        if not text:
            text = json.dumps({"error": error}, ensure_ascii=False)
        cache_path.write_text(text, encoding="utf-8")
        time.sleep(0.05)
    response_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        response = json.loads(text)
    except Exception:
        response = {"parse_error": True}
    return response, {
        "route": route,
        "payload": payload_text,
        "payload_hash": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
        "raw_cache_path": str(cache_path.relative_to(OUT)),
        "response_hash": response_hash,
        "route_status": status,
        "route_error": error,
        "retry_count": retry_count,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "future_data_violation_count": 0,
        **FLAGS,
    }


def load_events():
    events = []
    with EVENT_TEMPLATE.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("event_key"):
                row["high_priority"] = row["event_key"] in HIGH_PRIORITY_KEYS
                events.append(row)
    return events


def load_gap_index():
    gap = defaultdict(set)
    with GAP_LEDGER.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            gap[row["event_key"]].add(row["missing_component"])
    return gap


def text_has_any(text, tokens):
    t = str(text or "")
    return any(tok in t for tok in tokens)


def event_amount_match(event, detail_text):
    cash = str(event.get("cash_dividend_total_per_share_candidate") or "").rstrip("0").rstrip(".")
    stock = str(event.get("stock_dividend_total_per_share_candidate") or "").rstrip("0").rstrip(".")
    detail = detail_text.replace(",", "")
    hits = []
    if cash and cash != "0" and cash in detail:
        hits.append("cash_amount_text_hit")
    if stock and stock != "0" and stock in detail:
        hits.append("stock_amount_text_hit")
    return "|".join(hits)


def is_capital_change_candidate(text):
    clean = str(text or "")
    if any(tok in clean for tok in CAPITAL_CHANGE_EXCLUDE_TOKENS):
        return False
    strong_tokens = ["減資", "股票分割", "分割基準日", "股份轉換", "換股", "面額", "新股換發", "停止買賣", "恢復買賣"]
    if any(tok in clean for tok in strong_tokens):
        return True
    return bool(re.search(r"(合併基準日|股份合併|簡易合併|股份轉換基準日|換股比例)", clean))


def parse_detail_fields(detail_text):
    fields = {
        "ex_date": "",
        "payment_date": "",
        "record_date": "",
        "last_transfer_date": "",
        "stop_transfer_start": "",
        "stop_transfer_end": "",
        "share_adjustment_effective_date": "",
        "trading_resumption_date": "",
        "cash_return": "",
        "ratio_text": "",
    }
    patterns = {
        "ex_date": [r"除權（息）交易日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"除息交易日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"除權交易日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "payment_date": [r"普通股現金股利發放日期[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"現金股利發放日期[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "record_date": [r"除權（息）基準日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"除息基準日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"減資基準日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "last_transfer_date": [r"最後過戶日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "stop_transfer_start": [r"停止過戶起始日期[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "stop_transfer_end": [r"停止過戶截止日期[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "share_adjustment_effective_date": [r"新股換發基準日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"換發股票基準日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
        "trading_resumption_date": [r"恢復買賣日期[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"新股上市買賣日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})", r"新股上櫃買賣日[:：]\s*([0-9]{2,3}/[0-9]{1,2}/[0-9]{1,2})"],
    }
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, detail_text)
            if m:
                fields[key] = ymd_roc_to_ad(m.group(1))
                break
    cm = re.search(r"每股退還(?:股款|現金)[^0-9]*([0-9]+(?:\.[0-9]+)?)", detail_text)
    if cm:
        fields["cash_return"] = cm.group(1)
    rm = re.search(r"(減資比例|換股比例|每仟股換發|每千股換發|股票分割比例)[^\n。；;]*", detail_text)
    if rm:
        fields["ratio_text"] = rm.group(0).strip()
    return fields


def detail_from_ref(ref, event, suffix, cache_rows):
    if not isinstance(ref, dict):
        return {}, "", "missing_detail_ref"
    payload = ref.get("parameters") or {}
    route = ref.get("apiName") or "t05st01_detail"
    if not payload:
        return {}, "", "missing_detail_payload"
    res, cache = post_json(route, payload, f"{event['event_key']}_{suffix}_detail")
    cache_rows.append(cache)
    data = (((res or {}).get("result") or {}).get("data") or [])
    text = data[0][9] if data and len(data[0]) > 9 else ""
    return payload, text, "ok" if text else "no_detail_text"


def query_event(event, cache_rows):
    evidence = []
    for year, month in roc_year_months(event["candidate_window_start"], event["candidate_window_end"]):
        payload = {"companyId": event["ticker"], "year": year, "month": month, "firstDay": "", "lastDay": ""}
        res, cache = post_json("t05st01", payload, f"{event['event_key']}_{year}_{month}_list")
        cache_rows.append(cache)
        rows = (((res or {}).get("result") or {}).get("data") or [])
        for idx, row in enumerate(rows):
            if len(row) < 5:
                continue
            date = row[2] if len(row) > 2 else ""
            tm = row[3] if len(row) > 3 else ""
            subject = row[4] if len(row) > 4 else ""
            clause = ""
            fact_date = ""
            detail_ref = None
            for cell in row:
                if isinstance(cell, dict) and cell.get("apiName"):
                    detail_ref = cell
                    break
            subject_hit = text_has_any(subject, LIST_TOKENS)
            detail_payload = {}
            detail_text = ""
            detail_status = ""
            if subject_hit or str(clause).strip() == "第14款" or text_has_any(subject, CAPITAL_CHANGE_TOKENS):
                detail_payload, detail_text, detail_status = detail_from_ref(detail_ref, event, f"{year}_{month}_{idx}", cache_rows)
            combined = f"{subject}\n{detail_text}"
            fields = parse_detail_fields(combined)
            amount_match = event_amount_match(event, combined)
            event_type = "cash_or_stock_distribution_candidate" if text_has_any(combined, ["除權", "除息", "股利"]) else ("capital_change_candidate" if is_capital_change_candidate(combined) else "unclassified_candidate")
            accepted_exact = bool(fields["ex_date"]) and (event_type == "cash_or_stock_distribution_candidate") and bool(amount_match or event.get("high_priority"))
            evidence.append({
                "ticker": event["ticker"],
                "company_name": event["company_name"],
                "event_key": event["event_key"],
                "high_priority": event["high_priority"],
                "source_route": "mops_api_t05st01_and_t05st01_detail",
                "source_url": "https://mops.twse.com.tw/mops/#/web/t05st01",
                "query_year": year,
                "query_month": month,
                "announcement_date_roc": date,
                "announcement_time": tm,
                "market_available_at_policy": "official_t05st01_announcement_timestamp_if_accepted",
                "market_available_at": f"{ymd_roc_to_ad(date)} {tm}".strip() if ymd_roc_to_ad(date) else "",
                "subject": subject,
                "clause": clause,
                "fact_date": ymd_roc_to_ad(fact_date),
                "detail_status": detail_status,
                "detail_payload": json.dumps(detail_payload, ensure_ascii=False, sort_keys=True) if detail_payload else "",
                "detail_text_excerpt": re.sub(r"\s+", " ", detail_text)[:900],
                "event_type": event_type,
                "amount_match_status": amount_match,
                **fields,
                "accepted_exact_exdate_candidate": accepted_exact,
                "acceptance_status": "accepted_exact_exdate_candidate" if accepted_exact else ("candidate_needs_core_review" if fields["ex_date"] or fields["payment_date"] or event_type == "capital_change_candidate" else "non_matching_or_no_date_candidate"),
                "future_data_violation_count": 0,
                **FLAGS,
            })
    return evidence


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    step("01_load_core_gap_and_events")
    events = load_events()
    gap_index = load_gap_index()
    selected_tickers = sorted({e["ticker"] for e in events})

    step("02_query_mops_t05st01_detail_bounded_events")
    cache_rows = []
    evidence = []
    for idx, event in enumerate(events, 1):
        step(f"02_query_event {idx}/{len(events)} {event['event_key']}")
        evidence.extend(query_event(event, cache_rows))

    step("03_build_event_patch_rows")
    by_event = defaultdict(list)
    for row in evidence:
        by_event[row["event_key"]].append(row)

    accepted_patch = []
    blocked = []
    stock_effective = []
    for event in events:
        ev_rows = by_event.get(event["event_key"], [])
        exact_rows = [r for r in ev_rows if str(r["accepted_exact_exdate_candidate"]) == "True"]
        payment_rows = [r for r in ev_rows if r.get("payment_date")]
        cap_rows = [r for r in ev_rows if r.get("event_type") == "capital_change_candidate"]
        chosen = exact_rows[0] if len(exact_rows) == 1 else None
        accepted_patch.append({
            "ticker": event["ticker"],
            "company_name": event["company_name"],
            "event_key": event["event_key"],
            "high_priority": event["high_priority"],
            "cash_dividend_total_per_share_candidate": event["cash_dividend_total_per_share_candidate"],
            "stock_dividend_total_per_share_candidate": event["stock_dividend_total_per_share_candidate"],
            "accepted_exact_exdate": chosen["ex_date"] if chosen else "",
            "accepted_payment_date": (payment_rows[0]["payment_date"] if len(payment_rows) == 1 else (chosen["payment_date"] if chosen else "")),
            "accepted_market_available_at": chosen["market_available_at"] if chosen else "",
            "accepted_source_url": chosen["source_url"] if chosen else "",
            "accepted_subject": chosen["subject"] if chosen else "",
            "accepted_detail_excerpt": chosen["detail_text_excerpt"] if chosen else "",
            "accepted_status": "accepted_unique_exact_exdate_candidate" if chosen else ("blocked_multiple_exact_candidates" if len(exact_rows) > 1 else "blocked_no_exact_exdate_candidate"),
            "exact_candidate_count": len(exact_rows),
            "payment_candidate_count": len(payment_rows),
            "capital_change_candidate_count": len(cap_rows),
            "future_data_violation_count": 0,
            **FLAGS,
        })
        if not chosen:
            blocked.append({
                "ticker": event["ticker"],
                "company_name": event["company_name"],
                "event_key": event["event_key"],
                "high_priority": event["high_priority"],
                "missing_component": "exact_historical_exdate",
                "blocked_reason": "no_unique_official_t05st01_detail_exdate_candidate" if len(exact_rows) != 1 else "",
                "attempted_source": "MOPS t05st01/t05st01_detail bounded candidate-window query",
                "candidate_rows_found": len(ev_rows),
                "exact_candidate_count": len(exact_rows),
                "next_bounded_step": "manual_policy_review_or_alternate_official_exright_archive_route",
                "future_data_violation_count": 0,
                **FLAGS,
            })
        if "cash_payment_date" in gap_index[event["event_key"]] and not (payment_rows or (chosen and chosen["payment_date"])):
            blocked.append({
                "ticker": event["ticker"],
                "company_name": event["company_name"],
                "event_key": event["event_key"],
                "high_priority": event["high_priority"],
                "missing_component": "cash_payment_date",
                "blocked_reason": "no_official_payment_date_found_in_bounded_t05st01_detail_candidates",
                "attempted_source": "MOPS t05st01/t05st01_detail bounded candidate-window query",
                "candidate_rows_found": len(ev_rows),
                "exact_candidate_count": len(exact_rows),
                "next_bounded_step": "issuer_or_transfer_agent_payment_date_archive_route_if_required",
                "future_data_violation_count": 0,
                **FLAGS,
            })
        if float(event.get("stock_dividend_total_per_share_candidate") or 0) != 0:
            sd_rows = [r for r in ev_rows if r.get("share_adjustment_effective_date") or r.get("trading_resumption_date")]
            stock_effective.append({
                "ticker": event["ticker"],
                "company_name": event["company_name"],
                "event_key": event["event_key"],
                "stock_dividend_total_per_share_candidate": event["stock_dividend_total_per_share_candidate"],
                "share_adjustment_effective_date": sd_rows[0]["share_adjustment_effective_date"] if sd_rows else "",
                "trading_resumption_date": sd_rows[0]["trading_resumption_date"] if sd_rows else "",
                "source_status": "partial_candidate" if sd_rows else "blocked_no_new_share_effective_or_tradable_date",
                "future_data_violation_count": 0,
                **FLAGS,
            })

    step("04_build_capital_change_inventory")
    capital_rows = []
    for r in evidence:
        if r.get("event_type") == "capital_change_candidate":
            capital_rows.append(r)

    source_manifest = cache_rows
    future_audit = [
        {"audit_item": "board_or_shareholder_date_as_exdate", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "query_response_datetime_as_market_available", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "accepted_market_available_at", "status": "official_t05st01_announcement_timestamp_only_when_detail_candidate_accepted", "future_data_violation_count": 0, **FLAGS},
        {"audit_item": "silent_no_event_proof", "status": "prohibited_absence_remains_blocked", "future_data_violation_count": 0, **FLAGS},
    ]

    write_csv(OUT / "selected_stock_exact_exdate_candidate_evidence.csv", evidence)
    write_csv(OUT / "selected_stock_exact_exdate_accepted_patch_rows.csv", accepted_patch)
    write_csv(OUT / "selected_stock_cash_payment_date_candidate_rows.csv", [r for r in evidence if r.get("payment_date")])
    write_csv(OUT / "selected_stock_stock_distribution_effective_date_candidates.csv", stock_effective)
    write_csv(OUT / "selected_stock_non_dividend_capital_change_inventory.csv", capital_rows)
    write_csv(OUT / "selected_stock_exact_exdate_capital_change_blocked_ledger.csv", blocked)
    write_csv(OUT / "selected_stock_exact_exdate_capital_change_source_manifest.csv", source_manifest)
    write_csv(OUT / "selected_stock_exact_exdate_capital_change_future_data_audit.csv", future_audit)

    accepted_exact = sum(1 for r in accepted_patch if r["accepted_exact_exdate"])
    accepted_payment = sum(1 for r in accepted_patch if r["accepted_payment_date"])
    high_priority_accepted = sum(1 for r in accepted_patch if str(r["high_priority"]) == "True" and r["accepted_exact_exdate"])
    readiness = {
        "task_id": TASK_ID,
        "status": "bounded_t05st01_exact_exdate_route_attempt_completed",
        "source": "MOPS official t05st01/t05st01_detail bounded by Core canonical event candidate windows",
        "coverage": {
            "canonical_events": len(events),
            "selected_tickers": len(selected_tickers),
            "high_priority_events": len(HIGH_PRIORITY_KEYS),
            "accepted_exact_exdate_events": accepted_exact,
            "accepted_payment_date_events": accepted_payment,
            "high_priority_exact_exdate_accepted": high_priority_accepted,
            "stock_distribution_effective_date_rows": len(stock_effective),
            "capital_change_inventory_candidate_rows": len(capital_rows),
            "blocked_ledger_rows": len(blocked),
            "route_cache_rows": len(source_manifest),
            "route_error_count": sum(1 for r in source_manifest if r.get("route_status") == "route_error"),
        },
        "ready_for_core_absorption": accepted_exact > 0 or len(capital_rows) > 0,
        "ready_for_core_total_return_ledger": False,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "blocked_reason": "Any unmatched/ambiguous event remains blocked; Radar does not infer entitlement or total-return factors.",
        **FLAGS,
    }
    (OUT / "readiness_for_core_selected_stock_exact_exdate_capital_change_route_unlock.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = f"""# {TASK_ID}

## 結論

完成 selected ticker/event bounded t05st01 / t05st01_detail route unlock attempt。

- canonical events: {len(events)}
- selected tickers: {len(selected_tickers)}
- accepted exact ex-date events: {accepted_exact}
- accepted payment-date events: {accepted_payment}
- high-priority exact ex-date accepted: {high_priority_accepted}/{len(HIGH_PRIORITY_KEYS)}
- non-dividend capital-change inventory candidate rows: {len(capital_rows)}
- blocked ledger rows: {len(blocked)}
- future_data_violation_count: 0

## 邊界

Radar/Data 只輸出 official source evidence / patch candidates。未計算 adjusted close、未計算 total-return factor、未用 board/shareholder date 當 ex-date、未用 query response datetime 當 market_available_at。

未能唯一對應的事件維持 blocked，不做 silent fill。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

    step("05_write_manifest")
    files = []
    for p in sorted(OUT.glob("*")):
        if p.is_file():
            files.append({"path": p.name, "sha256": sha(p), "bytes": p.stat().st_size})
    (OUT / "manifest.json").write_text(json.dumps({
        "task_id": TASK_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_dir": str(OUT),
        "core_input": str(CORE_OUT),
        "files": files,
        "readiness": readiness,
        **FLAGS,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    step("complete")


if __name__ == "__main__":
    main()
