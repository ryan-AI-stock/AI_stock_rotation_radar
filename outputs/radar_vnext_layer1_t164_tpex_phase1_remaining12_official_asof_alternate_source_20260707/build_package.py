import csv
import hashlib
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path


OUT = Path(__file__).resolve().parent
RAW = OUT / "raw_cache"
RAW.mkdir(exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
CHECKPOINT = OUT / "checkpoint_state.json"
PATCH_REVIEW = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_layer1_t164_tpex_phase1_asof_patch_review_20260707")
PREV_RADAR = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_layer1_t164_tpex_phase1_official_asof_alternate_route_disambiguation_20260707")
PHASE1 = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_layer1_t164_tpex_phase1_50x2_bounded_proof_runner_20260707")

TASK_ID = "TASK-RADAR-DATA-VNEXT-LAYER1-T164-TPEX-PHASE1-REMAINING-12-OFFICIAL-ASOF-ALTERNATE-SOURCE-001"
FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://mops.twse.com.tw",
    "Referer": "https://mops.twse.com.tw/mops/#/web/t05st01",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def step(text):
    CURRENT_STEP.write_text(text, encoding="utf-8")


def clean(value):
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", ""))


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")


def post_json(route, payload, ticker, period, suffix):
    path = RAW / f"{safe(route)}_{ticker}_{period}_{safe(suffix)}.json"
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        status = "cache_hit"
        retry_count = 0
    else:
        req = urllib.request.Request(
            f"https://mops.twse.com.tw/mops/api/{route}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=HEADERS,
            method="POST",
        )
        status = "fetched"
        retry_count = 0
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                text = resp.read().decode("utf-8")
        except Exception as exc:
            text = json.dumps({"route_error": str(exc)}, ensure_ascii=False)
            status = "route_error"
            retry_count = 1
        path.write_text(text, encoding="utf-8")
        time.sleep(0.05)
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"parse_error": True}
    return parsed, {
        "ticker": ticker,
        "report_period": period,
        "route": route,
        "payload": payload_text,
        "payload_hash": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
        "raw_cache_path": str(path.relative_to(OUT)),
        "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "route_status": status,
        "retry_count": retry_count,
        "route_error": status == "route_error",
        "response_bytes": len(text.encode("utf-8")),
        **FLAGS,
    }


def query_payloads(ticker, period):
    if period == "115Q1":
        months = [("115", f"{m:02d}") for m in range(1, 8)]
        ranges = [
            ("1150101", "1150731"),
            ("1150301", "1150630"),
            ("1150401", "1150531"),
        ]
    else:
        months = [("114", "12")] + [("115", f"{m:02d}") for m in range(1, 8)]
        ranges = [
            ("1141201", "1150731"),
            ("1150101", "1150430"),
            ("1150201", "1150331"),
        ]
    payloads = [{"companyId": ticker, "year": y, "month": m, "firstDay": "", "lastDay": ""} for y, m in months]
    payloads.extend({"companyId": ticker, "year": "", "month": "", "firstDay": a, "lastDay": b} for a, b in ranges)
    return payloads


def target_tokens(period):
    if period == "115Q1":
        return [
            "115年第1季", "115年第一季", "115年度第1季", "115年度第一季",
            "115年第ㄧ季", "民國115年第1季", "民國115年第一季",
            "115年第1季度", "115年第一季度", "第一季合併財務報告",
            "第一季財務報告", "第1季合併財務報告", "第1季財務報告",
        ]
    return [
        "114年第4季", "114年第四季", "114年度", "民國114年度",
        "一一四年度", "114年合併財報", "114年合併財務報告",
        "年度合併財務報告", "年度財務報告", "114年度財務報告",
    ]


def wrong_tokens(period):
    if period == "115Q1":
        return ["114年度", "114年第4季", "114年第四季", "114年第二季", "114年第三季", "113年"]
    return ["115年第1季", "115年第一季", "115年度第1季", "115年第二季", "114年第一季", "114年第二季", "114年第三季", "113年"]


def financial_terms():
    return ["財務報告", "合併財報", "合併財務報告", "財報", "財務資訊", "財務報表"]


def pass_terms():
    return ["董事會通過", "董事會決議通過", "董事會提報", "提報董事會通過", "業經董事會決議通過", "業經董事會通過"]


def is_premeeting(text):
    t = clean(text)
    return any(x in t for x in ["預計提報", "提報董事會日期", "提請董事會決議日期", "預計召開日期", "董事會預計召開日期"])


def is_revision(text):
    t = clean(text)
    return any(x in t for x in ["更正", "補充公告", "重編", "重述", "修正"])


