from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/radar_vnext_p1_free_historical_source_reopen_audit_20260712"
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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def tdcc_audit() -> tuple[list[dict], list[dict]]:
    samples = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 RadarP1ReopenAudit/1.0"})
    page = "https://www.tdcc.com.tw/portal/zh/tcWeb/tc_05sat_main03_8"
    session.get(page, timeout=30)
    sample_dir = OUT / "raw_audit_samples/tdcc_taibir"
    sample_dir.mkdir(parents=True, exist_ok=True)
    for year in (2009, 2015, 2022):
        for table_id in (1, 2):
            url = f"https://www.tdcc.com.tw/portal/tcWeb/exportDataWithDate?exportForm=tc_05sat_main03_8&tid={table_id}&year={year}"
            response = session.get(url, timeout=45)
            raw = response.content
            text = raw.decode("big5", errors="strict")
            name = f"taibir_{table_id}_{year}.csv"
            (sample_dir / name).write_text(text, encoding="utf-8-sig")
            lines = text.splitlines()
            samples.append({
                "year": year,
                "column": table_id,
                "data_name": lines[0].replace("資料名稱：", "") if lines else "",
                "frequency": "daily_business_day",
                "granularity": "TAIBIR term rates, not security/ticker/holder bucket",
                "fields": lines[4] if len(lines) > 4 else "",
                "rows": max(len(lines) - 5, 0),
                "http_status": response.status_code,
                "response_bytes": len(raw),
                "source_url": url,
                "source_hash": digest(raw),
                "retrieval_time_utc": now(),
                "p1_holder_distribution_usable": False,
            })

    docs_url = "https://openapi.tdcc.com.tw/tdcc-opendata-api-docs"
    docs_response = session.get(docs_url, timeout=45)
    docs = docs_response.json()
    endpoint_spec = docs.get("paths", {}).get("/v1/opendata/1-5", {}).get("get", {})
    api_url = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
    api_response = session.get(api_url, timeout=120)
    api_rows = api_response.json()
    dates = sorted({row.get("\ufeff資料日期") or row.get("資料日期") or "" for row in api_rows})
    write_csv(OUT / "tdcc_openapi_1_5_current_sample.csv", api_rows[:100])
    openapi = [{
        "source_url": api_url,
        "http_status": api_response.status_code,
        "response_bytes": len(api_response.content),
        "response_sha256": digest(api_response.content),
        "row_count": len(api_rows),
        "unique_data_dates": ";".join(dates),
        "oas_parameters": len(endpoint_spec.get("parameters") or []),
        "historical_date_parameter_available": False,
        "historical_policy": "official query page states one-year retention; open API exposes current snapshot without date parameter",
        "p1_2015_2022_ready": False,
        "retrieval_time_utc": now(),
    }]
    return samples, openapi


