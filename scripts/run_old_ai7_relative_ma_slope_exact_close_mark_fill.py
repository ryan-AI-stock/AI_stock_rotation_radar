from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, clean_number, now, parse_twse_stock_day, read_checkpoint, request_month, sha256_file, write_checkpoint
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, clean_number, now, parse_twse_stock_day, read_checkpoint, request_month, sha256_file, write_checkpoint


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-00631L-OLD-AI7-RELATIVE-MA-SLOPE-SWITCH-EXACT-CLOSE-MARK-FILL-001"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_00631l_old_ai7_relative_ma_slope_switch_contract_20260719")
RAW_AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
MARK_AUTHORITY = CORE_OUTPUT / "holding_mark_gap_ledger.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_relative_ma_slope_exact_close_mark_fill_20260719"
REUSE_OUTPUTS = [
    REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718",
    REPO / "outputs/radar_vnext_p1_p2_sleeve_internal_timing_close_fill_20260718",
    REPO / "outputs/radar_vnext_p1_p2_strict_bear_cash_final_union_close_fill_20260718",
    REPO / "outputs/radar_vnext_p1_p2_strict_ai_diffusion_bear_cash_close_fill_20260718",
    REPO / "outputs/radar_vnext_p1_p2_strict_ai_diffusion_bear_cash_rechain_close_fill_20260718",
]
LOCAL_2308_ADJUSTED = REPO / "outputs/radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711/checkpoints/adjusted/2308.csv.gz"


def load_raw_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)
    expected = {"00631L": 67, "2308": 1, "2382": 1, "2454": 2, "6669": 1}
    if len(frame) != 72 or frame.groupby("ticker").size().to_dict() != expected:
        raise RuntimeError(f"raw_authority_scope_changed:{len(frame)}:{frame.groupby('ticker').size().to_dict()}")
    return frame


def load_mark_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["date", "ticker"]].drop_duplicates()
    frame["date"] = frame["date"].astype(str).str[:10]
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    if frame.to_dict("records") != [{"date": "2025-08-01", "ticker": "2308"}]:
        raise RuntimeError(f"mark_authority_scope_changed:{frame.to_dict('records')}")
    return frame


def output_checkpoint(output: Path, ticker: str, month: str) -> Path:
    return output / "checkpoints" / "official_raw" / ticker / f"{month}.json.gz"


def local_month_checkpoint(ticker: str, month: str) -> Path | None:
    for root in REUSE_OUTPUTS:
        candidate = root / "checkpoints" / ticker / f"{month}.json.gz"
        if candidate.exists() and read_checkpoint(candidate).get("status") == "accepted":
            return candidate
    return None


def exact_official_rows(item: dict, ticker: str, dates: set[str], lineage: str) -> list[dict]:
    return [
        {
            "ticker": ticker, "date": str(row.get("date", ""))[:10], "market": "TWSE", "close": row["close"],
            "source_quality": "official_twse_selected_ticker_month_close_only",
            "adjustment_policy": "official_unadjusted_execution_close_only",
            "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""),
            "retrieved_at": item.get("retrieved_at", ""), "source_reuse": lineage,
            "future_data_violation_count": 0,
        }
        for row in item.get("rows", [])
        if str(row.get("date", ""))[:10] in dates and row.get("close") is not None
    ]


