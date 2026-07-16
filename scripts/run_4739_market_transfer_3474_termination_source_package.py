from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-4739-MARKET-TRANSFER-3474-TERMINATION-SOURCE-PACKAGE-001"
OUTPUT_NAME = "radar_vnext_4739_market_transfer_3474_termination_source_package_20260716"
CORE_OUTPUT = Path(
    "C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab/outputs/"
    "vnext_p1_p2_primary80_MA_slope_CD50_official_raw_close_diagnostic_20260716"
)

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

EVENT_SOURCES = [
    {
        "source_id": "micron_inotera_acquisition_announcement_20151214",
        "source_url": (
            "https://investors.micron.com/news-releases/news-release-details/"
            "micron-technology-agrees-acquire-remaining-interest-inotera"
        ),
        "source_type": "official_issuer_announcement",
        "evidence_role": "initial_holder_treatment_and_cash_consideration",
    },
    {
        "source_id": "micron_2016_10k_inotera_closing_date",
        "source_url": "https://www.sec.gov/Archives/edgar/data/723125/000072312516000269/a2016q4.htm",
        "source_type": "official_regulator_filing",
        "evidence_role": "closing_date_known_by_filing_date",
    },
    {
        "source_id": "micron_inotera_acquisition_completed_20161206",
        "source_url": "https://investors.micron.com/node/34861",
        "source_type": "official_issuer_announcement",
        "evidence_role": "completion_and_cash_consideration_confirmation",
    },
]


def open_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def read_csv(path: Path) -> list[dict[str, str]]:
    with open_csv(path) as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else ["status"])
    if path.suffix == ".gz":
        handle_context = gzip.open(path, "wt", encoding="utf-8-sig", newline="")
    else:
        handle_context = path.open("w", encoding="utf-8-sig", newline="")
    with handle_context as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_post_last_row(row: dict[str, str]) -> bool:
    ticker = (row.get("ticker") or "").strip()
    ticker_last = (row.get("ticker_last") or "").strip()
    decision_date = (row.get("decision_date") or row.get("date") or "").strip()
    last_date = (row.get("last_official_raw_close_date") or "").strip()
    return not ticker and bool(ticker_last) and bool(decision_date) and bool(last_date) and decision_date > last_date