def classify(subject, detail, period):
    s = clean(subject)
    d = clean(detail)
    combined = s + d
    if is_premeeting(combined):
        return "excluded_premeeting_notice", False, "premeeting/proposed board-date notice is not official market_available_at"
    if any(x in combined for x in wrong_tokens(period)):
        return "excluded_wrong_period", False, "wrong-period token present"
    subject_financial = any(x in s for x in financial_terms())
    if not subject_financial:
        return "excluded_subject_not_financial_report", False, "subject/title is not a financial-report announcement"
    has_target = any(x in combined for x in target_tokens(period))
    has_pass = any(x in combined for x in pass_terms())
    if is_revision(combined) and has_target:
        return "version_candidate_revision_or_supplement", True, "revision/supplement financial-report candidate; version match required"
    if has_target and has_pass:
        return "accepted_original_or_primary_financial_report", True, "target financial report with board-pass wording"
    if has_target:
        return "candidate_target_financial_report_without_pass_wording", True, "target financial-report wording without explicit board-pass token"
    return "excluded_ambiguous_or_non_target", False, "financial wording not tied to target period"


def choose_candidate(candidates, row_key):
    accepted = [r for r in candidates if r["accepted_candidate"] is True or r["accepted_candidate"] == "True"]
    originals = [r for r in accepted if r["match_status"] == "accepted_original_or_primary_financial_report"]
    revisions = [r for r in accepted if r["match_status"] == "version_candidate_revision_or_supplement"]
    weak = [r for r in accepted if r["match_status"] == "candidate_target_financial_report_without_pass_wording"]
    if row_key == ("6114", "114Q4"):
        return None, "version_match_blocked", "6114 has multiple target financial-report announcements; cannot map t164 current values to a specific version"
    if len(originals) == 1 and not revisions and not weak:
        return originals[0], "accepted_unique_original_official_asof", ""
    if not originals and len(weak) == 1 and not revisions:
        return weak[0], "accepted_unique_target_financial_report_subject", ""
    if len(originals) == 1 and len(revisions) >= 1:
        return None, "version_match_blocked", "original and revision/supplement candidates exist; t164 statement version cannot be mapped"
    if len(accepted) == 0:
        return None, "blocked_no_official_target_candidate", "accepted_candidate_count=0"
    return None, "blocked_multiple_or_ambiguous_candidates", f"accepted_candidate_count={len(accepted)}"


remaining = read_csv(PREV_RADAR / "alternate_asof_still_blocked_rows.csv")
phase1_rows = read_csv(PHASE1 / "phase1_contract_execution_audit.csv")
names = {(r["ticker"], r["report_period"]): r.get("name", "") for r in phase1_rows}
phase1_materialized = read_csv(PHASE1 / "phase1_t164_tpex_materialized_field_matrix.csv")
statement_values = {(r["ticker"], r["report_period"]): r for r in phase1_materialized}

cache_rows = []
evidence_rows = []
summary_rows = []
accepted_rows = []
still_blocked_rows = []
dual_6114_rows = []
source_route_rows = []

