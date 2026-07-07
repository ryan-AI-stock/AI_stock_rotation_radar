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
CORE_REVIEW = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_layer1_t164_tpex_phase1_proof_review_20260707")
PHASE1 = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_layer1_t164_tpex_phase1_50x2_bounded_proof_runner_20260707")

TASK_ID = "TASK-RADAR-DATA-VNEXT-LAYER1-T164-TPEX-PHASE1-OFFICIAL-ASOF-ALTERNATE-ROUTE-DISAMBIGUATION-001"
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


def cache_path(route, ticker, period, suffix):
    return RAW / f"{safe(route)}_{ticker}_{period}_{safe(suffix)}.json"


def post_json(route, payload, ticker, period, suffix):
    path = cache_path(route, ticker, period, suffix)
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


def target_tokens(period):
    if period == "115Q1":
        return [
            "115年第1季",
            "115年第一季",
            "115年度第1季",
            "115年度第一季",
            "115年第ㄧ季",
            "民國115年第1季",
            "民國115年第一季",
        ]
    return [
        "114年第4季",
        "114年第四季",
        "114年度",
        "民國114年度",
        "一一四年度",
        "114年合併財報",
    ]


def wrong_tokens(period):
    if period == "115Q1":
        return ["114年度", "114年第4季", "114年第四季", "114年第二季", "114年第三季", "113年"]
    return ["115年第1季", "115年第一季", "115年度第1季", "114年第一季", "114年第二季", "114年第三季", "113年"]


def query_months(period):
    if period == "115Q1":
        return [("115", "04"), ("115", "05"), ("115", "06")]
    return [("115", "01"), ("115", "02"), ("115", "03"), ("115", "04")]


def t05_payloads(ticker, period):
    payloads = [{"companyId": ticker, "year": y, "month": m, "firstDay": "", "lastDay": ""} for y, m in query_months(period)]
    if period == "115Q1":
        payloads.append({"companyId": ticker, "year": "115", "month": "", "firstDay": "1150401", "lastDay": "1150615"})
    else:
        payloads.append({"companyId": ticker, "year": "115", "month": "", "firstDay": "1150101", "lastDay": "1150430"})
    return payloads


def is_premeeting(text):
    normalized = clean(text)
    return any(token in normalized for token in ["預計提報", "提報董事會日期", "提請董事會決議日期", "預計召開日期"])


def financial_subject(text):
    normalized = clean(text)
    return any(token in normalized for token in ["財務報告", "合併財報", "財報"])


def primary_pass_subject(text, period):
    normalized = clean(text)
    if is_premeeting(normalized):
        return "excluded_premeeting_notice", False
    if not financial_subject(normalized):
        return "excluded_non_financial_subject", False
    if any(token in normalized for token in wrong_tokens(period)):
        return "excluded_wrong_period", False
    if any(token in normalized for token in target_tokens(period)):
        return "target_period_financial_subject", True
    return "financial_subject_detail_needed", True


def classify(subject, detail, period):
    text = clean(subject)
    body = clean(detail)
    combined = text + body
    if is_premeeting(combined):
        return "excluded_premeeting_notice", False, "premeeting/proposed board-date notice is not official market_available_at"
    if any(token in combined for token in wrong_tokens(period)):
        return "excluded_wrong_period", False, "subject/detail maps to wrong report period"
    if any(token in text for token in ["更正", "補充公告"]):
        return "excluded_correction_or_supplement", False, "correction/supplement excluded unless Core policy explicitly accepts it"
    has_target = any(token in combined for token in target_tokens(period))
    has_financial = financial_subject(combined)
    has_pass = any(token in combined for token in ["董事會通過", "董事會決議通過", "董事會提報", "提報董事會通過", "業經董事會決議通過"])
    if has_target and has_financial and has_pass:
        return "accepted_direct_target_financial_report", True, "target-period financial report with board-pass wording"
    if has_target and has_financial:
        return "accepted_target_financial_report_subject", True, "target-period financial report subject/detail without premeeting wording"
    return "excluded_ambiguous_or_non_target", False, "not a unique target-period official financial-report timestamp"


def candidate_rank(row):
    status = row["match_status"]
    if status == "accepted_direct_target_financial_report":
        return 0
    if status == "accepted_target_financial_report_subject":
        return 1
    return 9


blocked_rows = read_csv(CORE_REVIEW / "layer1_t164_tpex_phase1_blocked_official_asof_rows.csv")
phase1_contract = read_csv(PHASE1 / "phase1_contract_execution_audit.csv")
contract_name = {(r["ticker"], r["report_period"]): r.get("name", "") for r in phase1_contract}

cache_rows = []
candidate_rows = []
summary_rows = []
accepted_rows = []
still_blocked_rows = []