def yahoo_mark(target: str) -> tuple[dict, dict]:
    start = datetime.fromisoformat(target).replace(tzinfo=timezone.utc) - timedelta(days=4)
    end = datetime.fromisoformat(target).replace(tzinfo=timezone.utc) + timedelta(days=5)
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2308.TW?" + urlencode({
        "period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d",
        "events": "div,splits", "includeAdjustedClose": "true",
    })
    retrieved = now()
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 RadarOldAi7CloseMark/1.0"}, timeout=60)
    raw = response.content
    result = {
        "ticker": "2308", "date": target, "source_url": response.url, "source_hash": hashlib.sha256(raw).hexdigest(),
        "retrieved_at": retrieved, "http_status": response.status_code, "response_bytes": len(raw),
        "status": "blocked", "reason": "", "mark": None, "factor_audit": {},
    }
    if response.status_code != 200:
        result["reason"] = f"http_{response.status_code}"
        return result, {"source_url": response.url, "source_hash": result["source_hash"], "events": []}
    try:
        chart = json.loads(raw.decode("utf-8")).get("chart", {})
        item = (chart.get("result") or [])[0]
        zone = ZoneInfo((item.get("meta") or {}).get("exchangeTimezoneName") or "Asia/Taipei")
        quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
        adjusted = ((item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        target_index = next((index for index, stamp in enumerate(item.get("timestamp") or []) if datetime.fromtimestamp(int(stamp), zone).date().isoformat() == target), None)
        if target_index is None:
            result["reason"] = "provider_session_absent"
            return result, {"source_url": response.url, "source_hash": result["source_hash"], "events": item.get("events") or {}}
        close_values = quote.get("close") or []
        close = clean_number(close_values[target_index]) if target_index < len(close_values) else None
        adjusted_close = clean_number(adjusted[target_index]) if target_index < len(adjusted) else None
        if close is None or adjusted_close is None:
            result["reason"] = "provider_raw_or_adjusted_value_missing"
            return result, {"source_url": response.url, "source_hash": result["source_hash"], "events": item.get("events") or {}}
        factor = adjusted_close / close
        result["status"] = "accepted"
        result["mark"] = {
            "ticker": "2308", "date": target, "adjusted_analysis_mark": adjusted_close,
            "source_quality": "trusted_nonofficial_yahoo_adjusted_analysis_mark",
            "adjustment_policy": "provider_adjusted_analysis_only_not_execution_price_not_formal",
            "source_url": response.url, "source_hash": result["source_hash"], "retrieved_at": retrieved,
            "future_data_violation_count": 0,
        }
        result["factor_audit"] = {
            "ticker": "2308", "date": target, "provider_raw_close": close,
            "provider_adjusted_close": adjusted_close, "adjustment_factor": factor,
            "factor_positive": factor > 0, "raw_used_as_adjusted": False,
            "event_payload_present": bool(item.get("events")), "source_url": response.url,
            "source_hash": result["source_hash"], "retrieved_at": retrieved,
            "source_quality": "trusted_nonofficial_yahoo_adjusted_analysis_mark",
            "future_data_violation_count": 0,
        }
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result["reason"] = f"parse_{type(exc).__name__}"
    return result, {"source_url": response.url, "source_hash": result["source_hash"], "events": {}}


def factor_continuity_mark(target: str, official_raw_close: float | None) -> tuple[dict | None, dict]:
    """Reconstruct only when trusted provider factors agree on both sides of the missing session."""
    if official_raw_close is None or not LOCAL_2308_ADJUSTED.exists():
        return None, {"factor_continuity_status": "unavailable_missing_official_raw_or_local_trusted_history"}
    with gzip.open(LOCAL_2308_ADJUSTED, "rt", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("ticker") == "2308"]
    prior = [row for row in rows if row.get("date", "") < target and row.get("adjusted_close") and row.get("raw_close_comparator")]
    later = [row for row in rows if row.get("date", "") > target and row.get("adjusted_close") and row.get("raw_close_comparator")]
    if not prior or not later:
        return None, {"factor_continuity_status": "unavailable_missing_neighbor_factor"}
    before, after = prior[-1], later[0]
    before_factor = float(before["adjusted_close"]) / float(before["raw_close_comparator"])
    after_factor = float(after["adjusted_close"]) / float(after["raw_close_comparator"])
    tolerance = 1e-7
    if abs(before_factor - after_factor) > tolerance:
        return None, {
            "factor_continuity_status": "blocked_factor_changes_across_missing_session",
            "before_date": before["date"], "after_date": after["date"],
            "before_factor": before_factor, "after_factor": after_factor, "factor_tolerance": tolerance,
        }
    factor = (before_factor + after_factor) / 2
    audit = {
        "ticker": "2308", "date": target, "factor_continuity_status": "accepted_trusted_factor_equal_on_both_adjacent_sessions",
        "before_date": before["date"], "after_date": after["date"], "before_factor": before_factor,
        "after_factor": after_factor, "factor_tolerance": tolerance, "adjustment_factor": factor,
        "official_raw_close_for_reconciliation": official_raw_close,
        "reconstructed_adjusted_analysis_mark": official_raw_close * factor,
        "raw_used_as_adjusted": False,
        "source_quality": "trusted_nonofficial_yahoo_factor_continuity_reconstruction",
        "source_url": before.get("source_url", ""), "source_hash": sha256_file(LOCAL_2308_ADJUSTED),
        "retrieved_at": before.get("retrieval_time_utc", ""), "future_data_violation_count": 0,
    }
    mark = {
        "ticker": "2308", "date": target, "adjusted_analysis_mark": official_raw_close * factor,
        "source_quality": "trusted_nonofficial_yahoo_factor_continuity_reconstruction",
        "adjustment_policy": "trusted_yahoo_factor_applied_to_official_raw_close; research_analysis_only_not_execution_price_not_formal",
        "source_url": before.get("source_url", ""), "source_hash": sha256_file(LOCAL_2308_ADJUSTED),
        "retrieved_at": before.get("retrieval_time_utc", ""), "future_data_violation_count": 0,
    }
    return mark, audit


def write_manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checks = pd.DataFrame([
        {"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in files
    ])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {
        "task": TASK, "generated_at": now(), "raw_authority_path": str(RAW_AUTHORITY),
        "raw_authority_sha256": sha256_file(RAW_AUTHORITY), "mark_authority_path": str(MARK_AUTHORITY),
        "mark_authority_sha256": sha256_file(MARK_AUTHORITY), "readiness": readiness,
        "files": checks.to_dict("records"), "future_data_violation_count": 0, **FLAGS,
    })


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw_authority = load_raw_authority(args.raw_authority)
    mark_authority = load_mark_authority(args.mark_authority)
    raw_rows: list[dict] = []
    no_trade: list[dict] = []
    network_routes = 0
    reused_routes = 0
    for (ticker, month), group in raw_authority.assign(month=lambda x: x["date"].str[:7]).groupby(["ticker", "month"]):
        dates = set(group["date"])
        checkpoint = output_checkpoint(output, ticker, month)
        if checkpoint.exists() and read_checkpoint(checkpoint).get("status") == "accepted":
            item = read_checkpoint(checkpoint)
            lineage = "resumed_authorized_official_month_checkpoint"
            network_routes += int(bool(item.get("network_attempted")))
        else:
            reuse = local_month_checkpoint(ticker, month)
            if reuse is not None:
                item = read_checkpoint(reuse)
                lineage = "previous_accepted_official_month_checkpoint"
                reused_routes += 1
            else:
                item = request_month(ticker, month)
                item["task"] = TASK
                write_checkpoint(checkpoint, item)
                lineage = "network_authorized_official_month"
                network_routes += 1
        found = {row["date"] for row in exact_official_rows(item, ticker, dates, lineage)}
        raw_rows.extend(exact_official_rows(item, ticker, dates, lineage))
        if item.get("status") == "accepted":
            for date in sorted(dates - found):
                no_trade.append({
                    "ticker": ticker, "date": date, "market": "TWSE", "classification": "official_no_trade",
                    "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row",
                    "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""),
                    "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0,
                })
    raw_patch = pd.DataFrame(raw_rows).drop_duplicates(["ticker", "date"], keep="first").sort_values(["ticker", "date"]).merge(raw_authority, on=["ticker", "date"], how="inner")
    ready_keys = set(map(tuple, raw_patch[["ticker", "date"]].to_records(index=False)))
    no_trade_keys = {(row["ticker"], row["date"]) for row in no_trade}
    blocked = pd.DataFrame([
        {"ticker": row.ticker, "date": row.date, "market": "TWSE", "classification": "source_gap",
         "reason": "authorized_official_month_route_failed_or_not_accepted", "source_url": "", "source_hash": "", "retrieved_at": "", "future_data_violation_count": 0}
        for row in raw_authority.itertuples(index=False)
        if (row.ticker, row.date) not in ready_keys and (row.ticker, row.date) not in no_trade_keys
    ])
    ledger_columns = ["ticker", "date", "market", "classification", "reason", "source_url", "source_hash", "retrieved_at", "future_data_violation_count"]
    no_trade_frame = pd.DataFrame(no_trade).reindex(columns=ledger_columns)
    blocked = blocked.reindex(columns=ledger_columns)

    mark_result, event_evidence = yahoo_mark(mark_authority.iloc[0]["date"])
    official_factor_raw = next((row for row in raw_patch.to_dict("records") if row["ticker"] == "2308" and row["date"] == "2025-08-01"), None)
    # 2308 2025-08-01 is a distinct mark authority, so obtain its official raw close only as factor reconciliation evidence.
    factor_month = "2025-08"
    factor_checkpoint = output_checkpoint(output, "2308", factor_month)
    if factor_checkpoint.exists() and read_checkpoint(factor_checkpoint).get("status") == "accepted":
        factor_item = read_checkpoint(factor_checkpoint)
        network_routes += int(bool(factor_item.get("network_attempted")))
    else:
        factor_item = request_month("2308", factor_month)
        factor_item["task"] = TASK
        factor_item["role"] = "adjusted_mark_factor_reconciliation_only"
        write_checkpoint(factor_checkpoint, factor_item)
        network_routes += 1
    factor_raw_rows = exact_official_rows(factor_item, "2308", {"2025-08-01"}, "network_adjusted_mark_factor_reconciliation")
    factor_audit = mark_result.get("factor_audit", {})
    if factor_audit:
        factor_audit["official_raw_close_for_reconciliation"] = factor_raw_rows[0]["close"] if factor_raw_rows else None
        factor_audit["official_raw_source_url"] = factor_raw_rows[0]["source_url"] if factor_raw_rows else factor_item.get("source_url", "")
        factor_audit["official_raw_source_hash"] = factor_raw_rows[0]["source_hash"] if factor_raw_rows else factor_item.get("source_hash", "")
        factor_audit["official_raw_matches_provider_raw"] = bool(factor_raw_rows and abs(float(factor_audit["provider_raw_close"]) - float(factor_raw_rows[0]["close"])) < 1e-9)
    if not mark_result.get("mark"):
        reconstructed_mark, continuity_audit = factor_continuity_mark(
            mark_authority.iloc[0]["date"], factor_raw_rows[0]["close"] if factor_raw_rows else None
        )
        if reconstructed_mark:
            mark_result["mark"] = reconstructed_mark
            mark_result["status"] = "accepted_factor_continuity_reconstruction"
            mark_result["reason"] = ""
            factor_audit = continuity_audit
        elif not factor_audit:
            factor_audit = continuity_audit
    mark_patch = pd.DataFrame([mark_result["mark"]] if mark_result.get("mark") else [])
    mark_blocked = pd.DataFrame([] if mark_result.get("mark") else [{
        "ticker": "2308", "date": "2025-08-01", "classification": "adjusted_mark_blocked",
        "reason": mark_result.get("reason", "trusted_adjusted_source_unavailable"), "source_url": mark_result.get("source_url", ""),
        "source_hash": mark_result.get("source_hash", ""), "retrieved_at": mark_result.get("retrieved_at", ""), "future_data_violation_count": 0,
    }])

    atomic_csv(output / "old_ai7_relative_exact_official_raw_close_patch.csv", raw_patch)
    atomic_csv(output / "old_ai7_relative_exact_official_raw_close_no_trade.csv", no_trade_frame)
    atomic_csv(output / "old_ai7_relative_exact_official_raw_close_blocked.csv", blocked)
    atomic_csv(output / "old_ai7_relative_adjusted_holding_mark_patch.csv", mark_patch)
    atomic_csv(output / "old_ai7_relative_adjusted_holding_mark_blocked.csv", mark_blocked)
    atomic_csv(output / "old_ai7_relative_adjustment_factor_audit.csv", pd.DataFrame([factor_audit]))
    atomic_json(output / "old_ai7_relative_adjusted_event_evidence.json", event_evidence)
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
        {"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "raw_used_as_adjusted", "status": "false", "future_data_violation_count": 0},
        {"audit": "neighbor_last_benchmark_substitution", "status": "false", "future_data_violation_count": 0},
        {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0},
    ]))
    partition = len(raw_patch) + len(no_trade_frame) + len(blocked)
    readiness = {
        "task": TASK, "status": "complete_ready_for_core_absorption" if not len(blocked) and not len(mark_blocked) else "complete_with_explicit_source_blockers",
        "official_raw_authority_keys": len(raw_authority), "official_raw_close_ready_rows": len(raw_patch),
        "official_raw_no_trade_rows": len(no_trade_frame), "official_raw_blocked_rows": len(blocked),
        "official_raw_partition_rows": partition, "official_raw_partition_matches_authority": partition == len(raw_authority),
        "adjusted_mark_authority_keys": len(mark_authority), "adjusted_mark_ready_rows": len(mark_patch), "adjusted_mark_blocked_rows": len(mark_blocked),
        "network_routes": network_routes, "reused_accepted_checkpoint_routes": reused_routes,
        "trusted_adjusted_mark_network_routes": 1,
        "network_outside_authority_rows": 0, "non_close_family_download_rows": 0,
        "raw_used_as_adjusted": False, "ready_for_core_old_ai7_relative_close_mark_absorption": not len(blocked) and not len(mark_blocked),
        "ready_for_experiments": False, "data_readiness_blocked_only": bool(len(blocked) or len(mark_blocked)),
        "may_be_used_to_reject_strategy": False, "future_data_violation_count": 0, **FLAGS,
    }
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([
        {"family": "official_raw_execution_close", "requested": len(raw_authority), "ready": len(raw_patch), "official_no_trade": len(no_trade_frame), "blocked": len(blocked)},
        {"family": "event_aware_adjusted_holding_mark", "requested": len(mark_authority), "ready": len(mark_patch), "official_no_trade": 0, "blocked": len(mark_blocked)},
    ]))
    atomic_json(output / "readiness_for_core_old_ai7_relative_close_mark_absorption.json", readiness)
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_old_ai7_relative_rechain\n")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 relative MA-slope exact close/mark fill\n\n- raw authority={len(raw_authority)}；ready={len(raw_patch)}；official_no_trade={len(no_trade_frame)}；blocked={len(blocked)}。\n- adjusted mark 2308/2025-08-01 ready={len(mark_patch)}；blocked={len(mark_blocked)}。\n- raw execution 與 adjusted holding mark 分欄；未計績效。\n")
    write_manifest(output, readiness)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return readiness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-authority", type=Path, default=RAW_AUTHORITY)
    parser.add_argument("--mark-authority", type=Path, default=MARK_AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
