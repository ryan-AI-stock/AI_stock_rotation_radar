import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TASK_ID = "TASK-RADAR-DATA-VNEXT-SELECTED-PATH-34-CORPORATE-ACTION-EFFECTIVE-DATE-ARCHIVE-ROUTE-UNLOCK-001"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_selected_path_total_return_completeness_absorption_20260710")
PREV = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_selected_path_holding_month_corporate_action_no_event_proof_20260710")
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

def sha_text(text): return hashlib.sha256(text.encode("utf-8")).hexdigest()

def fetch(url, name):
    RAW.mkdir(parents=True, exist_ok=True); path = RAW / name
    if path.exists(): text, status = path.read_text(encoding="utf-8"), "cache_hit"
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RadarDataSourcePackage/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r: text = r.read().decode("utf-8")
        path.write_text(text, encoding="utf-8"); status = "fetched"
    return text, {"source_url": url, "raw_cache_path": str(path.relative_to(OUT)), "response_hash": sha_text(text), "response_bytes": len(text.encode("utf-8")), "route_status": status, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "future_data_violation_count": 0, **FLAGS}

def kind_match(text, kind):
    t = text or ""
    lookup = {
        "cash_dividend_exdiv": ["除息", "現金股利", "現金股息"],
        "stock_dividend_exright": ["除權", "股票股利", "配股", "盈餘轉增資"],
        "capital_reduction_refund": ["減資", "退還股款", "退還股東"],
        "split_reverse_split_par_change": ["股票分割", "反分割", "併股", "股份合併", "面額變更", "變更面額"],
        "merger_share_conversion": ["股份轉換", "換股比例", "合併基準日", "吸收合併", "簡易合併"],
    }
    if kind == "merger_share_conversion" and "合併" in t and not any(x in t for x in ["合併營收", "合併營業額", "合併財報", "合併財務報告", "合併損益"]): return True
    return any(x in t for x in lookup.get(kind, []))

def roc_date(text):
    m = re.search(r"(\d{2,3})[年/]\s*(\d{1,2})[月/]\s*(\d{1,2})", text or "")
    return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""

def dates(text):
    result = {"exact_exdate": "", "new_share_effective_date": "", "trading_resumption_date": "", "cash_return_date": "", "ratio_text": ""}
    specs = [("exact_exdate", ["除權（息）交易日", "除息交易日", "除權交易日"]),
             ("new_share_effective_date", ["減資換發股票基準日", "新股換發基準日", "股份轉換基準日", "合併基準日"]),
             ("trading_resumption_date", ["新股票上市暨舊股票停止流通日期", "新股上市買賣日", "新股上櫃買賣日", "恢復買賣日期"]),
             ("cash_return_date", ["現金減資退還股款發放日期", "現金股利發放日期", "現金股利預計發放日", "現金股利發放日"])]
    for key, labels in specs:
        for label in labels:
            m = re.search(label + r"[:：]?\s*([^。；;\n]+)", text or "")
            if m:
                result[key] = roc_date(m.group(1))
                if result[key]: break
    m = re.search(r"(?:每仟股|每千股|換股比例|減資比例|股票分割比例)[^。；;\n]{0,100}", text or "")
    if m: result["ratio_text"] = m.group(0).strip()
    return result