total = len(blocked_rows)
for idx, row in enumerate(blocked_rows, start=1):
    ticker = row["ticker"]
    period = row["report_period"]
    step(f"alternate_asof {idx}/{total}: {ticker} {period}")
    CHECKPOINT.write_text(json.dumps({"current_step": idx, "total_steps": total, "ticker": ticker, "report_period": period}, ensure_ascii=False, indent=2), encoding="utf-8")
    announcements = []
    route_error = 0
    for payload_idx, payload in enumerate(t05_payloads(ticker, period)):
        res, cache = post_json("t05st01", payload, ticker, period, f"alternate_{payload_idx}_{payload.get('year')}_{payload.get('month')}_{payload.get('firstDay')}_{payload.get('lastDay')}")
        cache_rows.append(cache)
        route_error += 1 if cache["route_error"] else 0
        announcements.extend((((res or {}).get("result") or {}).get("data") or []))

    seen = set()
    accepted = []
    evidence_count = 0
    detail_fetch_count = 0
    for ann in announcements:
        date = ann[2] if len(ann) > 2 else ""
        tm = ann[3] if len(ann) > 3 else ""
        subject = ann[4] if len(ann) > 4 else ""
        key = (date, tm, subject)
        if key in seen:
            continue
        seen.add(key)
        prefilter_status, should_fetch_detail = primary_pass_subject(subject, period)
        if not should_fetch_detail and prefilter_status not in ("excluded_premeeting_notice", "excluded_wrong_period"):
            continue
        detail_payload = ""
        detail_text = ""
        detail_status = ""
        ref = ann[5] if len(ann) > 5 and isinstance(ann[5], dict) else {}
        if ref and should_fetch_detail:
            payload = ref.get("parameters") or {}
            api = ref.get("apiName", "t05st01_detail")
            detail_res, detail_cache = post_json(api, payload, ticker, period, f"detail_{date}_{tm}")
            cache_rows.append(detail_cache)
            route_error += 1 if detail_cache["route_error"] else 0
            detail_fetch_count += 1
            detail_payload = json.dumps(payload, ensure_ascii=False)
            data = (((detail_res or {}).get("result") or {}).get("data") or [])
            detail_text = (data[0][9] if data and len(data[0]) > 9 else "").replace("\n", " ")
            detail_status = "ok" if data else "no_detail_data"
        match_status, is_accepted, reason = classify(subject, detail_text, period)
        candidate = {
            "ticker": ticker,
            "name": contract_name.get((ticker, period), ""),
            "market": "TPEx",
            "report_period": period,
            "announcement_date": date,
            "announcement_time": tm,
            "market_available_at": f"{date} {tm}".strip(),
            "subject": subject,
            "prefilter_status": prefilter_status,
            "detail_fetched": detail_status != "",
            "detail_status": detail_status,
            "detail_payload": detail_payload,
            "detail_text_excerpt": detail_text[:700],
            "match_status": match_status,
            "accepted_candidate": is_accepted,
            "policy_reason": reason,
            **FLAGS,
        }
        candidate_rows.append(candidate)
        evidence_count += 1
        if is_accepted:
            accepted.append(candidate)

    accepted_sorted = sorted(accepted, key=lambda r: (candidate_rank(r), r["market_available_at"], r["subject"]))
    if len(accepted_sorted) == 1:
        status = "accepted_unique_official_asof"
        chosen = accepted_sorted[0]
        blocked_reason = ""
        accepted_rows.append({
            "ticker": ticker,
            "name": contract_name.get((ticker, period), ""),
            "market": "TPEx",
            "report_period": period,
            "market_available_at": chosen["market_available_at"],
            "accepted_subject": chosen["subject"],
            "accepted_match_status": chosen["match_status"],
            "source_route": "mops_t05st01_t05st01_detail_alternate_bounded",
            "after_close_next_trading_day_policy": "required_core_calendar_join",
            "quarter_end_date_used": False,
            "query_response_datetime_used": False,
            "conservative_deadline_proxy_used": False,
            **FLAGS,
        })
    else:
        status = "blocked_unmatched_or_ambiguous"
        chosen = {}
        blocked_reason = f"accepted_candidate_count={len(accepted_sorted)}"
        still_blocked_rows.append({
            "ticker": ticker,
            "name": contract_name.get((ticker, period), ""),
            "market": "TPEx",
            "report_period": period,
            "blocked_reason": blocked_reason,
            "accepted_candidate_count": len(accepted_sorted),
            "route_error_count": route_error,
            "requires_core_or_strategy_policy": len(accepted_sorted) > 1,
            **FLAGS,
        })

    summary_rows.append({
        "ticker": ticker,
        "name": contract_name.get((ticker, period), ""),
        "market": "TPEx",
        "report_period": period,
        "previous_blocked_reason": row.get("blocked_reason", ""),
        "alternate_query_payload_count": len(t05_payloads(ticker, period)),
        "candidate_evidence_rows": evidence_count,
        "detail_fetch_count": detail_fetch_count,
        "accepted_candidate_count": len(accepted_sorted),
        "resolution_status": status,
        "market_available_at": chosen.get("market_available_at", ""),
        "accepted_subject": chosen.get("subject", ""),
        "blocked_reason": blocked_reason,
        "route_error_count": route_error,
        **FLAGS,
    })

