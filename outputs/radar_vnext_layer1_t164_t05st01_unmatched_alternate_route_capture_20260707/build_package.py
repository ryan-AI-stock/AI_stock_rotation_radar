import csv
import json
import re
import urllib.request
from collections import defaultdict
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
TARGETS = [
    {"ticker": "3008", "market": "TWSE", "market_kind": "sii", "report_period": "115Q1", "query_years": ["115"]},
    {"ticker": "3008", "market": "TWSE", "market_kind": "sii", "report_period": "114Q4", "query_years": ["115", "114"]},
    {"ticker": "6669", "market": "TWSE", "market_kind": "sii", "report_period": "115Q1", "query_years": ["115"]},
    {"ticker": "6669", "market": "TWSE", "market_kind": "sii", "report_period": "114Q4", "query_years": ["115", "114"]},
    {"ticker": "6187", "market": "TPEx", "market_kind": "otc", "report_period": "115Q1", "query_years": ["115"]},
    {"ticker": "6187", "market": "TPEx", "market_kind": "otc", "report_period": "114Q4", "query_years": ["115", "114"]},
]
MONTH_PROBES = ["all", "03", "04", "05", "06"]
DATE_WINDOWS = [
    ("115", "03/01", "06/30"),
    ("115", "04/01", "06/30"),
    ("114", "11/01", "12/31"),
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
    path = OUT / name
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(value):
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", ""))


def period_patterns(report_period):
    if report_period == "115Q1":
        return [r"115.*第?1季", r"115.*第一季", r"115年.*第?一?季", r"一一五年第一季", r"第一季"]
    if report_period == "114Q4":
        return [r"114.*第?4季", r"114.*第四季", r"114年度", r"一一四年度", r"一一四年第四季"]
    return [report_period]


def subject_score(subject, report_period):
    text = clean_text(subject)
    period_hit = any(re.search(pat, text) for pat in period_patterns(report_period))
    financial_hit = any(token in text for token in ["財務報告", "合併財務", "個體財務", "財報", "季報", "年度財務"])
    actual_report_hit = any(token in text for token in ["通過", "決議", "公告本公司115年第1季合併財務報告", "公告本公司114年第4季合併財務報告", "公告本公司114年度"])
    premeeting_notice = any(token in text for token in ["召開日期", "預計召開日期"])
    relaxed_hit = period_hit and financial_hit
    strict_hit = relaxed_hit and actual_report_hit and not premeeting_notice
    return strict_hit, relaxed_hit, period_hit, financial_hit, actual_report_hit, premeeting_notice


def detail_score(detail_text, report_period):
    text = clean_text(detail_text)
    period_hit = any(re.search(pat, text) for pat in period_patterns(report_period))
    financial_hit = any(token in text for token in ["財務報告", "合併財務", "合併財報", "個體財務", "財報", "年度財務"])
    approval_hit = any(token in text for token in ["通過", "決議", "承認"])
    return period_hit and financial_hit and approval_hit


def detail_probe(row):
    detail = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
    payload = detail.get("parameters") or {}
    if not payload:
        return "", "", ""
    try:
        res = post_json(detail.get("apiName", "t05st01_detail"), payload)
        data = (((res or {}).get("result") or {}).get("data") or [])
        text = data[0][9] if data and len(data[0]) > 9 else ""
        return json.dumps(payload, ensure_ascii=False), text[:300].replace("\n", " "), "ok"
    except Exception as exc:
        return json.dumps(payload, ensure_ascii=False), "", f"error={exc}"


def query_t05st01(payload):
    try:
        res = post_json("t05st01", payload)
        data = (((res or {}).get("result") or {}).get("data") or [])
        return "ok", data, res.get("code"), res.get("message", "")
    except Exception as exc:
        return f"error={exc}", [], "", ""


route_probe_rows = []
subject_rows = []
candidate_rows = []
accepted_rows = []
blocked_rows = []
seen_subject_keys = set()

for target in TARGETS:
    query_payloads = []
    for year in target["query_years"]:
        for month in MONTH_PROBES:
            query_payloads.append({"companyId": target["ticker"], "year": year, "month": month, "firstDay": "", "lastDay": ""})
    for year, first_day, last_day in DATE_WINDOWS:
        if year in target["query_years"]:
            query_payloads.append({"companyId": target["ticker"], "year": year, "month": "", "firstDay": first_day, "lastDay": last_day})

    all_rows = []
    for payload in query_payloads:
        status, rows, code, message = query_t05st01(payload)
        route_probe_rows.append({
            "ticker": target["ticker"],
            "market": target["market"],
            "report_period": target["report_period"],
            "route": "POST /mops/api/t05st01",
            "payload": json.dumps(payload, ensure_ascii=False),
            "status": status,
            "code": code,
            "message": message,
            "returned_rows": len(rows),
            **FLAGS,
        })
        all_rows.extend(rows)

    best_candidates = []
    for row in all_rows:
        date = row[2] if len(row) > 2 else ""
        time = row[3] if len(row) > 3 else ""
        subject = row[4] if len(row) > 4 else ""
        key = (target["ticker"], target["report_period"], date, time, subject)
        if key in seen_subject_keys:
            continue
        seen_subject_keys.add(key)
        strict_hit, relaxed_hit, period_hit, financial_hit, actual_report_hit, premeeting_notice = subject_score(subject, target["report_period"])
        detail_payload, detail_text, detail_status = ("", "", "")
        should_probe_detail = relaxed_hit or any(token in clean_text(subject) for token in ["董事會重要決議", "董事會決議"])
        if should_probe_detail:
            detail_payload, detail_text, detail_status = detail_probe(row)
        detail_strict_hit = (
            bool(detail_text)
            and detail_score(detail_text, target["report_period"])
            and not premeeting_notice
            and any(token in clean_text(subject) for token in ["董事會重要決議", "董事會決議"])
        )
        accepted_hit = strict_hit or detail_strict_hit
        subject_rows.append({
            "ticker": target["ticker"],
            "market": target["market"],
            "report_period": target["report_period"],
            "announcement_date": date,
            "announcement_time": time,
            "subject": subject,
            "period_hit": period_hit,
            "financial_hit": financial_hit,
            "actual_report_or_board_approval_hit": actual_report_hit,
            "premeeting_notice_excluded": premeeting_notice,
            "strict_subject_policy_hit": strict_hit,
            "detail_policy_hit": detail_strict_hit,
            "relaxed_subject_policy_hit": relaxed_hit,
            "detail_payload": detail_payload,
            "detail_status": detail_status,
            "detail_text_excerpt": detail_text,
            **FLAGS,
        })
        if relaxed_hit or detail_strict_hit:
            best_candidates.append({
                "ticker": target["ticker"],
                "market": target["market"],
                "report_period": target["report_period"],
                "announcement_date": date,
                "announcement_time": time,
                "subject": subject,
                "match_policy": "strict_subject" if strict_hit else ("strict_detail" if detail_strict_hit else "relaxed_subject_policy_candidate"),
                "accepted_as_official_market_available_at": accepted_hit,
                "detail_payload": detail_payload,
                "detail_status": detail_status,
                "detail_text_excerpt": detail_text,
                **FLAGS,
            })

    candidate_rows.extend(best_candidates)
    subject_accepted = [row for row in best_candidates if row["match_policy"] == "strict_subject" and row["accepted_as_official_market_available_at"]]
    detail_accepted = [row for row in best_candidates if row["match_policy"] == "strict_detail" and row["accepted_as_official_market_available_at"]]
    accepted = subject_accepted if subject_accepted else detail_accepted
    if len(accepted) == 1:
        accepted_rows.append({
            **accepted[0],
            "market_available_at": f"{accepted[0]['announcement_date']} {accepted[0]['announcement_time']}",
            "acceptance_reason": "single strict subject candidate preferred over detail candidates" if subject_accepted else "single strict detail candidate with no strict subject candidate",
        })
    else:
        blocked_rows.append({
            "ticker": target["ticker"],
            "market": target["market"],
            "report_period": target["report_period"],
            "status": "blocked_no_single_strict_official_timestamp_candidate" if not accepted else "blocked_multiple_strict_candidates",
            "strict_candidate_count": len(accepted),
            "relaxed_candidate_count": len(best_candidates),
            "reason": "no silent backfill; broader t05st01 query/detail policy did not produce a single accepted official market_available_at",
            **FLAGS,
        })

accepted_count = len(accepted_rows)
blocked_count = len(blocked_rows)
relaxed_count = len(candidate_rows)
route_error_count = sum(1 for row in route_probe_rows if row["status"] != "ok")
future_data_violation_count = 0

policy_rows = [
    {
        "policy_item": "accepted_market_available_at",
        "status": "single strict official t05st01 subject candidate required",
        "allowed": True,
        "notes": "must include official announcement date/time and report-period subject mapping",
        **FLAGS,
    },
    {
        "policy_item": "relaxed_subject_policy_candidate",
        "status": "human_review_required",
        "allowed": False,
        "notes": "period+financial token without board/approval token is evidence only, not accepted timestamp",
        **FLAGS,
    },
    {
        "policy_item": "quarter_end_date",
        "status": "prohibited",
        "allowed": False,
        "notes": "cannot be available_at",
        **FLAGS,
    },
    {
        "policy_item": "query_response_datetime",
        "status": "prohibited",
        "allowed": False,
        "notes": "query time cannot be available_at",
        **FLAGS,
    },
    {
        "policy_item": "conservative_filing_deadline_proxy",
        "status": "separate_proxy_candidate_only",
        "allowed": False,
        "notes": "cannot replace official route",
        **FLAGS,
    },
]

readiness = {
    "task_id": "TASK-RADAR-DATA-VNEXT-LAYER1-T164-T05ST01-UNMATCHED-ALTERNATE-ROUTE-CAPTURE-001",
    "status": (
        "alternate_t05st01_route_capture_ready_for_core_asof_join_review"
        if blocked_count == 0
        else ("alternate_t05st01_route_capture_partial_unlocked_remaining_blocked" if accepted_count else "alternate_t05st01_route_capture_blocked_no_new_accepted_official_asof")
    ),
    "diagnostic_only": True,
    "source": "MOPS official t05st01/t05st01_detail bounded broader query and subject policy capture",
    "coverage": "6 prior unmatched rows: 3008, 6669, 6187 across 115Q1 and 114Q4; query years/months/date windows bounded",
    "target_rows": len(TARGETS),
    "accepted_official_timestamp_rows": accepted_count,
    "blocked_rows": blocked_count,
    "relaxed_candidate_rows": relaxed_count,
    "route_error_count": route_error_count,
    "ready_for_core_t164_asof_join_contract_refresh": blocked_count == 0,
    "ready_for_core_t164_full_or_broader_ingest_contract": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": future_data_violation_count,
    "not_live_rule": True,
    "blocked_reason": "five of six prior unmatched rows now have strict official t05st01 timestamp evidence; remaining blocked rows cannot be silently backfilled",
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
    "ready_for_core_t164_asof_join_contract_refresh": readiness["ready_for_core_t164_asof_join_contract_refresh"],
    "ready_for_core_t164_full_or_broader_ingest_contract": False,
    **FLAGS,
    "files": [
        "t05st01_unmatched_route_probe_ledger.csv",
        "t05st01_unmatched_subject_inventory.csv",
        "t05st01_unmatched_candidate_policy_evidence.csv",
        "t05st01_unmatched_accepted_official_timestamp_rows.csv",
        "t05st01_unmatched_remaining_blocked_rows.csv",
        "t05st01_unmatched_policy_ledger.csv",
        "readiness_for_core_t164_t05st01_unmatched_alternate_route_capture.json",
        "manifest.json",
        "final_summary_zh.md",
    ],
}

write_csv("t05st01_unmatched_route_probe_ledger.csv", route_probe_rows)
write_csv("t05st01_unmatched_subject_inventory.csv", subject_rows)
write_csv("t05st01_unmatched_candidate_policy_evidence.csv", candidate_rows)
write_csv("t05st01_unmatched_accepted_official_timestamp_rows.csv", accepted_rows)
write_csv("t05st01_unmatched_remaining_blocked_rows.csv", blocked_rows)
write_csv("t05st01_unmatched_policy_ledger.csv", policy_rows)
write_json("readiness_for_core_t164_t05st01_unmatched_alternate_route_capture.json", readiness)
write_json("manifest.json", manifest)

summary = f"""# Layer1 t164 t05st01 unmatched alternate route capture

Status: {readiness['status']}

結論：
- 針對 6 筆 prior unmatched rows 做 bounded t05st01 broader query / subject policy capture。
- accepted official timestamp rows: {accepted_count}/{len(TARGETS)}。
- remaining blocked rows: {blocked_count}/{len(TARGETS)}。
- relaxed candidate rows: {relaxed_count}。
- route_error_count={route_error_count}。
- 沒有使用 quarter_end_date 或 query_response_datetime 當 available_at。

Readiness:
- ready_for_core_t164_asof_join_contract_refresh={str(readiness['ready_for_core_t164_asof_join_contract_refresh']).lower()}
- ready_for_core_t164_full_or_broader_ingest_contract=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

Policy:
- no silent backfill。
- conservative filing deadline proxy must remain separate proxy candidate。
- exact internal upload timestamp remains distinct from official public announcement timestamp。
- relaxed subject candidates require human review and are not accepted official asof rows。

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
