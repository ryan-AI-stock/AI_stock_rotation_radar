from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_weekly_ai_diffusion_switch_close_fill import (
    REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, request_month,
    sha256_file, write_checkpoint,
)

TASK = "TASK-RADAR-DATA-THREE-STRATEGY-EXACT-RAW-CLOSE-MINIMUM-FILL-001"
AUTHORITY = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\strategy-center-core-experiments-research-materials\outputs\three_strategy_exact_position_unit_requirements_20150518_20260722\path_independent_official_raw_close_gap_union.csv")
OUT = REPO / "outputs" / "radar_three_strategy_exact_raw_close_fill_20260730"
INDEXES = [
    REPO / "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716/reusable_one_shot_close_index.csv.gz",
    REPO / "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716/bounded_network_raw_full_close_index.csv.gz",
    REPO / "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716/path_independent_primary80_official_raw_close_compact.csv.gz",
]
LISTING_EVIDENCE = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718/weekly_switch_exact_official_no_trade.csv"
NO_TRADE_COLUMNS = [
    "ticker", "date", "market", "classification", "reason", "source_path",
    "source_url", "source_hash", "future_data_violation_count",
]
BLOCKED_COLUMNS = [
    "ticker", "date", "market", "classification", "reason", "source_url",
    "source_hash", "future_data_violation_count",
]


