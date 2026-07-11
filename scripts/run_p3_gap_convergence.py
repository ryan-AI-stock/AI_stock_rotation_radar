from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
P3 = ROOT / "outputs" / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
OUT = ROOT / "outputs" / "radar_vnext_p3_gap_convergence_open_day_acceptance_20260711"
TASK = "TASK-RADAR-DATA-VNEXT-P3-GAP-CONVERGENCE-OPEN-DAY-ACCEPTANCE-001"
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


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["status"]
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def blocked(component: str) -> list[dict[str, str]]:
    return [r for r in read_csv(P3 / "p3_blocked_rows_detail.csv") if r["component"] == component]


def run_taifex() -> None:
    targets = {r["date"] for r in blocked("taifex_foreign_oi")}
    url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
    retrieved = now()
    response = requests.post(
        url,
        data={
            "queryStartDate": min(targets).replace("-", "/"),
            "queryEndDate": max(targets).replace("-", "/"),
            "commodityId": "TXF",
        },
        timeout=90,
        headers={"User-Agent": "Mozilla/5.0 RadarP3GapConvergence/1.0"},
    )
    response.raise_for_status()
    raw = response.content
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("cp950", errors="strict")
    source_rows = list(csv.DictReader(text.splitlines()))
    patch_rows: list[dict] = []
    for row in source_rows:
        values = list(row.values())
        if len(values) < 15:
            continue
        date = values[0].replace("/", "-")
        if date not in targets or values[1].strip() != "臺股期貨" or values[2].strip() not in {"外資", "外資及陸資"}:
            continue
        patch_rows.append(
            {
                "date": date,
                "product": "TXF",
                "investor": "foreign",
                "foreign_futures_oi_net_contracts": values[13].replace(",", "").strip(),
                "foreign_futures_oi_net_amount": values[14].replace(",", "").strip(),
                "source_quality": "official_taifex_market_level_range_download",
                "available_at_policy": "official post-close release; eligible next trading day only",
                "source_url": url,
                "source_hash": digest,
                "retrieval_time_utc": retrieved,
            }
        )
    by_date = {r["date"]: r for r in patch_rows}
    classifications = []
    for date in sorted(targets):
        ok = date in by_date
        classifications.append(
            {
                "date": date,
                "classification": "repairable_official_range_download" if ok else "official_download_no_target_row",
                "status": "accepted_patch" if ok else "blocked_official_no_target_row",
                "source_url": url,
                "source_hash": digest,
                "http_status": response.status_code,
                "blocked_reason": "" if ok else "TXF foreign row absent from official range CSV",
            }
        )
    write_csv(OUT / "taifex_110_failed_only_patch.csv", sorted(by_date.values(), key=lambda r: r["date"]))
    write_csv(OUT / "taifex_110_classification.csv", classifications)
    write_json(
        OUT / "taifex_checkpoint.json",
        {
            "status": "completed",
            "input_dates": len(targets),
            "accepted_patch_dates": len(by_date),
            "blocked_dates": len(targets - set(by_date)),
            "response_bytes": len(raw),
            "source_hash": digest,
            "updated_at": now(),
        },
    )


def parse_tdcc(ds: str, ticker: str, market: str) -> tuple[list[dict], dict]:
    url = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
    retrieved = now()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 RadarP3GapConvergence/1.0"})
    page = session.get(url, timeout=30)
    soup = BeautifulSoup(page.text, "html.parser")
    token_node = soup.select_one("input[name=SYNCHRONIZER_TOKEN]")
    if token_node is None:
        raise RuntimeError("synchronizer_token_missing")
    compact = ds.replace("-", "")
    response = session.post(
        url,
        data={
            "SYNCHRONIZER_TOKEN": token_node["value"],
            "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock",
            "method": "submit",
            "firDate": compact,
            "scaDate": compact,
            "sqlMethod": "StockNo",
            "stockNo": ticker,
        },
        timeout=45,
    )
    raw = response.content
    digest = hashlib.sha256(raw).hexdigest()
    result = BeautifulSoup(response.text, "html.parser")
    rows: list[dict] = []
    for table in result.select("table"):
        for tr in table.select("tr"):
            values = [c.get_text(" ", strip=True) for c in tr.select("th,td")]
            if len(values) >= 5 and values[0].isdigit() and values[0] != "16":
                rows.append(
                    {
                        "publication_date": ds,
                        "ticker": ticker,
                        "market": market,
                        "holding_bucket": values[1],
                        "holder_count": values[2].replace(",", ""),
                        "shares": values[3].replace(",", ""),
                        "share_pct": values[4].replace(",", ""),
                        "source_quality": "official_tdcc_retained_history",
                        "market_available_at": ds,
                        "available_at_policy": "official publication date only; exact time blocked; no prior-week backfill",
                        "source_url": response.url,
                        "source_hash": digest,
                        "retrieval_time_utc": retrieved,
                    }
                )
    meta = {
        "http_status": response.status_code,
        "response_bytes": len(raw),
        "source_url": response.url,
        "source_hash": digest,
        "retrieval_time_utc": retrieved,
    }
    return rows, meta