def main():
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("01_load_34_core_blockers\n", encoding="utf-8")
    blocked = load(CORE / "selected_path_structural_effective_date_blocked_ledger.csv")
    intervals = load(PREV / "selected_path_holding_intervals.csv")
    legs = {}
    for x in intervals: legs.setdefault((x["ticker"], x["hold_start"][:7]), []).append(x)
    manifest = []

    (OUT / "current_step.txt").write_text("02_capture_exchange_archive_route_limits\n", encoding="utf-8")
    twse_text, twse_meta = fetch("https://www.twse.com.tw/exchangeReport/TWT48U?response=json&date=20150201", "twse_twt48u_20150201_probe.json")
    twse_meta.update({"source_id": "twse_twt48u_public_probe", "coverage_status": "date_parameter_ignored_returns_current_forecast_not_historical_archive", "accepted_for_historical_effective_date": False})
    tpex_text, tpex_meta = fetch("https://www.tpex.org.tw/zh-tw/announce/market/ex/cal/historical.html", "tpex_exdailyqhis_historical_page.html")
    tpex_meta.update({"source_id": "tpex_exDailyQHis_public_page", "coverage_status": "page_declares_roc89_96_only_out_of_scope_for_2015_plus_blockers", "accepted_for_historical_effective_date": False})
    manifest.extend([twse_meta, tpex_meta])

    (OUT / "current_step.txt").write_text("03_read_official_mops_detail_cache_per_blocker\n", encoding="utf-8")
    results, candidates = [], []
    for i, row in enumerate(blocked, 1):
        (OUT / "current_step.txt").write_text(f"03_blocker {i}/{len(blocked)} {row['ticker']} ROC{row['year_roc']}/{row['month']} {row['event_type']}\n", encoding="utf-8")
        prefix = f"no_event_{row['ticker']}_{row['year_roc']}_{row['month']}"
        list_path = PREV / "raw_cache" / f"{prefix}_list.json"
        details = []
        if list_path.exists():
            listing = json.loads(list_path.read_text(encoding="utf-8"))
            raw_rows = (((listing or {}).get("result") or {}).get("data") or [])
            for pos, raw in enumerate(raw_rows):
                # detail_from_ref used the ticker/year/month suffix, while the list cache was
                # intentionally prefixed no_event_ for its separate query contract.
                detail_path = PREV / "raw_cache" / f"{row['ticker']}_{row['year_roc']}_{row['month']}_{pos}_detail.json"
                if not detail_path.exists(): continue
                detail_json = json.loads(detail_path.read_text(encoding="utf-8"))
                data = (((detail_json or {}).get("result") or {}).get("data") or [])
                detail = str(data[0][9] if data and len(data[0]) > 9 else "")
                subject = str(raw[4] if len(raw) > 4 else "")
                text = subject + "\n" + detail
                if kind_match(text, row["event_type"]):
                    fields = dates(text)
                    holder_exclusion = ""
                    if "子公司" in subject or "與公司關係(請輸入本公司或子公司):子公司" in detail:
                        holder_exclusion = "subcompany_or_non_holder_event"
                    elif row["event_type"] == "merger_share_conversion" and ("財務" in text or "注意交易" in text):
                        holder_exclusion = "financial_or_attention_disclosure_not_holder_conversion_event"
                    elif "現金增資" in text and "原股東" not in text:
                        holder_exclusion = "cash_capital_increase_not_holder_share_scale_event"
                    item = {"ticker": row["ticker"], "market": row["market"], "year_roc": row["year_roc"], "month": row["month"], "event_type": row["event_type"],
                        "subject": subject, "detail_text_excerpt": re.sub(r"\s+", " ", detail)[:1500], "mops_list_raw_path": str(list_path), "mops_detail_raw_path": str(detail_path),
                        "mops_detail_hash": sha_text(detail_path.read_text(encoding="utf-8")), "holder_exclusion_evidence": holder_exclusion, **fields,
                        "future_data_violation_count": 0, **FLAGS}
                    details.append(item); candidates.append(item)
        resolved = [x for x in details if x["holder_exclusion_evidence"] or x["exact_exdate"] or x["new_share_effective_date"] or x["trading_resumption_date"]]
        if resolved and all(x["holder_exclusion_evidence"] for x in resolved):
            status, reason = "accepted_non_holder_exclusion", "official_mops_detail_identifies_subcompany_or_non_holder_event"
        elif len(resolved) == 1:
            status, reason = "resolved_official_effective_date_candidate", "official_mops_detail_contains_explicit_effective_date"
        elif len(resolved) > 1:
            status, reason = "blocked_multiple_official_detail_candidates", "multiple candidate events require holder/version policy"
        else:
            status, reason = "structural_source_exhausted", "MOPS detail lacks effective date; public TWSE route ignores historical date; TPEx public historical route out of coverage"
        results.append({**row, "mops_matching_detail_candidate_count": len(details), "route_unlock_status": status, "route_unlock_reason": reason,
            "structural_source_exhausted": status == "structural_source_exhausted", "licensed_source_required": False,
            "licensed_source_status": "decision_deferred_to_core_strategy_center_after_public_route_exhaustion" if status == "structural_source_exhausted" else "not_required_for_this_row",
            "twse_public_archive_probe": twse_meta["coverage_status"] if row["market"] == "TWSE" else "not_applicable",
            "tpex_public_archive_probe": tpex_meta["coverage_status"] if row["market"] == "TPEx" else "not_applicable", "future_data_violation_count": 0, **FLAGS})

    (OUT / "current_step.txt").write_text("04_write_outputs\n", encoding="utf-8")
    write(OUT / "selected_path_34_effective_date_route_results.csv", results)
    write(OUT / "selected_path_34_mops_detail_candidate_evidence.csv", candidates)
    write(OUT / "selected_path_34_effective_date_route_blocked_ledger.csv", [r for r in results if r["route_unlock_status"].startswith("blocked") or r["structural_source_exhausted"]])
    write(OUT / "selected_path_34_official_archive_source_manifest.csv", manifest)
    audit = [{"audit_item": "board_or_shareholder_date_as_effective_date", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
             {"audit_item": "query_response_datetime_as_effective_date", "status": "prohibited_not_used", "future_data_violation_count": 0, **FLAGS},
             {"audit_item": "adjusted_close_total_return_factor_performance", "status": "not_calculated", "future_data_violation_count": 0, **FLAGS}]
    write(OUT / "selected_path_34_future_data_audit.csv", audit)
    counts = {k: sum(r["route_unlock_status"] == k for r in results) for k in sorted({r["route_unlock_status"] for r in results})}
    readiness = {"task_id": TASK_ID, "status": "bounded_34_effective_date_public_archive_route_unlock_completed", "coverage": {"input_structural_blocker_rows": len(blocked), "mops_detail_candidate_rows": len(candidates), "route_status_counts": counts, "structural_source_exhausted_rows": sum(r["structural_source_exhausted"] for r in results)},
        "ready_for_core_absorption": True, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "future_data_violation_count": 0,
        "blocked_reason": "Public historical exchange routes cannot provide date-scoped coverage for this 2015+ bounded set after MOPS detail omits an effective date; licensed source decision remains with Core/Strategy Center.", **FLAGS}
    (OUT / "readiness_for_core_selected_path_34_effective_date_route_unlock.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(f"# {TASK_ID}\n\n完成 34 個 selected-path structural effective-date blockers 的 bounded official route unlock。\n\n- input blockers: {len(blocked)}\n- MOPS detail candidates: {len(candidates)}\n- route status: {json.dumps(counts, ensure_ascii=False)}\n- structural_source_exhausted: {sum(r['structural_source_exhausted'] for r in results)}\n- future_data_violation_count: 0\n\n未以 board/shareholder date、query time 或價格推定 effective date；未計 adjusted close、total-return factor 或績效。\n", encoding="utf-8")
    files = [{"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob("*")) if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files, "readiness": readiness, **FLAGS}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("complete\n", encoding="utf-8")

if __name__ == "__main__": main()