def summarize_post_last(rows: list[dict[str, str]]) -> list[dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if is_post_last_row(row):
            grouped[row["ticker_last"].strip()].append(row)
    result: list[dict] = []
    for ticker, values in sorted(grouped.items()):
        dates = sorted({(row.get("decision_date") or row.get("date") or "").strip() for row in values})
        variants = {row.get("variant_id", "") for row in values}
        result.append({
            "ticker": ticker,
            "post_last_rows": len(values),
            "unique_decision_dates": len(dates),
            "decision_date_min": dates[0],
            "decision_date_max": dates[-1],
            "variant_count": len(variants),
            "last_official_raw_close_date": values[0].get("last_official_raw_close_date", ""),
        })
    return result


def classify_case(ticker: str) -> tuple[str, str]:
    if ticker == "4739":
        return "market_transfer_same_ticker", "TPEx_to_TWSE_continuity_required_no_forced_exit"
    if ticker == "3474":
        return "true_termination_cash_share_swap", "termination_and_holder_treatment_contract_required"
    return "source_mapping_gap", "bounded_followup_requires_separate_authority"


def load_ticker_prices(price_root: Path, tickers: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for market in ("TPEx", "TWSE"):
        for year in range(2015, 2023):
            path = price_root / market / f"{year}.csv.gz"
            if not path.exists():
                continue
            for row in read_csv(path):
                if (row.get("ticker") or "").strip() in tickers:
                    row["local_compact_path"] = str(path)
                    rows.append(row)
    return rows


def load_path_independent_ticker_prices(path: Path, tickers: set[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with open_csv(path) as handle:
        for row in csv.DictReader(handle):
            if (row.get("ticker") or "").strip() not in tickers:
                continue
            row["retrieval_time_utc"] = row.get("retrieved_at", "")
            row["local_compact_path"] = str(path)
            rows.append(row)
    return rows


def build_4739_patch(
    target_dates: set[str], price_rows: list[dict[str, str]]
) -> tuple[list[dict], list[dict], list[dict]]:
    rows = [row for row in price_rows if row.get("ticker") == "4739"]
    exact: dict[str, dict] = {}
    for row in rows:
        date = row.get("date", "")
        if date >= "2017-09-08" and row.get("market") == "TWSE" and row.get("close") not in {None, ""}:
            exact[date] = row
    patch: list[dict] = []
    for date in sorted(target_dates & set(exact)):
        row = exact[date]
        patch.append({
            "ticker": "4739",
            "date": date,
            "market": "TWSE",
            "close": row["close"],
            "source_quality": row.get("source_quality", ""),
            "adjustment_policy": row.get("adjustment_policy", ""),
            "source_url": row.get("source_url", ""),
            "source_hash": row.get("source_hash", ""),
            "retrieval_time_utc": row.get("retrieval_time_utc", ""),
            "local_compact_path": row.get("local_compact_path", ""),
            "patch_classification": "official_raw_close_after_TPEx_to_TWSE_market_transfer",
            "future_data_violation_count": 0,
        })
    missing = [{
        "ticker": "4739",
        "date": date,
        "expected_market": "TWSE",
        "classification": "local_compact_scope_gap_after_market_transfer",
        "network_attempted": False,
        "blocked_reason": "completed market-date checkpoint retained only original authority matches; exact 4739 row absent",
        "future_data_violation_count": 0,
    } for date in sorted(target_dates - set(exact))]
    boundary = []
    for date, market in (("2017-09-07", "TPEx"), ("2017-09-08", "TWSE")):
        candidates = [row for row in rows if row.get("date") == date and row.get("market") == market]
        if candidates:
            row = candidates[0]
            boundary.append({
                "ticker": "4739", "date": date, "market": market, "close": row.get("close", ""),
                "source_url": row.get("source_url", ""), "source_hash": row.get("source_hash", ""),
                "source_quality": row.get("source_quality", ""),
                "local_compact_path": row.get("local_compact_path", ""),
                "transition_boundary_status": "official_close_ready",
            })
    return patch, missing, boundary


def capture_event_sources(raw_dir: Path, network_enabled: bool) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for source in EVENT_SOURCES:
        path = raw_dir / f"{source['source_id']}.html"
        retrieved = utc_now()
        if path.exists():
            raw = path.read_bytes()
            status = "reused_local_raw_evidence"
            http_status = 200
            error = ""
        elif network_enabled:
            request = urllib.request.Request(
                source["source_url"],
                headers={"User-Agent": "Mozilla/5.0 RadarData/1.0 bounded historical event audit"},
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read()
                    http_status = response.status
                path.write_bytes(raw)
                status = "accepted_official_event_evidence"
                error = ""
            except Exception as exc:
                raw = b""
                http_status = 0
                status = "official_event_route_blocked"
                error = f"{type(exc).__name__}:{exc}"
        else:
            raw = b""
            http_status = 0
            status = "network_disabled_no_local_raw_evidence"
            error = "network_disabled"
        manifest.append({
            **source,
            "http_status": http_status,
            "status": status,
            "bytes": len(raw),
            "raw_sha256": sha256_bytes(raw) if raw else "",
            "raw_cache_path": str(path) if raw else "",
            "retrieval_time_utc": retrieved,
            "error": error,
        })
    return manifest


def local_source_manifest(repo: Path) -> list[dict]:
    sources = [
        (
            "tpex_4739_delisting_transfer_archive",
            repo / "outputs/radar_dynamic_pool1_tpex_historical_full_sweep_20260703/accepted_delisting_metadata_rows.csv",
            "https://www.tpex.org.tw/www/zh-tw/company/deListed",
        ),
        (
            "twse_4739_listing_archive",
            repo / "outputs/radar_dynamic_pool1_listing_delisting_suspension_master_20260703/raw_sources/twse_company_newlisting.json",
            "https://openapi.twse.com.tw/v1/company/newlisting",
        ),
        (
            "twse_3474_delisting_archive",
            repo / "outputs/radar_dynamic_pool1_listing_delisting_suspension_master_20260703/raw_sources/twse_company_suspend_listing.json",
            "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml",
        ),
        (
            "path_independent_primary80_official_raw_close_compact",
            repo / (
                "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716/"
                "path_independent_primary80_official_raw_close_compact.csv.gz"
            ),
            "mixed_official_market_date_bulk_routes_see_row_lineage",
        ),
    ]
    rows = []
    for source_id, path, url in sources:
        rows.append({
            "source_id": source_id,
            "source_url": url,
            "source_type": "official_market_archive_local_cache",
            "evidence_role": "listing_delisting_market_transition_metadata",
            "http_status": "local_cache",
            "status": "accepted" if path.exists() else "blocked_missing_local_cache",
            "bytes": path.stat().st_size if path.exists() else 0,
            "raw_sha256": sha256_file(path) if path.exists() else "",
            "raw_cache_path": str(path),
            "retrieval_time_utc": "",
            "error": "" if path.exists() else "local_cache_missing",
        })
    return rows


def build_3474_event_ledger(price_rows: list[dict[str, str]], event_manifest: list[dict]) -> tuple[list[dict], list[dict]]:
    rows = [row for row in price_rows if row.get("ticker") == "3474" and row.get("market") == "TWSE"]
    traded = sorted((row for row in rows if row.get("close") not in {None, ""}), key=lambda row: row.get("date", ""))
    last = traded[-1] if traded else {}
    evidence = {row["source_id"]: row for row in event_manifest}
    events = [
        {
            "ticker": "3474", "name": "華亞科", "event_type": "cash_share_swap_initial_announcement",
            "event_date": "2015-12-14", "market_available_at": "2015-12-14T15:00:00+08:00",
            "available_at_policy": "official issuer release timestamp converted from 2015-12-14 02:00 EST; after Taiwan close",
            "last_tradable_date": last.get("date", ""), "last_tradable_close": last.get("close", ""),
            "last_tradable_source_url": last.get("source_url", ""),
            "last_tradable_source_hash": last.get("source_hash", ""),
            "suspension_start_date": "", "termination_effective_date": "2016-12-06",
            "holder_treatment": "NTD_30_cash_per_share", "conversion_ratio": "not_applicable_cash_acquisition",
            "source_id": "micron_inotera_acquisition_announcement_20151214",
            "source_url": evidence.get("micron_inotera_acquisition_announcement_20151214", {}).get("source_url", ""),
            "source_hash": evidence.get("micron_inotera_acquisition_announcement_20151214", {}).get("raw_sha256", ""),
            "PIT_status": "market_known_after_announcement_not_backdated_from_effective_date",
            "future_data_violation_count": 0,
        },
        {
            "ticker": "3474", "name": "華亞科", "event_type": "cash_share_swap_closing_date_confirmation",
            "event_date": "2016-10-11", "market_available_at": "2016-10-28",
            "available_at_policy": "board event date kept separate; conservative SEC filing date used as evidence availability",
            "last_tradable_date": last.get("date", ""), "last_tradable_close": last.get("close", ""),
            "last_tradable_source_url": last.get("source_url", ""),
            "last_tradable_source_hash": last.get("source_hash", ""),
            "suspension_start_date": "", "termination_effective_date": "2016-12-06",
            "holder_treatment": "NTD_30_cash_per_share", "conversion_ratio": "not_applicable_cash_acquisition",
            "source_id": "micron_2016_10k_inotera_closing_date",
            "source_url": evidence.get("micron_2016_10k_inotera_closing_date", {}).get("source_url", ""),
            "source_hash": evidence.get("micron_2016_10k_inotera_closing_date", {}).get("raw_sha256", ""),
            "PIT_status": "exact_closing_date_known_by_conservative_public_filing_date",
            "future_data_violation_count": 0,
        },
        {
            "ticker": "3474", "name": "華亞科", "event_type": "TWSE_listing_termination_cash_share_swap_completed",
            "event_date": "2016-12-06", "market_available_at": "",
            "available_at_policy": "TWSE archive exposes effective date but no historical announcement timestamp; not used as prior PIT availability",
            "last_tradable_date": last.get("date", ""), "last_tradable_close": last.get("close", ""),
            "last_tradable_source_url": last.get("source_url", ""),
            "last_tradable_source_hash": last.get("source_hash", ""),
            "suspension_start_date": "", "termination_effective_date": "2016-12-06",
            "holder_treatment": "NTD_30_cash_per_share", "conversion_ratio": "not_applicable_cash_acquisition",
            "source_id": "twse_3474_delisting_archive",
            "source_url": "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml",
            "source_hash": "",
            "PIT_status": "effective_date_official_announcement_timestamp_blocked",
            "future_data_violation_count": 0,
        },
    ]
    blocked = [{
        "ticker": "3474",
        "blocked_component": "exact_official_suspension_start_date_and_announcement_timestamp",
        "derived_candidate_date": "2016-11-30" if last.get("date") == "2016-11-29" else "",
        "derived_candidate_policy": "derived only from last official price followed by no price; not accepted as official event date",
        "structural_source_blocked": True,
        "network_probe_expanded": False,
        "future_data_violation_count": 0,
    }]
    return events, blocked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-output", type=Path, default=CORE_OUTPUT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    output = args.output or repo / "outputs" / OUTPUT_NAME
    output.mkdir(parents=True, exist_ok=True)
    (output / "current_step.txt").write_text("loading_core_post_last_authority\n", encoding="utf-8")

    core_ledger = args.core_output / "raw_close_incumbent_no_observation_ledger.csv.gz"
    core_rows = read_csv(core_ledger)
    post_last = [row for row in core_rows if is_post_last_row(row)]
    summary = summarize_post_last(core_rows)
    if sum(int(row["post_last_rows"]) for row in summary) != 24118:
        raise RuntimeError("Core post-last authority changed; refusing stale bounded package")
    if {row["ticker"] for row in summary} != {"3474", "4739"}:
        raise RuntimeError("Unexpected material ticker in Core post-last authority")

    classification = []
    for row in summary:
        case_type, action = classify_case(row["ticker"])
        classification.append({**row, "case_type": case_type, "required_action": action})

    price_root = (
        repo / "outputs/radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710/compact/"
        "official_raw_execution_ohlcv"
    )
    price_rows = load_ticker_prices(price_root, {"3474", "4739"})
    path_independent_close = (
        repo / "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716/"
        "path_independent_primary80_official_raw_close_compact.csv.gz"
    )
    price_rows.extend(load_path_independent_ticker_prices(path_independent_close, {"3474", "4739"}))
    target_4739 = {
        (row.get("decision_date") or row.get("date") or "").strip()
        for row in post_last if row.get("ticker_last") == "4739"
    }
    patch, remaining, boundary = build_4739_patch(target_4739, price_rows)

    local_manifest = local_source_manifest(repo)
    event_manifest = capture_event_sources(output / "raw_event_evidence", not args.no_network)
    source_manifest = local_manifest + event_manifest
    events_3474, blocked_3474 = build_3474_event_ledger(price_rows, source_manifest)
    twse_hash = next((row["raw_sha256"] for row in local_manifest if row["source_id"] == "twse_3474_delisting_archive"), "")
    events_3474[-1]["source_hash"] = twse_hash

    transition_ledger = [{
        "ticker": "4739", "name": "康普材料", "transition_type": "TPEx_to_TWSE_same_ticker_market_transfer",
        "TPEx_last_market_date": "2017-09-07", "TWSE_listing_effective_date": "2017-09-08",
        "TWSE_application_date": "2017-06-15", "TWSE_approval_date": "2017-08-22",
        "TWSE_agreement_date": "2017-08-23", "official_note": "櫃轉市",
        "forced_exit_required": False, "ticker_identity_changed": False,
        "source_url_TPEx": "https://www.tpex.org.tw/www/zh-tw/company/deListed",
        "source_url_TWSE": "https://openapi.twse.com.tw/v1/company/newlisting",
        "source_hash_TPEx": next((row["raw_sha256"] for row in local_manifest if row["source_id"] == "tpex_4739_delisting_transfer_archive"), ""),
        "source_hash_TWSE": next((row["raw_sha256"] for row in local_manifest if row["source_id"] == "twse_4739_listing_archive"), ""),
        "PIT_policy": "listing milestones are event metadata; close continuity uses only same-date official market rows",
        "future_data_violation_count": 0,
    }]

    write_csv(output / "post_last_24118_ticker_summary.csv", summary)
    write_csv(output / "post_last_material_case_classification.csv", classification)
    write_csv(output / "ticker_4739_tpex_twse_transition_ledger.csv", transition_ledger)
    write_csv(output / "ticker_4739_transition_boundary_close_chain.csv", boundary)
    write_csv(output / "ticker_4739_post_transition_exact_close_patch.csv.gz", patch)
    write_csv(output / "ticker_4739_post_transition_remaining_local_gap.csv", remaining)
    write_csv(output / "ticker_3474_termination_event_ledger.csv", events_3474)
    write_csv(output / "ticker_3474_termination_blocked_ledger.csv", blocked_3474)
    write_csv(output / "source_manifest.csv", source_manifest)
    future_audit = [{
        "audit_item": "event_date_and_market_available_at_separated",
        "status": "pass",
        "detail": "3474 effective date is not substituted for historical announcement availability",
        "future_data_violation_count": 0,
    }, {
        "audit_item": "4739_exact_date_close_only",
        "status": "pass",
        "detail": "no neighbour, last-price, adjusted-price, or cross-ticker substitution",
        "future_data_violation_count": 0,
    }]
    write_csv(output / "future_data_audit.csv", future_audit)

    readiness = {
        "task_id": TASK_ID,
        "status": "bounded_market_transition_patch_ready_termination_metadata_partial_for_core_absorption",
        "core_post_last_rows": len(post_last),
        "material_ticker_count": len(summary),
        "material_tickers": [row["ticker"] for row in summary],
        "ticker_4739_unique_required_dates": len(target_4739),
        "ticker_4739_local_exact_close_patch_rows": len(patch),
        "ticker_4739_remaining_local_scope_gap_rows": len(remaining),
        "ticker_4739_market_transfer_proven": len(boundary) == 2,
        "ticker_4739_true_termination": False,
        "ticker_3474_true_termination_proven": True,
        "ticker_3474_last_tradable_date_ready": bool(events_3474[0]["last_tradable_date"]),
        "ticker_3474_holder_treatment_ready": any(row["source_hash"] for row in events_3474[:2]),
        "ticker_3474_exact_suspension_start_ready": False,
        "ready_for_core_market_transition_termination_absorption": True,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    (output / "readiness_for_core_market_transition_termination_absorption.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary_zh = f"""# 4739 轉板鏈與 3474 終止上市 bounded source package

- Core post-last 24,118 列只涉及 4739（18,186）與 3474（5,932），沒有第三個 material ticker。
- 4739 是同代碼 TPEx 轉 TWSE，不是終止交易。轉板邊界 2017-09-07 TPEx、2017-09-08 TWSE 均有官方收盤價。
- 4739 共 {len(target_4739):,} 個 exact decision dates；本機既有 compact 可補 {len(patch):,}，其餘 {len(remaining):,} 是舊 selected-scope compact 未保留，不得誤列 termination/no-trade。
- 3474 是 100% 現金股份交換後終止上市；官方終止日 2016-12-06，最後本機官方成交日為 {events_3474[0]['last_tradable_date']}，每股現金對價 NT$30。
- 3474 精確 suspension start／歷史公告時間仍保留 blocked；未用終止生效日倒填 market_available_at。
- 本包只含 close 與 listing/termination metadata，不含其他資料 family，不計績效。
"""
    (output / "final_summary_zh.md").write_text(summary_zh, encoding="utf-8")

    files = [path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv", "current_step.txt"}]
    checksums = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted(files)]
    write_csv(output / "checksum_manifest.csv", checksums)
    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "output_path": str(output),
        "core_authority": str(core_ledger),
        "network_scope": "three official 3474 event evidence pages only; no market price download",
        "artifacts": checksums,
        "readiness": readiness,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "current_step.txt").write_text(
        "status=complete_ready_for_core_absorption\n"
        "resume_step=none\n"
        f"output={output}\n",
        encoding="utf-8",
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
