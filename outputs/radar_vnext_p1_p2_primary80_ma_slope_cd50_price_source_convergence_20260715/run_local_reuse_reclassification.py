from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[0]
P1 = ROOT / "radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710"
P3 = ROOT / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
P3_EXACT = ROOT / "radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711"
P3_RANK1 = ROOT / "radar_vnext_p3_layer04_rank1_sequential_lifecycle_adjusted_hlc_factor_source_package_20260713"
TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-LAYER4-PRIMARY80-MA-SLOPE-CD50-PRICE-SOURCE-CONVERGENCE-001"
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


def ticker_text(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    frame.to_csv(temp, index=False, encoding="utf-8-sig", compression="gzip" if path.suffix == ".gz" else None)
    if path.suffix == ".gz":
        with gzip.open(temp, "rt", encoding="utf-8-sig") as handle:
            next(csv.reader(handle), None)
    os.replace(temp, path)


def write_json(path: Path, payload: dict) -> None:
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(step: str, **extra: object) -> None:
    write_json(OUT / "local_reuse_audit_progress.json", {
        "task_id": TASK_ID, "status": "running", "current_step": step,
        "network_acquisition_enabled": False, "updated_at": now(), **extra,
    })
    (OUT / "current_step.txt").write_text(step + "\n", encoding="utf-8")


def source_candidates() -> list[Path]:
    tokens = ("ohlc", "price", "raw_hlc", "official_raw", "unadjusted", "adjusted")
    paths = []
    for pattern in ("*.csv", "*.csv.gz"):
        for path in ROOT.rglob(pattern):
            if OUT in path.parents:
                continue
            source_locator = str(path).lower()
            if not any(token in source_locator for token in tokens):
                continue
            if path.stat().st_size > 150 * 1024 * 1024:
                continue
            paths.append(path)
    return sorted(set(paths))


def read_candidate(path: Path, required_keys: pd.MultiIndex) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    evidence = {
        "source_path": str(path), "bytes": path.stat().st_size,
        "header_status": "unread", "raw_rows_reused": 0, "adjusted_rows_reused": 0,
        "schema_issue": "", "sha256": "",
    }
    try:
        header = pd.read_csv(path, nrows=0).columns.tolist()
    except Exception as exc:
        evidence.update({"header_status": "read_failed", "schema_issue": type(exc).__name__})
        return pd.DataFrame(), pd.DataFrame(), evidence
    ticker_col = "ticker" if "ticker" in header else "stock_id" if "stock_id" in header else None
    date_col = "date" if "date" in header else "trade_date" if "trade_date" in header else "price_date" if "price_date" in header else None
    raw_col = next((column for column in ("close", "official_raw_close") if column in header), None)
    adjusted_col = "adjusted_close" if "adjusted_close" in header else "adj_close" if "adj_close" in header else None
    if not ticker_col or not date_col or (not raw_col and not adjusted_col):
        evidence.update({"header_status": "schema_not_price_rows", "schema_issue": "missing ticker/date/value columns"})
        return pd.DataFrame(), pd.DataFrame(), evidence
    wanted = list(dict.fromkeys([ticker_col, date_col, raw_col, adjusted_col, "market", "name", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc", "retrieved_at"]))
    wanted = [column for column in wanted if column and column in header]
    try:
        frame = pd.read_csv(path, usecols=wanted, dtype={ticker_col: str, date_col: str})
    except Exception as exc:
        evidence.update({"header_status": "body_read_failed", "schema_issue": type(exc).__name__})
        return pd.DataFrame(), pd.DataFrame(), evidence
    frame["ticker"] = frame[ticker_col].map(ticker_text)
    frame["date"] = frame[date_col].astype(str)
    keys = pd.MultiIndex.from_frame(frame[["ticker", "date"]])
    frame = frame.loc[keys.isin(required_keys)].copy()
    if frame.empty:
        evidence["header_status"] = "valid_schema_no_required_keys"
        return pd.DataFrame(), pd.DataFrame(), evidence
    common = pd.DataFrame({
        "ticker": frame["ticker"], "date": frame["date"],
        "market": frame["market"].astype(str) if "market" in frame else "",
        "name": frame["name"].astype(str) if "name" in frame else "",
        "source_quality": frame["source_quality"].astype(str) if "source_quality" in frame else "source_quality_inferred_from_package",
        "adjustment_policy": frame["adjustment_policy"].astype(str) if "adjustment_policy" in frame else "package_policy_review_required",
        "source_url": frame["source_url"].astype(str) if "source_url" in frame else "",
        "source_hash": frame["source_hash"].astype(str) if "source_hash" in frame else "",
        "retrieved_at": frame["retrieval_time_utc"].astype(str) if "retrieval_time_utc" in frame else frame["retrieved_at"].astype(str) if "retrieved_at" in frame else "",
        "source_path": str(path),
    })
    raw, adjusted = pd.DataFrame(), pd.DataFrame()
    if raw_col:
        raw = common.copy()
        raw["raw_close"] = pd.to_numeric(frame[raw_col], errors="coerce")
        quality = raw["source_quality"].str.lower()
        url = raw["source_url"].str.lower()
        locator = str(path).lower()
        official_mask = (
            (quality.str.contains("official", na=False) & ~quality.str.contains("nonofficial", na=False))
            | url.str.contains("twse.com.tw|tpex.org.tw", regex=True, na=False)
            | ("official" in locator and "trusted_adjusted" not in locator)
        )
        raw = raw.loc[raw["raw_close"].notna() & raw["raw_close"].gt(0) & official_mask]
    if adjusted_col:
        adjusted = common.copy()
        adjusted["adjusted_close"] = pd.to_numeric(frame[adjusted_col], errors="coerce")
        adjusted = adjusted.loc[adjusted["adjusted_close"].notna() & adjusted["adjusted_close"].gt(0)]
    evidence.update({
        "header_status": "required_keys_reused", "raw_rows_reused": len(raw),
        "adjusted_rows_reused": len(adjusted), "sha256": sha256_file(path),
    })
    return raw, adjusted, evidence


def normalize_prebuilt(path: Path, raw: bool) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"ticker": str, "date": str})
    frame["ticker"] = frame["ticker"].map(ticker_text)
    result = frame[["ticker", "date"]].copy()
    if raw:
        result["raw_close"] = pd.to_numeric(frame["value"], errors="coerce")
    else:
        result["adjusted_close"] = pd.to_numeric(frame["value"], errors="coerce")
    for column in ("market", "name", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieved_at", "source_path"):
        result[column] = frame[column] if column in frame else ""
    return result


def collect_trusted_raw_comparators(required_keys: pd.MultiIndex) -> pd.DataFrame:
    paths = []
    paths.extend((P1 / "compact" / "trusted_adjusted_analysis").glob("*.csv.gz"))
    paths.extend((P3 / "compact" / "adjusted").glob("*.csv.gz"))
    paths.extend((P3_EXACT / "checkpoints" / "adjusted").glob("*.csv.gz"))
    paths.append(P3_RANK1 / "rank1_adjusted_analysis_hlc_factor_compact.csv.gz")
    rows = []
    for path in paths:
        if not path.exists():
            continue
        header = pd.read_csv(path, nrows=0).columns.tolist()
        raw_col = next((column for column in ("close", "raw_close_comparator", "provider_raw_close") if column in header), None)
        if not raw_col or "ticker" not in header or "date" not in header:
            continue
        wanted = [column for column in ("ticker", "date", raw_col, "source_quality", "adjusted_source_quality", "source_url", "source_hash") if column in header]
        frame = pd.read_csv(path, usecols=wanted, dtype={"ticker": str, "date": str})
        frame["ticker"] = frame["ticker"].map(ticker_text)
        keys = pd.MultiIndex.from_frame(frame[["ticker", "date"]])
        frame = frame.loc[keys.isin(required_keys)].copy()
        if frame.empty:
            continue
        quality_col = "source_quality" if "source_quality" in frame else "adjusted_source_quality" if "adjusted_source_quality" in frame else None
        rows.append(pd.DataFrame({
            "ticker": frame["ticker"], "date": frame["date"],
            "trusted_raw_close": pd.to_numeric(frame[raw_col], errors="coerce"),
            "trusted_raw_source_quality": frame[quality_col].astype(str) if quality_col else "trusted_nonofficial_raw_comparator",
            "trusted_raw_source_url": frame["source_url"].astype(str) if "source_url" in frame else "",
            "trusted_raw_source_hash": frame["source_hash"].astype(str) if "source_hash" in frame else "",
            "trusted_raw_source_path": str(path),
        }))
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "trusted_raw_close"])
    combined = pd.concat(rows, ignore_index=True)
    combined = combined.loc[combined["trusted_raw_close"].notna() & combined["trusted_raw_close"].gt(0)]
    return combined.drop_duplicates(["ticker", "date"], keep="first")


def main() -> None:
    checkpoint("build_union_exact_requirement")
    adjusted_requirement = pd.read_csv(OUT / "p1_p2_primary80_adjusted_analysis_exact_requirement.csv.gz", dtype={"ticker": str})
    raw_requirement = pd.read_csv(OUT / "p1_p2_primary80_official_raw_execution_exact_requirement.csv.gz", dtype={"ticker": str})
    requirement = pd.concat([
        adjusted_requirement.assign(adjusted_required=True, raw_required=False),
        raw_requirement.assign(adjusted_required=False, raw_required=True),
    ], ignore_index=True)
    requirement = requirement.groupby(["period", "ticker", "date"], as_index=False).agg(
        requirement_role=("requirement_role", lambda values: "|".join(sorted(set(values)))),
        adjusted_required=("adjusted_required", "max"), raw_required=("raw_required", "max"),
    )
    required_keys = pd.MultiIndex.from_frame(requirement[["ticker", "date"]])

    raw_parts = [normalize_prebuilt(OUT / "p1_p2_primary80_official_raw_execution_close_reuse_compact.csv.gz", True)]
    adjusted_parts = [normalize_prebuilt(OUT / "p1_p2_primary80_adjusted_analysis_close_reuse_compact.csv.gz", False)]
    evidence_rows = []
    candidates = source_candidates()
    checkpoint("scan_preexisting_local_price_packages", total_files=len(candidates))
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(read_candidate, path, required_keys): path for path in candidates}
        for index, future in enumerate(as_completed(futures), start=1):
            raw, adjusted, evidence = future.result()
            if not raw.empty:
                raw_parts.append(raw)
            if not adjusted.empty:
                adjusted_parts.append(adjusted)
            evidence_rows.append(evidence)
            if index % 100 == 0:
                checkpoint("scan_preexisting_local_price_packages", completed=index, total_files=len(candidates))
    raw = pd.concat(raw_parts, ignore_index=True, sort=False).drop_duplicates(["ticker", "date"], keep="first")
    adjusted = pd.concat(adjusted_parts, ignore_index=True, sort=False).drop_duplicates(["ticker", "date"], keep="first")
    trusted_raw = collect_trusted_raw_comparators(required_keys)
    merged = requirement.merge(raw, on=["ticker", "date"], how="left", suffixes=("", "_raw"))
    merged = merged.merge(adjusted[["ticker", "date", "adjusted_close", "source_quality", "source_path", "source_hash"]], on=["ticker", "date"], how="left", suffixes=("_raw", "_adjusted"))
    merged = merged.merge(trusted_raw, on=["ticker", "date"], how="left")
    merged["raw_ready"] = merged["raw_close"].notna()
    merged["trusted_raw_comparator_ready"] = merged["trusted_raw_close"].notna()
    merged["analysis_raw_any_ready"] = merged["raw_ready"] | merged["trusted_raw_comparator_ready"]
    merged["analysis_raw_close"] = merged["raw_close"].combine_first(merged["trusted_raw_close"])
    merged["adjusted_ready"] = merged["adjusted_close"].notna()
    merged["reconstructable_factor"] = merged["analysis_raw_any_ready"] & merged["adjusted_ready"]
    merged["adjustment_factor"] = merged["adjusted_close"] / merged["analysis_raw_close"]
    merged.loc[~merged["reconstructable_factor"], "adjustment_factor"] = pd.NA
    merged["future_data_violation_count"] = 0

    table_a = merged.loc[merged["analysis_raw_any_ready"] & (merged["adjusted_required"] | merged["raw_required"])].copy()
    table_a["category"] = "A_existing_raw_close_unadjusted_MA_slope_ready"
    table_b = merged.loc[merged["adjusted_required"] & merged["reconstructable_factor"]].copy()
    table_b["category"] = "B_existing_raw_plus_adjusted_factor_reconstructable"
    table_c = merged.loc[merged["raw_required"] & ~merged["raw_ready"] & (merged["trusted_raw_comparator_ready"] | merged["adjusted_ready"])].copy()
    table_c["category"] = "C_true_local_official_raw_gap_trusted_source_proves_trade"
    table_d = merged.loc[merged["adjusted_required"] & merged["analysis_raw_any_ready"] & ~merged["adjusted_ready"]].copy()
    table_d["category"] = "D_raw_ready_adjusted_factor_or_event_incomplete"
    table_e = merged.loc[(merged["adjusted_required"] | merged["raw_required"]) & ~merged["analysis_raw_any_ready"] & ~merged["adjusted_ready"]].copy()
    table_e["category"] = "E_no_exact_trade_evidence_prelisting_suspension_or_not_applicable_review"

    write_frame(OUT / "reuse_A_existing_raw_close.csv.gz", table_a)
    write_frame(OUT / "reuse_B_raw_plus_adjusted_factor_reconstructable.csv.gz", table_b)
    write_frame(OUT / "reuse_C_true_local_raw_gap.csv.gz", table_c)
    write_frame(OUT / "reuse_D_raw_ready_adjusted_factor_incomplete.csv.gz", table_d)
    write_frame(OUT / "reuse_E_not_applicable_or_no_trade_review.csv.gz", table_e)
    evidence = pd.DataFrame(evidence_rows)
    write_frame(OUT / "local_price_source_path_schema_audit.csv", evidence)

    interrupted = []
    for path in sorted((OUT / "raw_cache").rglob("*")) if (OUT / "raw_cache").exists() else []:
        if not path.is_file():
            continue
        interrupted.append({
            "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path),
            "downloaded_before_emergency_stop": True,
            "accepted_into_preexisting_reuse_verdict": False,
        })
    interrupted_frame = pd.DataFrame(interrupted)
    write_frame(OUT / "interrupted_network_download_inventory.csv", interrupted_frame)

    summary_rows = []
    for period in ("P1", "P2"):
        part = merged.loc[merged["period"].eq(period)]
        adjusted_scope = part.loc[part["adjusted_required"]]
        raw_scope = part.loc[part["raw_required"]]
        summary_rows.append({
            "period": period,
            "adjusted_requirement_keys": len(adjusted_scope),
            "adjusted_direct_ready_keys": int(adjusted_scope["adjusted_ready"].sum()),
            "A_raw_available_for_unadjusted_MA_keys": int(adjusted_scope["analysis_raw_any_ready"].sum()),
            "A_official_raw_keys": int(adjusted_scope["raw_ready"].sum()),
            "A_trusted_raw_comparator_only_keys": int((~adjusted_scope["raw_ready"] & adjusted_scope["trusted_raw_comparator_ready"]).sum()),
            "B_raw_plus_adjusted_reconstructable_keys": int((adjusted_scope["analysis_raw_any_ready"] & adjusted_scope["adjusted_ready"]).sum()),
            "D_raw_ready_factor_incomplete_keys": int((adjusted_scope["analysis_raw_any_ready"] & ~adjusted_scope["adjusted_ready"]).sum()),
            "adjusted_neither_source_review_keys": int((~adjusted_scope["analysis_raw_any_ready"] & ~adjusted_scope["adjusted_ready"]).sum()),
            "raw_execution_requirement_keys": len(raw_scope),
            "raw_execution_ready_keys": int(raw_scope["raw_ready"].sum()),
            "C_true_local_raw_gap_trusted_trade_evidence_keys": int((~raw_scope["raw_ready"] & (raw_scope["trusted_raw_comparator_ready"] | raw_scope["adjusted_ready"])).sum()),
            "E_raw_no_trade_or_NA_review_keys": int((~raw_scope["analysis_raw_any_ready"] & ~raw_scope["adjusted_ready"]).sum()),
        })
    summary = pd.DataFrame(summary_rows)
    summary["raw_execution_ready_share"] = summary["raw_execution_ready_keys"] / summary["raw_execution_requirement_keys"]
    summary["adjusted_direct_ready_share"] = summary["adjusted_direct_ready_keys"] / summary["adjusted_requirement_keys"]
    summary["future_data_violation_count"] = 0
    write_frame(OUT / "local_reuse_A_to_E_coverage_summary.csv", summary)

    reasons = pd.DataFrame([
        {"issue": "Core path registry incomplete", "evidence": "later Radar selected-price/all80/rank1 packages contain exact rows outside Core original path list", "classification": "ingestion_path_gap_not_price_gap"},
        {"issue": "schema variation", "evidence": "close/official_raw_close/entry_close/exit_close and date/trade_date/price_date require normalization", "classification": "schema_mapping_gap_not_price_gap"},
        {"issue": "calendar contamination", "evidence": "legacy bulk can label a holiday query with query date although response represents prior session; 2019-10-10 example", "classification": "calendar_response_date_bug"},
        {"issue": "scope mismatch", "evidence": "P3 initial compact used extended watchlist scope; exact primary80 supplemental packages were separate", "classification": "scope_join_gap_not_price_gap"},
        {"issue": "suspension/prelisting", "evidence": "market session exists but ticker need not have an official row", "classification": "not_applicable_requires_official_no_row_or_listing_evidence"},
        {"issue": "adjusted source limitation", "evidence": "raw execution close can exist while trusted adjusted/corporate-action factor remains blocked", "classification": "factor_event_gap_not_daily_close_gap"},
    ])
    write_frame(OUT / "why_existing_price_was_not_hit_ledger.csv", reasons)

    readiness = {
        "task_id": TASK_ID,
        "status": "network_stopped_local_reuse_reclassification_completed_strategy_review_required",
        "network_acquisition_stopped": True,
        "interrupted_cache_files": len(interrupted_frame),
        "interrupted_cache_bytes": int(interrupted_frame["bytes"].sum()) if len(interrupted_frame) else 0,
        "preexisting_local_reuse_summary": summary.to_dict("records"),
        "can_compute_unadjusted_MA_slope_where_A_ready": True,
        "can_reconstruct_adjusted_close_where_B_ready": True,
        "C_scope_is_broad_planning_calendar_not_materialized_action_legs": True,
        "C_requires_action_leg_intersection_before_source_acquisition": True,
        "network_resume_authorized": False,
        "next_required_step": "Core must normalize local source registry/schema and materialize MA/action legs before any exact official raw gap request",
        "all_requirements_reconstructable_from_preexisting_local": bool(len(table_c) == 0 and len(table_d) == 0),
        "ready_for_core_absorption": False,
        "requires_strategy_center_review_before_any_network_resume": True,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(OUT / "readiness_after_emergency_local_reuse_audit.json", readiness)
    final = f"""# P1/P2 primary80 價格來源緊急本機重用稽核

## 結論

- 新增網路下載已停止；cache/checkpoint 全部保留，沒有刪除。
- MA/斜率不需要重新下載全段日價。既有本機 raw 或 trusted comparator 已覆蓋 P1 {summary.loc[summary['period'].eq('P1'), 'A_raw_available_for_unadjusted_MA_keys'].iloc[0] / summary.loc[summary['period'].eq('P1'), 'adjusted_requirement_keys'].iloc[0]:.4%}、P2 {summary.loc[summary['period'].eq('P2'), 'A_raw_available_for_unadjusted_MA_keys'].iloc[0] / summary.loc[summary['period'].eq('P2'), 'adjusted_requirement_keys'].iloc[0]:.4%} 的分析 key。
- 既有 adjusted series 可直接覆蓋 P1 {summary.loc[summary['period'].eq('P1'), 'adjusted_direct_ready_share'].iloc[0]:.4%}、P2 {summary.loc[summary['period'].eq('P2'), 'adjusted_direct_ready_share'].iloc[0]:.4%}。
- C 類目前仍是 broad planning calendar 的潛在 official raw gap，不是已 materialize 的實際交易 execution leg。必須先由 Core 算完 MA/斜率與 action，再取實際 action dates 交集；不得直接依 C 表恢復下載。
- P1 既有 63 檔問題主要是 adjusted factor / corporate-action / 舊碼來源治理，不是整段每日 raw close 都不存在。

## 停止點

- 中斷點：P2 official raw 1125/1138 routes。
- 中斷 cache：{len(interrupted_frame)} files / {int(interrupted_frame['bytes'].sum()) if len(interrupted_frame) else 0} bytes。
- 中斷下載未混入 pre-existing reuse verdict。
- 中斷前已產生 P2 trusted adjusted delta；official raw delta 尚未 finalize。
- 現在沒有 matching network runner。

## A-E 分類

- A：已有 raw close，可算未調整 MA/斜率。
- B：已有 raw + adjusted series/factor，可重建 research-grade adjusted close。
- C：trusted source 顯示該 key 有交易，但本機未命中 official raw；仍須先與實際 action leg 交集。
- D：raw 已有，只缺 adjusted factor/event；不是每日收盤價缺口。
- E：無 exact trade evidence，需依上市前、停牌、休市或 official no-row 分類，不可直接稱 source gap。

## 為何先前沒有命中

- Core source path registry 未納入後續 Radar selected-price、all80、rank1 packages。
- date/close 欄位存在 schema 差異，需要統一 date/trade_date/price_date 與 close/official_raw_close 等欄位。
- 舊 bulk cache 有 query date 與實際 response market date 混淆風險。
- P3 初版 watchlist scope 與 exact primary80 supplemental package 分離。
- 上市前、停牌與 official no-row 被混入一般 calendar gap。

## 下一步

- 網路維持 disabled。
- Strategy Center 若要續作，應先交 Core 修 local path/schema/calendar ingestion，利用 A/B 計算 MA/斜率與 action ledger。
- Core 只應把 action ledger 中仍缺 official raw 的 exact execution legs 交回 Radar。未做這一步前，不得恢復下載。
- future_data_violation_count=0。

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false
"""
    (OUT / "final_summary_zh.md").write_text(final, encoding="utf-8")
    write_json(OUT / "local_reuse_audit_progress.json", {
        "task_id": TASK_ID, "status": "completed_waiting_strategy_center",
        "current_step": "completed_local_A_to_E_reclassification_network_disabled",
        "network_acquisition_enabled": False, "updated_at": now(),
    })
    (OUT / "current_step.txt").write_text("completed_local_A_to_E_reclassification_network_disabled\n", encoding="utf-8")
    checksum_files = [
        path for path in OUT.iterdir()
        if path.is_file() and not path.name.startswith(".")
        and path.name not in {"manifest.json", "local_reuse_audit_checksum_manifest.csv"}
    ]
    checksum_manifest = pd.DataFrame([
        {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(checksum_files)
    ])
    write_frame(OUT / "local_reuse_audit_checksum_manifest.csv", checksum_manifest)
    manifest_files = [
        path for path in OUT.iterdir()
        if path.is_file() and not path.name.startswith(".") and path.name != "manifest.json"
    ]
    write_json(OUT / "manifest.json", {
        "task_id": TASK_ID, "updated_at": now(), "network_acquisition_stopped": True,
        "artifacts": [
            {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in sorted(manifest_files)
        ],
        "future_data_violation_count": 0, **FLAGS,
    })
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
