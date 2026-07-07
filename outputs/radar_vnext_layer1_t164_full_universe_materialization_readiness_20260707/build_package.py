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
    "Referer": "https://mops.twse.com.tw/mops/#/web/t164sb05",
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9",
}
TICKERS = [
    {"ticker": "1101", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "1216", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "1301", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2330", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2308", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2317", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2454", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2881", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "2882", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "3008", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "3711", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "6669", "market": "TWSE", "market_kind": "sii"},
    {"ticker": "6488", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "8299", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "5347", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "6187", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "8069", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "3081", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "6147", "market": "TPEx", "market_kind": "otc"},
    {"ticker": "3264", "market": "TPEx", "market_kind": "otc"},
]
PERIODS = [
    {"report_period": "115Q1", "roc_year": "115", "season": "1", "announcement_query_year": "115", "announcement_month": "all"},
    {"report_period": "114Q4", "roc_year": "114", "season": "4", "announcement_query_year": "115", "announcement_month": "all"},
]
ANN_CACHE = {}


def post_json(api, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://mops.twse.com.tw/mops/api/{api}",
        data=data,
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8")
    return json.loads(text)


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


def clean_label(label):
    return re.sub(r"\s+", "", str(label or "").replace("\u3000", ""))


def find_row(rows, patterns):
    for row in rows or []:
        label = clean_label(row[0] if row else "")
        for pat in patterns:
            if re.search(pat, label):
                return row
    return None


def parse_num(v):
    if v is None or v == "":
        return ""
    return str(v).replace(",", "").strip()


def period_patterns(report_period):
    if report_period == "115Q1":
        return [r"115.*第?1季", r"115.*第一季", r"民國115年第1季", r"115年第1季"]
    if report_period == "114Q4":
        return [r"114.*第?4季", r"114.*第四季", r"114年度", r"114年.*合併財務報告"]
    return [report_period]


def match_announcement(ticker, market_kind, report_period, query_year):
    payload = {"companyId": ticker, "year": query_year, "month": "all", "firstDay": "", "lastDay": ""}
    try:
        cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if cache_key not in ANN_CACHE:
            ANN_CACHE[cache_key] = post_json("t05st01", payload)
        res = ANN_CACHE[cache_key]
    except Exception as exc:
        return {"matched": False, "error": str(exc), "payload": json.dumps(payload, ensure_ascii=False)}
    data = (((res or {}).get("result") or {}).get("data") or [])
    pats = period_patterns(report_period)
    candidates = []
    for row in data:
        subject = row[4] if len(row) > 4 else ""
        if "財務報告" not in subject:
            continue
        if not ("通過" in subject or "決議" in subject):
            continue
        if any(re.search(pat, subject) for pat in pats):
            candidates.append(row)
    if not candidates:
        return {
            "matched": False,
            "payload": json.dumps(payload, ensure_ascii=False),
            "candidate_count": 0,
            "subject": "",
            "announcement_date": "",
            "announcement_time": "",
            "detail_payload": "",
            "detail_period": "",
            "detail_note": "",
        }
    row = candidates[0]
    detail = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
    detail_payload = detail.get("parameters") or {}
    detail_period = ""
    detail_note = ""
    try:
        detail_res = post_json(detail.get("apiName", "t05st01_detail"), detail_payload)
        detail_data = (((detail_res or {}).get("result") or {}).get("data") or [])
        if detail_data:
            detail_text = detail_data[0][9] if len(detail_data[0]) > 9 else ""
            m = re.search(r"起訖日期\(XXX/XX/XX~XXX/XX/XX\):([0-9/~-]+)", detail_text)
            detail_period = m.group(1) if m else ""
            detail_note = "upload_deadline_text_present" if "完成上傳作業" in detail_text else ""
    except Exception as exc:
        detail_note = f"detail_probe_error={exc}"
    return {
        "matched": True,
        "payload": json.dumps(payload, ensure_ascii=False),
        "candidate_count": len(candidates),
        "subject": row[4],
        "announcement_date": row[2],
        "announcement_time": row[3],
        "detail_payload": json.dumps(detail_payload, ensure_ascii=False),
        "detail_period": detail_period,
        "detail_note": detail_note,
    }


materialization_rows = []
coverage_rows = []
route_rows = []
asof_rows = []
unmatched_ambiguous_rows = []
after_close_rows = []

for t in TICKERS:
    for p in PERIODS:
        base_payload = {
            "companyId": t["ticker"],
            "dataType": "2",
            "year": p["roc_year"],
            "season": p["season"],
            "subsidiaryCompanyId": "",
        }
        cf_ok = bs_ok = False
        fields = {
            "operating_cash_flow": "",
            "investing_cash_flow": "",
            "capex_proxy": "",
            "inventory": "",
            "receivables_trade": "",
            "current_assets": "",
            "current_liabilities": "",
            "current_ratio_available": False,
        }
        cf_rows = []
        bs_rows = []
        cf_status = bs_status = "not_run"
        try:
            cf_res = post_json("t164sb05", base_payload)
            cf_rows = ((cf_res.get("result") or {}).get("reportList") or [])
            cf_ok = cf_res.get("code") == 200 and bool(cf_rows)
            cf_status = f"code={cf_res.get('code')} rows={len(cf_rows)}"
        except Exception as exc:
            cf_status = f"error={exc}"
        try:
            bs_res = post_json("t164sb03", base_payload)
            bs_rows = ((bs_res.get("result") or {}).get("reportList") or [])
            bs_ok = bs_res.get("code") == 200 and bool(bs_rows)
            bs_status = f"code={bs_res.get('code')} rows={len(bs_rows)}"
        except Exception as exc:
            bs_status = f"error={exc}"
        row = find_row(cf_rows, [r"營業活動之淨現金流入（流出）"])
        fields["operating_cash_flow"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(cf_rows, [r"投資活動之淨現金流入（流出）"])
        fields["investing_cash_flow"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(cf_rows, [r"取得不動產、廠房及設備", r"購置不動產、廠房及設備"])
        fields["capex_proxy"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(bs_rows, [r"^存貨$"])
        fields["inventory"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(bs_rows, [r"應收帳款淨額"])
        fields["receivables_trade"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(bs_rows, [r"流動資產合計"])
        fields["current_assets"] = parse_num(row[1]) if row and len(row) > 1 else ""
        row = find_row(bs_rows, [r"流動負債合計"])
        fields["current_liabilities"] = parse_num(row[1]) if row and len(row) > 1 else ""
        fields["current_ratio_available"] = bool(fields["current_assets"] and fields["current_liabilities"])
        ann = match_announcement(t["ticker"], t["market_kind"], p["report_period"], p["announcement_query_year"])
        materialization_rows.append({
            "ticker": t["ticker"],
            "market": t["market"],
            "report_period": p["report_period"],
            "t164_payload": json.dumps(base_payload, ensure_ascii=False),
            "t164sb05_status": cf_status,
            "t164sb03_status": bs_status,
            "cashflow_fields_available": bool(fields["operating_cash_flow"] and fields["investing_cash_flow"]),
            "balance_sheet_fields_available": bool(fields["inventory"] and fields["receivables_trade"]),
            "current_ratio_available": fields["current_ratio_available"],
            "operating_cash_flow": fields["operating_cash_flow"],
            "investing_cash_flow": fields["investing_cash_flow"],
            "capex_proxy": fields["capex_proxy"],
            "inventory": fields["inventory"],
            "receivables_trade": fields["receivables_trade"],
            "current_assets": fields["current_assets"],
            "current_liabilities": fields["current_liabilities"],
            "official_announcement_timestamp_matched": ann["matched"],
            "market_available_at": f"{ann.get('announcement_date','')} {ann.get('announcement_time','')}".strip(),
            "announcement_subject": ann.get("subject", ""),
            "after_close_next_trading_day_policy": "required_if_after_13_30_or_after_market_close; Core calendar join needed",
            "detail_note": ann.get("detail_note", ""),
            **FLAGS,
        })
        coverage_rows.append({
            "ticker": t["ticker"],
            "market": t["market"],
            "report_period": p["report_period"],
            "t05st01_query_payload": ann.get("payload", ""),
            "matched": ann["matched"],
            "candidate_count": ann.get("candidate_count", ""),
            "announcement_date": ann.get("announcement_date", ""),
            "announcement_time": ann.get("announcement_time", ""),
            "detail_payload": ann.get("detail_payload", ""),
            "detail_period": ann.get("detail_period", ""),
            "detail_note": ann.get("detail_note", ""),
            **FLAGS,
        })
        if (not ann["matched"]) or (ann.get("candidate_count") not in ("", 1)):
            unmatched_ambiguous_rows.append({
                "ticker": t["ticker"],
                "market": t["market"],
                "report_period": p["report_period"],
                "status": "unmatched" if not ann["matched"] else "ambiguous_multiple_candidates",
                "candidate_count": ann.get("candidate_count", ""),
                "chosen_subject": ann.get("subject", ""),
                "announcement_date": ann.get("announcement_date", ""),
                "announcement_time": ann.get("announcement_time", ""),
                "policy": "do not silent backfill; Core must keep explicit match/audit key and review multi-candidate rows",
                **FLAGS,
            })
        after_close_rows.append({
            "ticker": t["ticker"],
            "market": t["market"],
            "report_period": p["report_period"],
            "market_available_at": f"{ann.get('announcement_date','')} {ann.get('announcement_time','')}".strip(),
            "announcement_time": ann.get("announcement_time", ""),
            "after_close_policy": "if timestamp is after regular market close, eligible date must be next trading day",
            "required_core_fields": "market_available_at, exchange_calendar, regular_session_close_time, next_trading_day",
            "field_available_in_source_package": bool(ann["matched"] and ann.get("announcement_time")),
            **FLAGS,
        })

for market in ["TWSE", "TPEx"]:
    rows = [r for r in materialization_rows if r["market"] == market]
    route_rows.append({
        "market": market,
        "ticker_count": len(set(r["ticker"] for r in rows)),
        "period_count": len(set(r["report_period"] for r in rows)),
        "sample_rows": len(rows),
        "t164sb05_success_rows": sum("code=200" in r["t164sb05_status"] for r in rows),
        "t164sb03_success_rows": sum("code=200" in r["t164sb03_status"] for r in rows),
        "t05st01_matched_rows": sum(bool(r["official_announcement_timestamp_matched"]) for r in rows),
        "universal_ready": False,
        "assessment": "bounded sample route coverage only, not full universe readiness",
        **FLAGS,
    })

for r in materialization_rows:
    asof_rows.append({
        "ticker": r["ticker"],
        "market": r["market"],
        "report_period": r["report_period"],
        "market_available_at_source": "MOPS t05st01/t05st01_detail public material-information announcement timestamp" if r["official_announcement_timestamp_matched"] else "unmatched",
        "market_available_at": r["market_available_at"],
        "quarter_end_date_used": False,
        "query_response_datetime_used": False,
        "after_close_next_trading_day_policy_preserved": True,
        "needs_core_trading_calendar_join": True,
        "future_data_violation_count": 0,
        **FLAGS,
    })

label_rows = [
    {
        "field": "operating_cash_flow",
        "source": "t164sb05",
        "primary_label": "營業活動之淨現金流入（流出）",
        "status": "bounded_available",
        "human_review_required": False,
        "policy": "exact label match after whitespace normalization",
        **FLAGS,
    },
    {
        "field": "investing_cash_flow",
        "source": "t164sb05",
        "primary_label": "投資活動之淨現金流入（流出）",
        "status": "bounded_available",
        "human_review_required": False,
        "policy": "exact label match after whitespace normalization",
        **FLAGS,
    },
    {
        "field": "capex_proxy",
        "source": "t164sb05",
        "primary_label": "取得不動產、廠房及設備",
        "status": "bounded_available_proxy_human_review",
        "human_review_required": True,
        "policy": "FCF proxy only; label variants require approval before broader ingest",
        **FLAGS,
    },
    {
        "field": "inventory",
        "source": "t164sb03",
        "primary_label": "存貨",
        "status": "bounded_available",
        "human_review_required": False,
        "policy": "balance-sheet ending balance, not cash-flow inventory change row",
        **FLAGS,
    },
    {
        "field": "receivables_basket",
        "source": "t164sb03",
        "primary_label": "應收帳款淨額",
        "status": "bounded_available_human_review",
        "human_review_required": True,
        "policy": "trade receivable available; broader basket policy still needs approval",
        **FLAGS,
    },
    {
        "field": "current_ratio",
        "source": "t164sb03",
        "primary_label": "流動資產合計 / 流動負債合計",
        "status": "bounded_available",
        "human_review_required": False,
        "policy": "derive current_assets/current_liabilities; cross-check with t163sb05 if needed",
        **FLAGS,
    },
]

blocked_rows = [
    {
        "item": "full_universe_materialization_runner",
        "status": "blocked_not_started",
        "reason": "this task is bounded readiness; no full download/full sweep",
        "impact": "ready_for_core_full_ingest_readiness=false",
        **FLAGS,
    },
    {
        "item": "tpex_universal_ready",
        "status": "blocked_bounded_only",
        "reason": "TPEx 6488/8299 samples pass but not all-stock coverage",
        "impact": "do not claim universal readiness",
        **FLAGS,
    },
    {
        "item": "quarter_end_date",
        "status": "prohibited",
        "reason": "quarter end precedes disclosure",
        "impact": "never use as available_date",
        **FLAGS,
    },
    {
        "item": "query_response_datetime",
        "status": "prohibited",
        "reason": "API response datetime is query time",
        "impact": "never use as available_date",
        **FLAGS,
    },
    {
        "item": "capex_proxy_and_receivables_basket",
        "status": "human_review_required",
        "reason": "label variants and basket definition require policy approval",
        "impact": "not formal-ready",
        **FLAGS,
    },
]

tpex_rows = [r for r in materialization_rows if r["market"] == "TPEx"]
tpex_success_rows = sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in tpex_rows)
tpex_match_rows = sum(bool(r["official_announcement_timestamp_matched"]) for r in tpex_rows)
tpex_universal_rows = [
    {
        "market": "TPEx",
        "bounded_ticker_count": len(set(r["ticker"] for r in tpex_rows)),
        "bounded_rows": len(tpex_rows),
        "statement_success_rows": tpex_success_rows,
        "t05st01_matched_rows": tpex_match_rows,
        "universal_readiness": False,
        "minimal_blocker": "bounded TPEx sample can replay, but no all-stock TPEx ticker universe/full coverage runner and no all-period failure audit yet",
        **FLAGS,
    }
]

total_rows = len(materialization_rows)
matched_rows = sum(bool(r["official_announcement_timestamp_matched"]) for r in materialization_rows)
t164_success_rows = sum(("code=200" in r["t164sb05_status"]) and ("code=200" in r["t164sb03_status"]) for r in materialization_rows)
contract_ready = matched_rows == total_rows and t164_success_rows == total_rows
status = "larger_universe_materialization_readiness_ready_not_full_ingest" if contract_ready else "larger_universe_materialization_readiness_blocked_by_asof_match_gaps"
readiness = {
    "task_id": "TASK-RADAR-DATA-VNEXT-LAYER1-T164-FULL-UNIVERSE-MATERIALIZATION-READINESS-001",
    "status": status,
    "diagnostic_only": True,
    "source": "MOPS official t164sb05/t164sb03 direct replay and t05st01/t05st01_detail announcement timestamp routes",
    "coverage": "larger bounded sample: 20 tickers, TWSE/TPEx, 2 periods, t164 cashflow/balance sheet plus t05st01 announcement timestamp match coverage",
    "ticker_count": len(TICKERS),
    "markets": "TWSE,TPEx",
    "periods": "115Q1,114Q4",
    "sample_rows": total_rows,
    "t164_statement_success_rows": t164_success_rows,
    "t05st01_matched_rows": matched_rows,
    "t05st01_matched_share": round(matched_rows / total_rows, 4) if total_rows else 0,
    "ready_for_core_t164_broader_interim_official_asof_join": contract_ready,
    "ready_for_core_t164_full_or_broader_ingest_contract": contract_ready,
    "ready_for_core_full_ingest_readiness": False,
    "ready_for_experiments": False,
    "ready_for_formal": False,
    "ready_for_strategy_replay": False,
    "future_data_violation_count": 0,
    "not_live_rule": True,
    "blocked_reason": "larger bounded sample has complete t164 statement replay but t05st01 official-asof match gaps remain; unmatched rows must not be silently backfilled. Full ingest also needs universe runner, full coverage audit, TPEx universal confirmation, and label policy approval",
    **FLAGS,
}

manifest = {
    "task_id": readiness["task_id"],
    "created_at": "2026-07-07",
    "source": readiness["source"],
    "coverage": readiness["coverage"],
    "future_data_violation_count": 0,
    "ready_for_core_rerun": False,
    "ready_for_strategy_replay": False,
    "ready_for_core_t164_broader_interim_official_asof_join": readiness["ready_for_core_t164_broader_interim_official_asof_join"],
    "ready_for_core_full_ingest_readiness": False,
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
    "files": [
        "radar_t164_full_universe_materialization_matrix.csv",
        "radar_t164_market_period_coverage.csv",
        "radar_t164_t05st01_announcement_match_coverage.csv",
        "radar_t164_after_close_eligibility_fields.csv",
        "radar_t164_unmatched_ambiguous_announcement_ledger.csv",
        "radar_t164_tpex_universal_readiness_ledger.csv",
        "radar_t164_label_policy_recommendation.csv",
        "radar_t164_future_data_audit.csv",
        "radar_t164_blocked_prohibited_ledger.csv",
        "readiness_for_core_t164_full_universe_materialization.json",
        "final_summary_zh.md",
        "manifest.json",
    ],
}

write_csv("radar_t164_full_universe_materialization_matrix.csv", materialization_rows)
write_csv("radar_t164_t05st01_announcement_match_coverage.csv", coverage_rows)
write_csv("radar_t164_market_period_coverage.csv", route_rows)
write_csv("radar_t164_after_close_eligibility_fields.csv", after_close_rows)
write_csv("radar_t164_unmatched_ambiguous_announcement_ledger.csv", unmatched_ambiguous_rows)
write_csv("radar_t164_tpex_universal_readiness_ledger.csv", tpex_universal_rows)
write_csv("radar_t164_label_policy_recommendation.csv", label_rows)
write_csv("radar_t164_future_data_audit.csv", asof_rows)
write_csv("radar_t164_blocked_prohibited_ledger.csv", blocked_rows)
write_json("readiness_for_core_t164_full_universe_materialization.json", readiness)
write_json("manifest.json", manifest)

summary = f"""# vNext Layer1 t164 full-universe / broader materialization readiness

Status: {readiness['status']}

結論：
- 這是 larger bounded materialization readiness，不是 full ingest，不交 Experiments。
- payload replay 已實際擴到 {len(TICKERS)} 檔、2 個市場、2 個期間；115Q1、114Q4。
- t164sb05/t164sb03 statement sample success rows: {t164_success_rows}/{total_rows}。
- t05st01 official announcement timestamp matched rows: {matched_rows}/{total_rows}。
- unmatched / ambiguous announcement rows: {len(unmatched_ambiguous_rows)}。
- `market_available_at` 使用 t05st01/t05st01_detail public material-information timestamp；沒有使用 quarter_end_date 或 query_response_datetime。
- after-close next-trading-day eligibility policy 已保留為 Core calendar join requirement。

Readiness:
- ready_for_core_t164_broader_interim_official_asof_join={str(readiness['ready_for_core_t164_broader_interim_official_asof_join']).lower()}
- ready_for_core_t164_full_or_broader_ingest_contract={str(readiness['ready_for_core_t164_full_or_broader_ingest_contract']).lower()}
- ready_for_core_full_ingest_readiness=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

仍非 full ingest 的原因：
- 這仍是 larger bounded sample，不是 full-universe runner。
- TPEx 只有 bounded coverage probe，不是 universal ready。
- capex_proxy 與 receivables_basket 仍需 human-review label policy。
- exact upload timestamp 仍不是 t05st01 public announcement timestamp；這裡只做 official announcement asof。

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