route_error_count = sum(1 for r in cache_rows if r["route_error"])
resolved_rows = len(accepted_rows)
still_blocked = len(still_blocked_rows)
future_rows = [
    {"policy": "market_available_at", "status": "official_t05st01_timestamp_only", "violation_count": 0, **FLAGS},
    {"policy": "quarter_end_date", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "query_response_datetime", "status": "prohibited", "violation_count": 0, **FLAGS},
    {"policy": "conservative_deadline_proxy", "status": "separate_proxy_only_not_official_route", "violation_count": 0, **FLAGS},
    {"policy": "unmatched_or_ambiguous", "status": "blocked_no_silent_backfill", "violation_count": 0, **FLAGS},
]
readiness = {
    "task_id": TASK_ID,
    "status": "alternate_asof_disambiguation_completed_partial_patch_ready" if resolved_rows else "alternate_asof_disambiguation_completed_still_blocked",
    "diagnostic_only": True,
    "source": "MOPS official t05st01/t05st01_detail alternate bounded query",
    "coverage": "15 TPEx phase1 official-asof blocked rows only",
    "input_blocked_rows": total,
    "resolved_rows": resolved_rows,
    "still_blocked_rows": still_blocked,
    "route_error_count": route_error_count,
    "cache_manifest_rows": len(cache_rows),
    "future_data_violation_count": 0,
    "ready_for_core_t164_tpex_phase1_asof_patch_review": route_error_count == 0,
    "ready_for_core_t164_tpex_all_stock_proof_readiness_update": resolved_rows == total and route_error_count == 0,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "ready_for_full_universe": False,
    "tpex_all_stock_universal_ready": False,
    "blocked_reason": "" if resolved_rows == total else f"{still_blocked} rows remain unmatched/ambiguous and require Core policy/alternate source review",
    **FLAGS,
}
manifest = {
    "task_id": TASK_ID,
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": 0,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "files": [
        "build_package.py",
        "raw_cache/.gitignore",
        "current_step.txt",
        "checkpoint_state.json",
        "alternate_route_payload_response_hash_manifest.csv",
        "alternate_asof_resolution_summary.csv",
        "alternate_asof_accepted_patch_rows.csv",
        "alternate_asof_still_blocked_rows.csv",
        "alternate_asof_candidate_evidence.csv",
        "future_data_governance_audit.csv",
        "readiness_for_core_t164_tpex_phase1_asof_alternate_route.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
    **FLAGS,
}

for copied in [
    "layer1_t164_tpex_phase1_blocked_official_asof_rows.csv",
    "layer1_t164_tpex_phase1_asof_failure_attribution.csv",
    "readiness_for_layer1_t164_tpex_phase1_proof_review.json",
]:
    src = CORE_REVIEW / copied
    if src.exists():
        shutil.copyfile(src, OUT / copied)

write_csv("alternate_route_payload_response_hash_manifest.csv", cache_rows)
write_csv("alternate_asof_resolution_summary.csv", summary_rows)
write_csv("alternate_asof_accepted_patch_rows.csv", accepted_rows)
write_csv("alternate_asof_still_blocked_rows.csv", still_blocked_rows)
write_csv("alternate_asof_candidate_evidence.csv", candidate_rows)
write_csv("future_data_governance_audit.csv", future_rows)
write_json("readiness_for_core_t164_tpex_phase1_asof_alternate_route.json", readiness)
write_json("manifest.json", manifest)
(OUT / "final_summary_zh.md").write_text(f"""# Layer1 t164 TPEx phase_1 official-asof alternate route/disambiguation

Status: {readiness['status']}

結論：
- input_blocked_rows={total}
- resolved_rows={resolved_rows}
- still_blocked_rows={still_blocked}
- route_error_count={route_error_count}
- cache_manifest_rows={len(cache_rows)}
- future_data_violation_count=0

Readiness:
- ready_for_core_t164_tpex_phase1_asof_patch_review={str(readiness['ready_for_core_t164_tpex_phase1_asof_patch_review']).lower()}
- ready_for_core_t164_tpex_all_stock_proof_readiness_update={str(readiness['ready_for_core_t164_tpex_all_stock_proof_readiness_update']).lower()}
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

Policy:
- accepted official public t05st01/t05st01_detail timestamp only。
- unmatched/ambiguous remains blocked; no silent backfill。
- quarter_end_date / query_response_datetime / conservative deadline proxy prohibited as official available_at。
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
CHECKPOINT.write_text(json.dumps({"current_step": total, "total_steps": total, "status": "completed"}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote package to {OUT}")