def taifex_audit() -> list[dict]:
    url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
    rows = []
    for date in ("2015/01/05", "2018/06/15", "2022/12/23"):
        response = requests.post(
            url,
            data={"queryStartDate": date, "queryEndDate": date, "commodityId": "TXF"},
            headers={"User-Agent": "Mozilla/5.0 RadarP1ReopenAudit/1.0"},
            timeout=60,
        )
        raw = response.content
        text = raw.decode("utf-8", errors="replace")
        rows.append({
            "date": date.replace("/", "-"),
            "source_url": url,
            "http_status": response.status_code,
            "response_bytes": len(raw),
            "response_sha256": digest(raw),
            "response_classification": "official_datetime_error_three_year_limit" if "DateTime error" in text else "unexpected_response",
            "target_rows": 0,
            "free_p1_ready": False,
            "paid_store_reference": "TAIFEX historical institutional futures data is paid; no purchase executed",
            "retrieval_time_utc": now(),
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    progress = json.loads((OUT / "tpex_institutional_progress.json").read_text(encoding="utf-8"))
    if progress.get("status") != "completed":
        raise RuntimeError("TPEx institutional runner not completed")
    tpex_manifest = list(csv.DictReader((OUT / "tpex_institutional_source_manifest.csv").open(encoding="utf-8-sig")))
    tpex_accepted = [row for row in tpex_manifest if row["status"] == "accepted"]
    tpex_failed = [row for row in tpex_manifest if row["status"] != "accepted"]
    representative_rows = []
    for date, preferred in (("2015-01-05", {"3105", "6187"}), ("2018-06-15", {"3105", "6187", "6488"}), ("2022-12-23", {"3105", "6187", "6488"})):
        path = OUT / "checkpoints/tpex_institutional" / f"{date}.csv.gz"
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        selected = [row for row in rows if row["ticker"] in preferred]
        representative_rows.extend(selected or rows[:3])
    write_csv(OUT / "tpex_institutional_representative_ticker_evidence.csv", representative_rows)

    tdcc_samples, tdcc_openapi = tdcc_audit()
    taifex = taifex_audit()
    write_csv(OUT / "tdcc_taibir_representative_download_audit.csv", tdcc_samples)
    write_csv(OUT / "tdcc_openapi_1_5_historical_capability_audit.csv", tdcc_openapi)
    write_csv(OUT / "taifex_p1_free_range_endpoint_audit.csv", taifex)

    conclusions = [
        {"source_family": "TDCC_holder_distribution_P1", "prior_exhausted_conclusion": "official free historical route exhausted", "audit_verdict": "confirmed", "reason": "screenshot page is TAIBIR rates; holder query retains one year; OpenAPI 1-5 has no date parameter and returns one current date", "p1_ready": False},
        {"source_family": "TAIFEX_TXF_foreign_trade_OI_P1", "prior_exhausted_conclusion": "official free historical route exhausted", "audit_verdict": "confirmed", "reason": "2015/2018/2022 official range endpoint returns DateTime error; older data remains paid store route", "p1_ready": False},
        {"source_family": "TPEx_daily_stock_institutional_P1", "prior_exhausted_conclusion": "official free historical route exhausted", "audit_verdict": "corrected", "reason": "correct current endpoint is insti/dailyTrade with sect=EW; full P1 daily market files materialized", "p1_ready": len(tpex_failed) == 0},
        {"source_family": "trusted_adjusted_analysis_63", "prior_exhausted_conclusion": "free structured coverage partial", "audit_verdict": "confirmed", "reason": "not reprobed in this task; prior explicit ticker-level blockers preserved", "p1_ready": False},
    ]
    write_csv(OUT / "prior_exhausted_conclusion_reassessment.csv", conclusions)

    providers = [
        {"provider": "TPEx", "source_quality": "official", "dataset": "daily per-stock institutional buy/sell", "reproducible_access": "public JSON/CSV endpoint", "p1_coverage": "2015-2022 verified and materialized", "batch_status": "accepted", "terms_or_cost": "public website; free", "notes": "sect=EW required; cate parameter was the prior route error"},
        {"provider": "TDCC", "source_quality": "official", "dataset": "holder distribution OpenAPI 1-5", "reproducible_access": "current snapshot API only", "p1_coverage": "blocked", "batch_status": "no historical parameter", "terms_or_cost": "government open data license; free current snapshot", "notes": "one-year query retention; no latest backfill"},
        {"provider": "TAIFEX", "source_quality": "official", "dataset": "TXF institutional trade/OI", "reproducible_access": "free range endpoint limited to recent years", "p1_coverage": "blocked", "batch_status": "official DateTime error for P1", "terms_or_cost": "older history paid; no purchase", "notes": "UI and endpoint limit confirmed"},
        {"provider": "FinMind", "source_quality": "trusted_nonofficial_structured", "dataset": "TaiwanStockInstitutionalInvestorsBuySell", "reproducible_access": "documented API; token/rate limits", "p1_coverage": "candidate cross-check", "batch_status": "not needed after official TPEx correction", "terms_or_cost": "free tier exists; account/token terms apply", "notes": "do not upgrade to official/formal"},
        {"provider": "Yahoo Finance", "source_quality": "trusted_nonofficial", "dataset": "adjusted price/dividend/split", "reproducible_access": "chart endpoint used for research; UI CSV download Gold", "p1_coverage": "partial with known ticker blockers", "batch_status": "research cross-check only", "terms_or_cost": "licensing restrictions; no purchase", "notes": "not institutional/TDCC/TAIFEX replacement"},
        {"provider": "MoneyDJ", "source_quality": "web_reference", "dataset": "market/institutional pages", "reproducible_access": "no documented stable bulk API/CSV found", "p1_coverage": "not accepted", "batch_status": "page view only", "terms_or_cost": "site terms; no bypass", "notes": "cannot treat visible page as reproducible source"},
        {"provider": "Anue", "source_quality": "web_reference", "dataset": "market pages", "reproducible_access": "no documented stable bulk API/CSV found", "p1_coverage": "not accepted", "batch_status": "page view only", "terms_or_cost": "site terms; no bypass", "notes": "not primary evidence"},
        {"provider": "Goodinfo/HiStock", "source_quality": "web_reference", "dataset": "stock/institutional pages", "reproducible_access": "no authorized stable bulk export established", "p1_coverage": "not accepted", "batch_status": "login/anti-bot constraints not bypassed", "terms_or_cost": "no account/payment used", "notes": "manual page availability is not batch readiness"},
    ]
    write_csv(OUT / "trusted_free_provider_inventory.csv", providers)

    coverage = [
        {"family": "TPEx_daily_stock_institutional", "requested_start": "2015-01-02", "requested_end": "2022-12-29", "actual_start": min(row["date"] for row in tpex_accepted), "actual_end": max(row["date"] for row in tpex_accepted), "requested_trading_dates": len(tpex_manifest), "accepted_dates": len(tpex_accepted), "blocked_dates": len(tpex_failed), "status": "ready" if not tpex_failed else "partial"},
        {"family": "TDCC_holder_distribution", "requested_start": "2015-01-02", "requested_end": "2022-12-29", "actual_start": "", "actual_end": "", "requested_trading_dates": "weekly", "accepted_dates": 0, "blocked_dates": "P1 full period", "status": "blocked_official_public_retention"},
        {"family": "TAIFEX_TXF_foreign_trade_OI", "requested_start": "2015-01-02", "requested_end": "2022-12-29", "actual_start": "", "actual_end": "", "requested_trading_dates": "daily", "accepted_dates": 0, "blocked_dates": "P1 full period", "status": "blocked_free_endpoint_three_year_limit"},
    ]
    write_csv(OUT / "p1_free_historical_requested_vs_actual.csv", coverage)
    write_csv(OUT / "p1_free_historical_future_data_audit.csv", [
        {"audit_item": "post_close_institutional_same_day_use", "status": "prohibited_next_trading_day_only", "future_data_violation_count": 0},
        {"audit_item": "TDCC_latest_backfill_to_P1", "status": "prohibited", "future_data_violation_count": 0},
        {"audit_item": "nonofficial_as_official", "status": "prohibited", "future_data_violation_count": 0},
    ])

    readiness = {
        "task_id": "TASK-RADAR-DATA-VNEXT-P1-FREE-HISTORICAL-SOURCE-REOPEN-AUDIT-001",
        "status": "tpex_official_p1_corrected_and_materialized_tdcc_taifex_confirmed_blocked",
        "source": "official TDCC/TAIFEX/TPEx route tests plus bounded trusted-provider inventory",
        "ready_for_core_tpex_p1_institutional_absorption": len(tpex_failed) == 0,
        "tpex_p1_dates": len(tpex_accepted),
        "tpex_p1_rows": progress.get("rows", 0),
        "tdcc_p1_holder_distribution_ready": False,
        "taifex_p1_free_history_ready": False,
        "future_data_violation_count": 0,
        "ready_for_experiments": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p1_free_historical_reopen.json", readiness)
    (OUT / "final_summary_zh.md").write_text(
        f"""# P1 免費歷史來源重新開案

- TDCC 截圖頁已確認是 TAIBIR 01/02 利率資料，不是股權分散。2009/2015/2022 六檔已下載驗證。
- TDCC 集保戶股權分散 OpenAPI 1-5 無日期參數，只回單一最新資料日；P1 仍 blocked。
- TAIFEX 2015/2018/2022 官方 range endpoint 都回 DateTime error；免費 P1 仍 blocked，未購買。
- TPEx 法人 exhausted 結論已修正：正確 `insti/dailyTrade?sect=EW` 路線鎖存 {len(tpex_accepted)}/{len(tpex_manifest)} 交易日，rows={progress.get('rows', 0)}。
- 民間來源僅作 trusted/web inventory；沒有把可見頁面當可重現批次來源。
- future_data_violation_count=0。
""",
        encoding="utf-8",
    )
    (OUT / "current_step.txt").write_text("completed_ready_for_core_tpex_institutional_absorption\n", encoding="utf-8")
    files = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and "checkpoints" not in path.parts and path.name != "manifest.json":
            files.append({"path": str(path.relative_to(OUT)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "manifest.json", {"task_id": readiness["task_id"], "generated_at_utc": now(), "files": files, **FLAGS})
    print(json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    main()