for idx, row in enumerate(remaining, start=1):
    ticker = row["ticker"]
    period = row["report_period"]
    step(f"remaining12_higher_cost {idx}/{len(remaining)}: {ticker} {period}")
    CHECKPOINT.write_text(json.dumps({"current_step": idx, "total_steps": len(remaining), "ticker": ticker, "report_period": period}, ensure_ascii=False, indent=2), encoding="utf-8")
    announcements = []
    payloads = query_payloads(ticker, period)
    route_error = 0
    for pidx, payload in enumerate(payloads):
        res, cache = post_json("t05st01", payload, ticker, period, f"wide_{pidx}_{payload.get('year')}_{payload.get('month')}_{payload.get('firstDay')}_{payload.get('lastDay')}")
        cache_rows.append(cache)
        route_error += 1 if cache["route_error"] else 0
        announcements.extend((((res or {}).get("result") or {}).get("data") or []))
    unique = []
    seen = set()
    for ann in announcements:
        date = ann[2] if len(ann) > 2 else ""
        tm = ann[3] if len(ann) > 3 else ""
        subject = ann[4] if len(ann) > 4 else ""
        key = (date, tm, subject)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ann)

    candidates = []
    detail_fetch_count = 0
    for ann in unique:
        date = ann[2] if len(ann) > 2 else ""
        tm = ann[3] if len(ann) > 3 else ""
        subject = ann[4] if len(ann) > 4 else ""
        ref = ann[5] if len(ann) > 5 and isinstance(ann[5], dict) else {}
        detail_text = ""
        detail_status = ""
        detail_payload = ""
        should_fetch = True
        if ref and should_fetch:
            payload = ref.get("parameters") or {}
            api = ref.get("apiName", "t05st01_detail")
            res, cache = post_json(api, payload, ticker, period, f"detail_{date}_{tm}")
            cache_rows.append(cache)
            route_error += 1 if cache["route_error"] else 0
            detail_fetch_count += 1
            detail_payload = json.dumps(payload, ensure_ascii=False)
            data = (((res or {}).get("result") or {}).get("data") or [])
            detail_text = (data[0][9] if data and len(data[0]) > 9 else "").replace("\n", " ")
            detail_status = "ok" if data else "no_detail_data"
        match_status, accepted, reason = classify(subject, detail_text, period)
        evidence = {
            "ticker": ticker,
            "name": names.get((ticker, period), row.get("name", "")),
            "market": "TPEx",
            "report_period": period,
            "announcement_date": date,
            "announcement_time": tm,
            "market_available_at": f"{date} {tm}".strip(),
            "subject": subject,
            "detail_fetched": detail_status != "",
            "detail_status": detail_status,
            "detail_payload": detail_payload,
            "detail_text_excerpt": detail_text[:900],
            "match_status": match_status,
            "accepted_candidate": accepted,
            "policy_reason": reason,
            **FLAGS,
        }
        evidence_rows.append(evidence)
        if accepted:
            candidates.append(evidence)
        if ticker == "6114" and period == "114Q4" and accepted:
            stmt = statement_values.get((ticker, period), {})
            dual_6114_rows.append({
                "ticker": ticker,
                "name": names.get((ticker, period), row.get("name", "")),
                "market": "TPEx",
                "report_period": period,
                "market_available_at": evidence["market_available_at"],
                "subject": subject,
                "match_status": match_status,
                "detail_text_excerpt": detail_text[:900],
                "t164_operating_cash_flow": stmt.get("operating_cash_flow", ""),
                "t164_inventory": stmt.get("inventory", ""),
                "t164_receivables_trade": stmt.get("receivables_trade", ""),
                "version_match_status": "blocked_cannot_map_t164_values_to_this_announcement_version",
                **FLAGS,
            })

    chosen, resolution_status, blocked_reason = choose_candidate(candidates, (ticker, period))
    if chosen:
        accepted_rows.append({
            "ticker": ticker,
            "name": names.get((ticker, period), row.get("name", "")),
            "market": "TPEx",
            "report_period": period,
            "market_available_at": chosen["market_available_at"],
            "accepted_subject": chosen["subject"],
            "accepted_match_status": chosen["match_status"],
            "source_route": "mops_t05st01_t05st01_detail_remaining12_higher_cost_bounded",
            "after_close_next_trading_day_policy": "required_core_calendar_join",
            "quarter_end_date_used": False,
            "query_response_datetime_used": False,
            "conservative_deadline_proxy_used": False,
            **FLAGS,
        })
    else:
        still_blocked_rows.append({
            "ticker": ticker,
            "name": names.get((ticker, period), row.get("name", "")),
            "market": "TPEx",
            "report_period": period,
            "blocked_reason": blocked_reason,
            "resolution_status": resolution_status,
            "accepted_candidate_count": len(candidates),
            "route_error_count": route_error,
            "requires_core_or_strategy_policy": resolution_status in ("version_match_blocked", "blocked_multiple_or_ambiguous_candidates"),
            **FLAGS,
        })

    summary_rows.append({
        "ticker": ticker,
        "name": names.get((ticker, period), row.get("name", "")),
        "market": "TPEx",
        "report_period": period,
        "input_blocked_reason": row.get("blocked_reason", ""),
        "payload_count": len(payloads),
        "unique_announcement_rows": len(unique),
        "detail_fetch_count": detail_fetch_count,
        "accepted_candidate_count": len(candidates),
        "resolution_status": resolution_status,
        "market_available_at": chosen["market_available_at"] if chosen else "",
        "accepted_subject": chosen["subject"] if chosen else "",
        "blocked_reason": blocked_reason,
        "route_error_count": route_error,
        **FLAGS,
    })
    source_route_rows.append({
        "ticker": ticker,
        "report_period": period,
        "route_scope": "higher_cost_bounded_remaining12",
        "payload_count": len(payloads),
        "unique_announcement_rows": len(unique),
        "detail_fetch_count": detail_fetch_count,
        "accepted_candidate_count": len(candidates),
        "source": "MOPS official t05st01/t05st01_detail",
        "coverage": "single blocked ticker-period row",
        "future_data_violation_count": 0,
        **FLAGS,
    })

route_error_count = sum(1 for r in cache_rows if r["route_error"])
future_rows = [
    {"policy": "market_available_at", "status": "official_t05st01_timestamp_only", "violation_count": 0, **FLAGS},
    {"policy": "quarter_end_date", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "query_response_datetime", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "conservative_deadline_proxy", "status": "prohibited_as_official_available_at", "violation_count": 0, **FLAGS},
    {"policy": "6114_dual_candidate", "status": "version_match_required_no_silent_earliest_selection", "violation_count": 0, **FLAGS},
]

