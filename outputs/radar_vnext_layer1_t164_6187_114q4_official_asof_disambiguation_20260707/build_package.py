import csv
import json
import re
import urllib.request
from pathlib import Path


OUT = Path(__file__).resolve().parent
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
TARGET = {
    "ticker": "6187",
    "market": "TPEx",
    "market_kind": "otc",
    "report_period": "114Q4",
}
QUERY_PAYLOADS = [
    {"companyId": "6187", "year": "115", "month": "all", "firstDay": "", "lastDay": ""},
    {"companyId": "6187", "year": "115", "month": "02", "firstDay": "", "lastDay": ""},
    {"companyId": "6187", "year": "115", "month": "", "firstDay": "02/01", "lastDay": "02/28"},
    {"companyId": "6187", "year": "114", "month": "all", "firstDay": "", "lastDay": ""},
]


def post_json(api, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://mops.twse.com.tw/mops/api/{api}",
        data=data,
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_csv(name, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(value):
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", ""))


def detail_probe(row):
    detail = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
    payload = detail.get("parameters") or {}
    api = detail.get("apiName", "t05st01_detail")
    if not payload:
        return api, "", "", "missing_detail_payload"
    try:
        res = post_json(api, payload)
        data = (((res or {}).get("result") or {}).get("data") or [])
        text = data[0][9] if data and len(data[0]) > 9 else ""
        return api, json.dumps(payload, ensure_ascii=False), text.replace("\n", " "), "ok"
    except Exception as exc:
        return api, json.dumps(payload, ensure_ascii=False), "", f"error={exc}"


def classify_candidate(subject, detail_text):
    subject_text = clean_text(subject)
    detail = clean_text(detail_text)
    premeeting = any(token in subject_text for token in ["預計召開日期", "召開日期"])
    subject_financial = any(token in subject_text for token in ["財務報告", "合併財報", "合併財務報告"])
    subject_period_114q4 = any(token in subject_text for token in ["114年第4季", "一一四年第四季", "114年度", "一一四年度"])
    detail_114_annual = any(token in detail for token in [
        "114年度營業報告書",
        "114年度個體財務報告暨合併財務報告",
        "一一四年度",
    ])
    detail_direct_114_annual_period = "114/01/01~114/12/31" in detail
    detail_wrong_period = any(token in detail for token in ["115年第一季", "114年第二季", "114年第三季", "113年合併財報"])
    actual_approval = any(token in subject_text + detail for token in ["董事會決議通過", "董事會通過", "決議通過"])
    if premeeting:
        return "excluded_premeeting_notice", False, "董事會預計/召開日期通知，不是財報通過或公告可用時間"
    if subject_financial and detail_direct_114_annual_period and actual_approval:
        return "accepted_direct_financial_report_detail", True, "direct financial-report announcement detail maps to 114/01/01~114/12/31"
    if subject_financial and subject_period_114q4 and actual_approval:
        return "accepted_subject_strict", True, "subject explicitly maps to 114Q4/annual financial report approval"
    if detail_114_annual and actual_approval and not detail_wrong_period:
        return "accepted_detail_strict", True, "detail explicitly states board approval of 114 annual individual and consolidated financial statements"
    if detail_wrong_period:
        return "excluded_wrong_report_period", False, "detail maps to another period, not 6187 114Q4/114 annual"
    if not subject_financial and not detail_114_annual:
        return "excluded_non_financial_report_approval", False, "not a financial-report approval announcement for target period"
    return "excluded_ambiguous", False, "insufficient unique mapping to 6187 114Q4 official available timestamp"


route_rows = []
all_rows = []
seen = set()
for payload in QUERY_PAYLOADS:
    status = "ok"
    code = ""
    message = ""
    rows = []
    try:
        res = post_json("t05st01", payload)
        code = res.get("code")
        message = res.get("message", "")
        rows = (((res or {}).get("result") or {}).get("data") or [])
    except Exception as exc:
        status = f"error={exc}"
    route_rows.append({
        "ticker": TARGET["ticker"],
        "market": TARGET["market"],
        "report_period": TARGET["report_period"],
        "route": "POST /mops/api/t05st01",
        "payload": json.dumps(payload, ensure_ascii=False),
        "status": status,
        "code": code,
        "message": message,
        "returned_rows": len(rows),
        **FLAGS,
    })
    for row in rows:
        date = row[2] if len(row) > 2 else ""
        time = row[3] if len(row) > 3 else ""
        subject = row[4] if len(row) > 4 else ""
        key = (date, time, subject)
        if key not in seen:
            seen.add(key)
            all_rows.append(row)

candidate_rows = []
exclusion_rows = []
for row in all_rows:
    date = row[2] if len(row) > 2 else ""
    time = row[3] if len(row) > 3 else ""
    subject = row[4] if len(row) > 4 else ""
    subject_text = clean_text(subject)
    should_probe = any(token in subject_text for token in ["財務報告", "合併財報", "財報", "董事會重要決議", "董事會決議", "第4季", "年度"])
    detail_api = detail_payload = detail_text = detail_status = ""
    if should_probe:
        detail_api, detail_payload, detail_text, detail_status = detail_probe(row)
    reason_code, accepted, reason = classify_candidate(subject, detail_text)
    if should_probe or reason_code.startswith("accepted"):
        base = {
            "ticker": TARGET["ticker"],
            "market": TARGET["market"],
            "report_period": TARGET["report_period"],
            "announcement_date": date,
            "announcement_time": time,
            "market_available_at": f"{date} {time}".strip(),
            "source_route": "MOPS t05st01/t05st01_detail",
            "subject": subject,
            "detail_api": detail_api,
            "detail_payload": detail_payload,
            "detail_status": detail_status,
            "detail_text_excerpt": detail_text[:500],
            "match_reason": reason_code,
            "accepted_as_official_market_available_at": accepted,
            "policy_reason": reason,
            **FLAGS,
        }
        candidate_rows.append(base)
        if not accepted:
            exclusion_rows.append(base)

accepted_rows = [row for row in candidate_rows if row["accepted_as_official_market_available_at"]]
direct_accepted_rows = [row for row in accepted_rows if row["match_reason"] == "accepted_direct_financial_report_detail"]
subject_accepted_rows = [row for row in accepted_rows if row["match_reason"] == "accepted_subject_strict"]
detail_accepted_rows = [row for row in accepted_rows if row["match_reason"] == "accepted_detail_strict"]
if len(direct_accepted_rows) == 1:
    chosen_rows = direct_accepted_rows
elif len(subject_accepted_rows) == 1:
    chosen_rows = subject_accepted_rows
else:
    chosen_rows = detail_accepted_rows
ready = len(chosen_rows) == 1
accepted = chosen_rows[0] if ready else {}
for row in accepted_rows:
    if ready and row is not accepted:
        exclusion_rows.append({
            **row,
            "accepted_as_official_market_available_at": False,
            "policy_reason": "excluded lower-priority supporting announcement because a direct financial-report timestamp is available",
        })
accepted_rows = chosen_rows if ready else accepted_rows
future_data_violation_count = 0

after_close_rows = []
if ready:
    after_close_rows.append({
        "ticker": TARGET["ticker"],
        "market": TARGET["market"],
        "report_period": TARGET["report_period"],
        "market_available_at": accepted["market_available_at"],
        "announcement_time": accepted["announcement_time"],
        "after_close_next_trading_day_policy": "required_if_after_regular_session_close; Core must join exchange calendar",
        "required_core_fields": "market_available_at, market, exchange_calendar, regular_session_close_time, next_trading_day",
        "eligible_same_day": False,
        "eligible_date_rule": "next_trading_day_after_market_available_at",
        **FLAGS,
    })

future_audit_rows = [
    {"field": "quarter_end_date", "status": "prohibited", "used_as_available_at": False, "reason": "period end precedes disclosure", **FLAGS},
    {"field": "query_response_datetime", "status": "prohibited", "used_as_available_at": False, "reason": "query runtime is not official available time", **FLAGS},
    {"field": "conservative_deadline_proxy", "status": "separate_proxy_only", "used_as_available_at": False, "reason": "not official public timestamp", **FLAGS},
    {"field": "forward_return_as_rule", "status": "prohibited", "used_as_available_at": False, "reason": "not live rule", **FLAGS},
]

readiness = {
    "task_id": "TASK-RADAR-DATA-VNEXT-LAYER1-T164-6187-114Q4-OFFICIAL-ASOF-DISAMBIGUATION-001",
    "status": "accepted_unique_official_public_timestamp" if ready else "blocked_no_unique_official_public_timestamp",
    "diagnostic_only": True,
    "source": "MOPS official t05st01/t05st01_detail bounded single-row disambiguation",
    "coverage": "6187 TPEx 114Q4 only; bounded t05st01 year/month/date-window probes",
    "target_rows": 1,
    "candidate_rows": len(candidate_rows),
    "accepted_official_timestamp_rows": len(accepted_rows),
    "accepted_market_available_at": accepted.get("market_available_at", ""),
    "accepted_subject": accepted.get("subject", ""),
    "accepted_match_reason": accepted.get("match_reason", ""),
    "ready_for_core_t164_asof_patch_refresh": ready,
    "ready_for_core_t164_full_or_broader_ingest_contract": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": future_data_violation_count,
    "not_live_rule": True,
    "blocked_reason": "" if ready else "no unique defensible official public announcement timestamp",
    **FLAGS,
}

manifest = {
    "task_id": readiness["task_id"],
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": future_data_violation_count,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "ready_for_core_t164_asof_patch_refresh": readiness["ready_for_core_t164_asof_patch_refresh"],
    **FLAGS,
    "files": [
        "t05st01_6187_114q4_route_probe_ledger.csv",
        "t05st01_6187_114q4_strict_detail_candidates.csv",
        "t05st01_6187_114q4_exclusion_policy_ledger.csv",
        "t05st01_6187_114q4_accepted_official_timestamp.csv",
        "t05st01_6187_114q4_after_close_eligibility.csv",
        "t05st01_6187_114q4_future_data_audit.csv",
        "readiness_for_core_t164_6187_114q4_official_asof_disambiguation.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("t05st01_6187_114q4_route_probe_ledger.csv", route_rows)
write_csv("t05st01_6187_114q4_strict_detail_candidates.csv", candidate_rows)
write_csv("t05st01_6187_114q4_exclusion_policy_ledger.csv", exclusion_rows)
write_csv("t05st01_6187_114q4_accepted_official_timestamp.csv", accepted_rows)
write_csv("t05st01_6187_114q4_after_close_eligibility.csv", after_close_rows)
write_csv("t05st01_6187_114q4_future_data_audit.csv", future_audit_rows)
write_json("readiness_for_core_t164_6187_114q4_official_asof_disambiguation.json", readiness)
write_json("manifest.json", manifest)

summary = f"""# Layer1 t164 6187 114Q4 official-asof disambiguation

Status: {readiness['status']}

結論：
- 只針對 6187 TPEx 114Q4 做 final bounded disambiguation。
- accepted official timestamp rows: {len(accepted_rows)}。
- accepted market_available_at: {readiness['accepted_market_available_at'] or 'blocked'}。
- source: MOPS t05st01/t05st01_detail official public material-information route。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_asof_patch_refresh={str(readiness['ready_for_core_t164_asof_patch_refresh']).lower()}
- ready_for_core_t164_full_or_broader_ingest_contract=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

Policy:
- premeeting notice excluded。
- non-target-period announcements excluded。
- quarter_end_date prohibited。
- query_response_datetime prohibited。
- conservative deadline proxy separate only。
- forward_return_as_rule=false。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
"""
(OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")

print(f"wrote package to {OUT}")