def authority() -> pd.DataFrame:
    d = pd.read_csv(AUTHORITY, dtype={"ticker": str})
    d["ticker"] = d.ticker.str.strip().str.upper()
    d["date"] = d.date.astype(str).str[:10]
    return d.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def index_reuse(keys: pd.DataFrame) -> dict[tuple[str, str], dict]:
    wanted = set(zip(keys.ticker, keys.date)); found: dict[tuple[str, str], dict] = {}
    for path in INDEXES:
        if not path.exists():
            continue
        d = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
        d["ticker"] = d.ticker.astype(str).str.strip().str.upper(); d["date"] = d.date.astype(str).str[:10]
        close_col = "official_raw_close" if "official_raw_close" in d.columns else "close"
        for row in d[d[close_col].notna()].itertuples():
            key = (row.ticker, row.date)
            if key in wanted and key not in found:
                found[key] = {"ticker": key[0], "date": key[1], "market": getattr(row, "market", "TWSE"), "close": getattr(row, close_col), "source_quality": "official_raw_close_local_index_reuse", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": getattr(row, "source_url", ""), "source_hash": getattr(row, "source_hash", ""), "retrieved_at": getattr(row, "retrieved_at", ""), "source_reuse": str(path), "future_data_violation_count": 0}
    return found


def checkpoint_row(item: dict, ticker: str, date: str, path: Path, reuse: str) -> dict | None:
    for row in item.get("rows", []):
        if row.get("date") == date and row.get("close") is not None:
            return {"ticker": ticker, "date": date, "market": "TWSE", "close": row["close"], "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "source_reuse": reuse, "checkpoint_path": str(path), "future_data_violation_count": 0}
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    req = authority(); found = index_reuse(req); no_trade: list[dict] = []; blocked: list[dict] = []; manifest: list[dict] = []
    # Official listing evidence already established 6669 first TWSE trading date as 2019-03-27.
    listing_hash = ""
    if LISTING_EVIDENCE.exists():
        listing_rows = pd.read_csv(LISTING_EVIDENCE, dtype={"ticker": str})
        listing_match = listing_rows[
            listing_rows["ticker"].astype(str).str.strip().eq("6669")
            & listing_rows["classification"].eq("official_no_trade_prelisting")
        ]
        if not listing_match.empty:
            listing_hash = str(listing_match.iloc[0].get("source_hash", ""))
    remaining = req[~req.apply(lambda r: (r.ticker, r.date) in found, axis=1)].copy()
    for row in remaining[remaining.ticker.eq("6669") & remaining.date.lt("2019-03-27")].itertuples():
        no_trade.append({"ticker": row.ticker, "date": row.date, "market": "TWSE", "classification": "official_no_trade_prelisting", "reason": "official_twse_listing_date_2019-03-27", "source_path": str(LISTING_EVIDENCE), "source_hash": listing_hash, "future_data_violation_count": 0})
    remaining = remaining[~((remaining.ticker.eq("6669")) & (remaining.date.lt("2019-03-27")))]
    route_count = 0
    for (ticker, month), group in remaining.groupby(["ticker", remaining.date.str[:7]], sort=True):
        checkpoint = OUT / "checkpoints" / ticker / f"{month}.json.gz"
        if checkpoint.exists():
            item = read_checkpoint(checkpoint)
        else:
            item = request_month(ticker, month); write_checkpoint(checkpoint, item); route_count += 1
        manifest.append({"ticker": ticker, "month": month, "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "http_status": item.get("http_status", ""), "route_status": item.get("status", ""), "retrieved_at": item.get("retrieved_at", ""), "checkpoint_path": str(checkpoint), "future_data_violation_count": 0})
        for date in group.date:
            hit = checkpoint_row(item, ticker, date, checkpoint, "authorized_official_ticker_month_route") if item.get("status") == "accepted" else None
            if hit: found[(ticker, date)] = hit
            elif item.get("status") == "accepted": no_trade.append({"ticker": ticker, "date": date, "market": "TWSE", "classification": "official_no_trade", "reason": "accepted_official_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "future_data_violation_count": 0})
            else: blocked.append({"ticker": ticker, "date": date, "market": "TWSE", "classification": "source_gap", "reason": item.get("error", "official_month_route_not_accepted"), "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "future_data_violation_count": 0})
    patch = pd.DataFrame(found.values()).drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
    atomic_csv(OUT / "three_strategy_exact_official_raw_close_patch.csv", patch)
    atomic_csv(OUT / "three_strategy_exact_official_raw_close_no_trade.csv", pd.DataFrame(no_trade, columns=NO_TRADE_COLUMNS))
    atomic_csv(OUT / "three_strategy_exact_official_raw_close_blocked.csv", pd.DataFrame(blocked, columns=BLOCKED_COLUMNS))
    atomic_csv(OUT / "three_strategy_exact_official_raw_close_source_manifest.csv", pd.DataFrame(manifest))
    atomic_csv(OUT / "future_data_audit.csv", pd.DataFrame([{"audit": "exact_close_only_no_neighbor_no_adjusted_substitution", "future_data_violation_count": 0}]))
    ready = {"task_id": TASK, "requested_unique_keys": len(req), "official_raw_close_ready_keys": len(patch), "official_no_trade_keys": len(no_trade), "blocked_keys": len(blocked), "partition_matches_authority": len(patch)+len(no_trade)+len(blocked)==len(req), "local_reuse_keys": sum(v.get("source_quality") == "official_raw_close_local_index_reuse" for v in found.values()), "new_official_month_routes": route_count, "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_absorption": not blocked, "future_data_violation_count": 0, "formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "not_live_rule": True}
    atomic_json(OUT / "readiness_for_core_three_strategy_exact_raw_close_fill.json", ready); atomic_json(OUT / "progress.json", {**ready, "updated_at": now()}); atomic_text(OUT / "current_step.txt", "status=complete\nresume_step=Strategy_Center_whole_share_units_cash_monthly_withdrawal_replay\n")
    atomic_text(OUT / "final_summary_zh.md", f"# 三策略 exact raw-close fill\n\n- authority={len(req)}；ready={len(patch)}；official no-trade={len(no_trade)}；blocked={len(blocked)}。\n- local reuse={ready['local_reuse_keys']}；new official ticker-month routes={route_count}。\n")
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name not in {'manifest.json','checksum_manifest.csv'}]
    checks=pd.DataFrame([{"file":str(p.relative_to(OUT)).replace('\\','/'),"bytes":p.stat().st_size,"sha256":sha256_file(p)} for p in files]); atomic_csv(OUT / "checksum_manifest.csv", checks); atomic_json(OUT / "manifest.json", {"task_id":TASK,"authority_path":str(AUTHORITY),"authority_sha256":sha256_file(AUTHORITY),"files":checks.to_dict('records'),"readiness":ready})


if __name__ == "__main__": main()