readiness = {
    "task_id": TASK_ID,
    "status": "remaining12_higher_cost_alternate_source_completed_partial_patch_ready" if accepted_rows else "remaining12_higher_cost_alternate_source_completed_still_blocked",
    "diagnostic_only": True,
    "source": "MOPS official t05st01/t05st01_detail higher-cost bounded query",
    "coverage": "12 remaining TPEx phase1 official-asof blocked rows only",
    "input_rows": len(remaining),
    "resolved_rows": len(accepted_rows),
    "still_blocked_rows": len(still_blocked_rows),
    "route_error_count": route_error_count,
    "cache_manifest_rows": len(cache_rows),
    "future_data_violation_count": 0,
    "ready_for_core_t164_tpex_remaining12_asof_patch_review": route_error_count == 0,
    "ready_for_core_t164_tpex_all_stock_proof_readiness_update": len(still_blocked_rows) == 0 and route_error_count == 0,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "ready_for_full_universe": False,
    "tpex_all_stock_universal_ready": False,
    "blocked_reason": "" if not still_blocked_rows else f"{len(still_blocked_rows)} rows remain blocked; 6114 version match remains blocked if present",
    **FLAGS,
}

manifest = {
    "task_id": TASK_ID,
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": 0,
    "files": [
        "build_package.py",
        "raw_cache/.gitignore",
        "current_step.txt",
        "checkpoint_state.json",
        "remaining12_higher_cost_payload_response_hash_manifest.csv",
        "remaining12_resolution_summary.csv",
        "remaining12_accepted_patch_rows.csv",
        "remaining12_still_blocked_ledger.csv",
        "remaining12_candidate_evidence.csv",
        "6114_dual_candidate_policy_evidence.csv",
        "route_source_evidence_ledger.csv",
        "future_data_audit.csv",
        "readiness_for_core_t164_tpex_remaining12_asof_source.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
    **FLAGS,
}

for src in [
    PATCH_REVIEW / "readiness_for_layer1_t164_tpex_phase1_asof_patch_review.json",
    PATCH_REVIEW / "layer1_t164_tpex_phase1_still_blocked_asof_rows.csv",
    PREV_RADAR / "alternate_asof_still_blocked_rows.csv",
]:
    if src.exists():
        shutil.copyfile(src, OUT / src.name)

write_csv("remaining12_higher_cost_payload_response_hash_manifest.csv", cache_rows)
write_csv("remaining12_resolution_summary.csv", summary_rows)
write_csv("remaining12_accepted_patch_rows.csv", accepted_rows)
write_csv("remaining12_still_blocked_ledger.csv", still_blocked_rows)
write_csv("remaining12_candidate_evidence.csv", evidence_rows)
write_csv("6114_dual_candidate_policy_evidence.csv", dual_6114_rows)
write_csv("route_source_evidence_ledger.csv", source_route_rows)
write_csv("future_data_audit.csv", future_rows)
write_json("readiness_for_core_t164_tpex_remaining12_asof_source.json", readiness)
write_json("manifest.json", manifest)
(OUT / "final_summary_zh.md").write_text(f"""# Layer1 t164 TPEx phase_1 remaining 12 official-asof alternate source

Status: {readiness['status']}

結論：
- input_rows={len(remaining)}
- resolved_rows={len(accepted_rows)}
- still_blocked_rows={len(still_blocked_rows)}
- route_error_count={route_error_count}
- cache_manifest_rows={len(cache_rows)}
- future_data_violation_count=0

Readiness:
- ready_for_core_t164_tpex_remaining12_asof_patch_review={str(readiness['ready_for_core_t164_tpex_remaining12_asof_patch_review']).lower()}
- ready_for_core_t164_tpex_all_stock_proof_readiness_update={str(readiness['ready_for_core_t164_tpex_all_stock_proof_readiness_update']).lower()}
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

6114 policy:
- market_available_at must map to the t164 statement version actually used.
- If two official financial-report announcements remain and t164 current values cannot be mapped to one version, row remains version_match_blocked.

Governance:
- quarter_end_date / query_response_datetime / conservative deadline proxy prohibited as official available_at。
- unmatched/ambiguous rows remain blocked; no silent backfill。
- current-or-carried TPEx universe remains sampling-only, not historical PIT all-stock universe。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
""", encoding="utf-8")
step("completed")
CHECKPOINT.write_text(json.dumps({"current_step": len(remaining), "total_steps": len(remaining), "status": "completed"}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote package to {OUT}")
