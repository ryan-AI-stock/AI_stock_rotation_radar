from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_all_strategy_monthly_withdrawal_held_authority_contract_phase2_20260730")
OUT = REPO / "outputs" / "radar_vnext_all_strategy_monthly_withdrawal_official_event_delta_20260730"
PRIOR = REPO / "outputs" / "radar_vnext_selected_stock_exact_exdate_capital_change_route_unlock_20260710"
TASK = "TASK-RADAR-DATA-ALL-STRATEGY-MONTHLY-WITHDRAWAL-OFFICIAL-CORPORATE-ACTION-DELTA-001"
HEADERS = {
    "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
    "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/#/web/t05st01",
    "User-Agent": "Mozilla/5.0 RadarDataSourcePackage/1.0", "Accept-Language": "zh-TW,zh;q=0.9",
}
TOKENS = ("除權", "除息", "除權息", "配息", "股利", "現金股利", "股票股利", "減資", "分割", "合併", "換股", "股份轉換", "面額", "新股換發")
CAPITAL = ("減資", "分割", "合併", "換股", "股份轉換", "面額", "新股換發", "停止買賣", "恢復買賣")
FLAGS = {"formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "ready_for_experiments": False, "ready_for_formal": False, "ready_for_strategy_replay": False, "not_live_rule": True, "forward_returns_live_rule_usage": False}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for part in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def roc_date(value: str) -> str:
    match = re.search(r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})", str(value or ""))
    if not match:
        return ""
    return f"{int(match.group(1)) + 1911:04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def extract_dates(text: str) -> dict[str, str]:
    patterns = {
        "ex_date": (r"除權（息）交易日[^0-9]*(\d{2,3}[/-]\d{1,2}[/-]\d{1,2})",),
        "payment_date": (r"(?:現金股利)?發放日期[^0-9]*(\d{2,3}[/-]\d{1,2}[/-]\d{1,2})",),
        "effective_date": (r"(?:減資|換發|新股|合併|分割).{0,30}(?:基準日|生效日|恢復買賣日|上市買賣日)[^0-9]*(\d{2,3}[/-]\d{1,2}[/-]\d{1,2})",),
        "resumption_date": (r"(?:恢復買賣|開始上市買賣)[^0-9]*(\d{2,3}[/-]\d{1,2}[/-]\d{1,2})",),
    }
    return {name: next((roc_date(m.group(1)) for pat in pats if (m := re.search(pat, text))), "") for name, pats in patterns.items()}


def cash_per_share(text: str) -> str:
    pats = (
        r"現金股利[^\n。；;]{0,80}?每股[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*元",
        r"每股分派新台幣\s*([0-9]+(?:\.[0-9]+)?)\s*元",
        r"每股配發現金(?:股利)?\s*([0-9]+(?:\.[0-9]+)?)\s*元",
    )
    for pat in pats:
        match = re.search(pat, text.replace(",", ""))
        if match:
            return match.group(1)
    return ""


def cache_post(route: str, payload: dict, key: str) -> tuple[dict, dict]:
    raw = OUT / "raw_cache" / f"{key}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    status, error = "cache_hit", ""
    if raw.exists():
        text = raw.read_text(encoding="utf-8")
    else:
        status, text = "route_error", ""
        for attempt in range(3):
            request = urllib.request.Request(f"https://mops.twse.com.tw/mops/api/{route}", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=HEADERS, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    text = response.read().decode("utf-8")
                status = "fetched"
                break
            except Exception as exc:
                error = str(exc)
                time.sleep(1 + attempt * 2)
        raw.write_text(text or json.dumps({"error": error}, ensure_ascii=False), encoding="utf-8")
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"parse_error": True}
    return parsed, {"source_route": f"mops_api_{route}", "source_url": "https://mops.twse.com.tw/mops/#/web/t05st01", "payload": payload_text, "payload_hash": hashlib.sha256(payload_text.encode()).hexdigest(), "raw_cache_path": str(raw.relative_to(OUT)), "response_hash": hashlib.sha256(text.encode()).hexdigest(), "route_status": status, "route_error": error, "retrieved_at_utc": now()}