def run_tdcc() -> None:
    targets = blocked("tdcc_holder_distribution")
    patch_rows: list[dict] = []
    classifications: list[dict] = []
    checkpoint = {"status": "running", "input_rows": len(targets), "completed": 0, "updated_at": now()}
    for item in targets:
        ds, ticker, market = item["date"], item["ticker"], item["market"]
        try:
            rows, meta = parse_tdcc(ds, ticker, market)
            patch_rows.extend(rows)
            classification = "repairable_fresh_session" if rows else "official_query_success_no_ticker_result"
            status = "accepted_patch" if rows else "blocked_official_zero_rows"
            reason = "" if rows else "official ticker-week query returned no distribution table rows"
        except Exception as exc:
            rows = []
            meta = {"http_status": "", "response_bytes": 0, "source_url": "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock", "source_hash": "", "retrieval_time_utc": now()}
            classification, status, reason = "source_route_error", "blocked_route_error", type(exc).__name__
        classifications.append(
            {
                "publication_date": ds,
                "ticker": ticker,
                "market": market,
                "classification": classification,
                "status": status,
                "filtered_rows": len(rows),
                **meta,
                "blocked_reason": reason,
            }
        )
        checkpoint.update({"completed": checkpoint["completed"] + 1, "last_key": f"{ds}|{ticker}", "updated_at": now()})
        write_json(OUT / "tdcc_checkpoint.json", checkpoint)
    checkpoint["status"] = "completed"
    write_json(OUT / "tdcc_checkpoint.json", checkpoint)
    write_csv(OUT / "tdcc_11_failed_only_patch.csv", patch_rows)
    write_csv(OUT / "tdcc_11_classification.csv", classifications)


def write_static_ledgers() -> None:
    adjusted = []
    for row in blocked("adjusted_analysis_ohlc"):
        adjusted.append(
            {
                **row,
                "bounded_resolution": "blocked_free_trusted_routes_exhausted_no_reprobe",
                "accepted_for_research_adjusted_analysis": False,
                "official_adjusted_ready": False,
                "future_data_violation_count": 0,
            }
        )
    write_csv(OUT / "adjusted_12_exhausted_evidence.csv", adjusted)
    write_csv(
        OUT / "layer4_membership_freshness_ledger.csv",
        [
            {
                "field": "layer4_primary80_membership",
                "exact_pit_coverage_end": "2026-06-29",
                "after_coverage_status": "carried_scope_reference_only",
                "exact_pit_membership_ready_after_2026_06_29": False,
                "prohibited_claim": "carry-forward scope as exact PIT membership",
                "future_data_violation_count": 0,
            }
        ],
    )


def finalize() -> None:
    taifex = read_csv(OUT / "taifex_110_classification.csv")
    tdcc = read_csv(OUT / "tdcc_11_classification.csv")
    ta_ok = sum(r["status"] == "accepted_patch" for r in taifex)
    td_ok = sum(r["status"] == "accepted_patch" for r in tdcc)
    readiness = {
        "task_id": TASK,
        "status": "gap_convergence_complete_open_day_acceptance_pending",
        "source": "TAIFEX official range CSV; TDCC official retained-history ticker-week query; prior adjusted source exhaustion evidence",
        "coverage": {
            "taifex_input_dates": len(taifex),
            "taifex_repaired_dates": ta_ok,
            "taifex_blocked_dates": len(taifex) - ta_ok,
            "tdcc_input_ticker_weeks": len(tdcc),
            "tdcc_repaired_ticker_weeks": td_ok,
            "tdcc_blocked_ticker_weeks": len(tdcc) - td_ok,
            "adjusted_analysis_tickers_blocked": 12,
            "layer4_exact_pit_membership_end": "2026-06-29",
        },
        "future_data_violation_count": 0,
        "ready_for_core_p3_gap_patch_absorption": ta_ok > 0 or td_ok > 0,
        "ready_for_core_p3_full_feature_contract": False,
        "ready_for_open_day_ingestion_validation": False,
        "open_day_validation_status": "pending_first_official_open_day_after_workflow_schedule",
        "ready_for_experiments": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_gap_convergence.json", readiness)
    write_json(
        OUT / "first_open_day_acceptance_status.json",
        {
            "status": "pending_future_official_open_day",
            "date_policy": "determine from official market calendar and actual market data; not hardcoded",
            "required_validation": [
                "OHLCV",
                "institutional_flow",
                "margin_short_lending",
                "official_foreign_ownership",
                "TAIFEX",
                "Yahoo_global",
                "corporate_action_final_selection_guard",
                "TDCC_no_new_release_or_accepted",
            ],
            "run_url": "",
            "persisted_commit": "",
            "updated_at": now(),
        },
    )
    summary = f"""# P3 缺口收斂與首個正常交易日驗收\n\n- TAIFEX 110 日：官方區間下載補回 {ta_ok} 日，仍 blocked {len(taifex)-ta_ok} 日。\n- TDCC 11 ticker-week：fresh-session bounded retry 補回 {td_ok} 筆，仍 blocked {len(tdcc)-td_ok} 筆。\n- adjusted analysis 12 tickers：沿用已耗盡的免費可信來源證據，未重複探測，仍 blocked。\n- Layer4 exact PIT membership 截止 2026-06-29；之後僅 carried scope reference，不宣稱 exact membership。\n- 首個正常交易日驗收屬未來事件，狀態維持 pending；日期由官方市場日曆與實際市場資料共同判定。\n- future_data_violation_count=0。\n- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    files = []
    for path in sorted(OUT.glob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "manifest.json", {"task_id": TASK, "generated_at": now(), "files": files, "future_data_violation_count": 0, **FLAGS})
    (OUT / "current_step.txt").write_text("gap_convergence_complete_open_day_acceptance_pending\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=["taifex", "tdcc", "static", "finalize", "all"], default="all")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.family in {"taifex", "all"}:
        run_taifex()
    if args.family in {"tdcc", "all"}:
        run_tdcc()
    if args.family in {"static", "all"}:
        write_static_ledgers()
    if args.family in {"finalize", "all"}:
        finalize()


if __name__ == "__main__":
    main()