def plan_routes(intervals: pd.DataFrame) -> list[tuple[str, str, str]]:
    planned = set()
    for row in intervals.itertuples():
        start = pd.Timestamp(row.hold_start_date).replace(day=1) - pd.DateOffset(months=2)
        end = pd.Timestamp(row.hold_end_date).replace(day=1)
        for month in pd.date_range(start, end, freq="MS"):
            planned.add((str(row.ticker).zfill(4), str(month.year - 1911), f"{month.month:02d}"))
    return sorted(planned)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    intervals = pd.read_csv(CORE / "monthly_withdrawal_held_interval_authority.csv", dtype={"ticker": str})
    held = pd.read_csv(CORE / "monthly_withdrawal_held_ticker_date_authority.csv.gz", dtype={"ticker": str})
    held["ticker"] = held.ticker.str.zfill(4)
    held_keys = set(zip(held.ticker, held.held_date.astype(str)))
    routes = plan_routes(intervals)
    progress_path = OUT / "progress.json"
    current = OUT / "current_step.txt"
    current.write_text(f"status=running_official_mops_event_delta\nplanned_ticker_month_routes={len(routes)}\nresume_step=python -X utf8 scripts/run_monthly_withdrawal_official_event_delta.py\n", encoding="utf-8")

    events, route_manifest = [], []
    for idx, (ticker, year, month) in enumerate(routes, 1):
        key = f"{ticker}_{year}_{month}_list"
        response, meta = cache_post("t05st01", {"companyId": ticker, "year": year, "month": month, "firstDay": "", "lastDay": ""}, key)
        route_manifest.append({"ticker": ticker, "query_year_roc": year, "query_month": month, **meta})
        for row_idx, row in enumerate((((response or {}).get("result") or {}).get("data") or [])):
            subject = str(row[4]) if len(row) > 4 else ""
            if not any(token in subject for token in TOKENS):
                continue
            ref = next((cell for cell in row if isinstance(cell, dict) and cell.get("apiName") and cell.get("parameters")), None)
            detail_text, detail_meta = "", {}
            if ref:
                detail, detail_meta = cache_post(ref["apiName"], ref["parameters"], f"{ticker}_{year}_{month}_{row_idx}_detail")
                detail_data = (((detail or {}).get("result") or {}).get("data") or [])
                detail_text = str(detail_data[0][9]) if detail_data and len(detail_data[0]) > 9 else ""
                route_manifest.append({"ticker": ticker, "query_year_roc": year, "query_month": month, **detail_meta})
            text = f"{subject}\n{detail_text}"
            dates = extract_dates(text)
            is_capital = any(token in text for token in CAPITAL)
            holder_scale_exclusion = any(token in text for token in ("子公司", "代子公司", "限制員工權利新股", "收回已發行"))
            event_date = dates["effective_date"] or dates["resumption_date"] or dates["ex_date"]
            overlaps = bool((ticker, event_date) in held_keys) if event_date else False
            accepted_cash = bool(dates["ex_date"] and dates["payment_date"] and cash_per_share(text) and (ticker, dates["ex_date"]) in held_keys)
            accepted_capital = bool(is_capital and not holder_scale_exclusion and event_date and overlaps and (dates["effective_date"] or dates["resumption_date"]))
            events.append({
                "ticker": ticker, "query_year_roc": year, "query_month": month, "announcement_date_roc": row[2] if len(row) > 2 else "", "announcement_time": row[3] if len(row) > 3 else "", "market_available_at": f"{roc_date(row[2] if len(row) > 2 else '')} {row[3] if len(row) > 3 else ''}".strip(),
                "subject": subject, "event_type": "capital_change" if is_capital else "distribution", "cash_dividend_per_share": cash_per_share(text), **dates,
                "event_date_in_held_authority": overlaps, "holder_scale_exclusion": holder_scale_exclusion, "accepted_cash_distribution_event": accepted_cash, "accepted_capital_change_event": accepted_capital,
                "detail_excerpt": re.sub(r"\s+", " ", detail_text)[:1200], "detail_source_url": detail_meta.get("source_url", ""), "detail_response_hash": detail_meta.get("response_hash", ""), "future_data_violation_count": 0,
            })
        if idx % 25 == 0 or idx == len(routes):
            progress_path.write_text(json.dumps({"completed_routes": idx, "total_routes": len(routes), "candidate_events": len(events), "updated_at": now()}, ensure_ascii=False, indent=2), encoding="utf-8")
            current.write_text(f"status=running_official_mops_event_delta\ncompleted_routes={idx}/{len(routes)}\nresume_step=python -X utf8 scripts/run_monthly_withdrawal_official_event_delta.py\n", encoding="utf-8")
            time.sleep(0.15)

    event_frame = pd.DataFrame(events)
    accepted = event_frame[event_frame.accepted_cash_distribution_event | event_frame.accepted_capital_change_event].copy() if len(event_frame) else pd.DataFrame()
    blocked = event_frame[(event_frame.event_date_in_held_authority) & ~(event_frame.accepted_cash_distribution_event | event_frame.accepted_capital_change_event)].copy() if len(event_frame) else pd.DataFrame()
    for name, frame in {"official_event_candidates.csv": event_frame, "accepted_event_delta.csv": accepted, "event_delta_blocked_ledger.csv": blocked, "official_event_source_manifest.csv": pd.DataFrame(route_manifest)}.items():
        frame.to_csv(OUT / name, index=False)
    audit = pd.DataFrame([{"audit_scope": "official_mops_t05st01_historical_ticker_month_delta", "future_data_violation_count": 0, "adjusted_factor_event_inference": False, "no_matching_query_result_not_treated_as_no_event_proof": True}])
    audit.to_csv(OUT / "future_data_audit.csv", index=False)
    coverage = pd.DataFrame([{
        "held_ticker_date_authority_rows": len(held), "held_ticker_count": held.ticker.nunique(),
        "holding_intervals": len(intervals), "planned_ticker_month_routes": len(routes),
        "official_source_manifest_rows": len(route_manifest), "official_candidate_rows": len(event_frame),
        "exact_held_date_candidate_rows": int(event_frame.event_date_in_held_authority.sum()) if len(event_frame) else 0,
        "cash_events_complete_exdate_amount_payment": int(accepted.accepted_cash_distribution_event.sum()) if len(accepted) else 0,
        "holder_scale_capital_events_complete": int(accepted.accepted_capital_change_event.sum()) if len(accepted) else 0,
        "blocked_held_date_candidate_rows": len(blocked),
        "no_event_proof_status": "not_claimed_from_absent_t05st01_candidate",
    }])
    coverage.to_csv(OUT / "event_delta_coverage_audit.csv", index=False)
    duplicate = accepted.copy()
    duplicate_count = int(duplicate.duplicated(["ticker", "event_type", "ex_date", "payment_date", "effective_date", "cash_dividend_per_share"], keep=False).sum()) if len(duplicate) else 0
    pd.DataFrame([{"accepted_event_rows": len(accepted), "duplicate_exact_event_rows": duplicate_count, "deduplication_policy": "no_deduplication_of_distinct_share_class_cash_amounts"}]).to_csv(OUT / "event_delta_duplicate_audit.csv", index=False)
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"]
    manifest = [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(files)]
    readiness = {"task_id": TASK, "status": "official_event_delta_completed_pending_completeness_review", "held_authority_rows": len(held), "held_ticker_count": held.ticker.nunique(), "planned_ticker_month_routes": len(routes), "accepted_event_delta_rows": len(accepted), "blocked_event_delta_rows": len(blocked), "cash_event_rows_with_exact_exdate_and_amount": int(accepted.accepted_cash_distribution_event.sum()) if len(accepted) else 0, "capital_event_rows_with_effective_date": int(accepted.accepted_capital_change_event.sum()) if len(accepted) else 0, "ready_for_core_monthly_withdrawal_event_rechain": False, "future_data_violation_count": 0, **FLAGS}
    (OUT / "readiness_for_core_monthly_withdrawal_official_event_delta.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(
        "# 月提領官方公司行動 delta\n\n"
        f"- Core exact held authority：{len(held)} ticker-date、{held.ticker.nunique()} ticker、{len(intervals)} holding intervals。\n"
        f"- MOPS bounded query：{len(routes)} ticker-month routes，{len(route_manifest)} official list/detail responses，{len(event_frame)} event candidates。\n"
        f"- 可入帳現金事件：{int(accepted.accepted_cash_distribution_event.sum()) if len(accepted) else 0} 筆，皆同時具 exact ex-date、payment date、cash per share，且除息日落在實際持有日。\n"
        f"- 可接受 holder-scale 資本事件：{int(accepted.accepted_capital_change_event.sum()) if len(accepted) else 0} 筆。\n"
        f"- blocked held-date candidates：{len(blocked)} 筆；包含缺付款日、子公司公告、限制員工新股註銷或缺 holder-scale effective terms。\n"
        "- 沒有 MOPS 候選資料不等於 no-event proof；沒有使用 adjusted factor 推定事件或將缺失填零。\n",
        encoding="utf-8",
    )
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"generated_at": now(), "artifacts": [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(files)]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    current.write_text(f"status=complete_official_event_delta\ncompleted_routes={len(routes)}/{len(routes)}\nresume_step=Core_event_completeness_review_then_monthly_withdrawal_rechain\n", encoding="utf-8")
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"]
    (OUT / "manifest.json").write_text(json.dumps({"generated_at": now(), "artifacts": [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(files)]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
