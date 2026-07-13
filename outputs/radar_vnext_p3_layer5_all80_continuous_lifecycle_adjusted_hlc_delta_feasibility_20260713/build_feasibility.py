import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER5-ALL80-CONTINUOUS-LIFECYCLE-ADJUSTED-HLC-DELTA-FEASIBILITY-001"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p3_layer5_all80_continuous_sequential_lifecycle_state_supply_contract_20260713")
ROOT = OUT.parents[0]
P3 = ROOT / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
WARMUP = ROOT / "radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711"
RANK1 = ROOT / "radar_vnext_p3_layer04_rank1_sequential_lifecycle_adjusted_hlc_factor_source_package_20260713"
CURRENT = ROOT / "radar_vnext_p3_ridge_shadow_current_layer1_4_bounded_delta_fill_20260712"
ROW_STOP_GATE = 100_000
ROUTE_STOP_GATE = 5_000

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
GOVERNANCE = {
    "diagnostic_subproblem": False,
    "represents_intended_all80_layer5_state_supply": True,
    "performance_authorized": False,
    "P3_2_outcome_read_authorized": False,
    "Top3_authorized": False,
}


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path, rows, fields=None):
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False, encoding="utf-8-sig", compression="gzip" if str(path).endswith(".gz") else None)
        return
    fields = fields or (list(rows[0]) if rows else ["empty"])
    opener = gzip.open if str(path).endswith(".gz") else open
    kwargs = {"mode": "wt", "encoding": "utf-8-sig", "newline": ""} if str(path).endswith(".gz") else {"mode": "w", "encoding": "utf-8-sig", "newline": ""}
    with opener(path, **kwargs) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_frames(paths, tickers, columns):
    frames = []
    for path in paths:
        if not path.exists():
            continue
        available = pd.read_csv(path, nrows=0).columns
        use = [column for column in columns if column in available]
        frame = pd.read_csv(path, dtype={"ticker": str}, usecols=use)
        frame["ticker"] = frame["ticker"].str.zfill(4)
        frame = frame[frame["ticker"].isin(tickers)]
        if len(frame):
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ticker", "date"])


def key_series(frame):
    return frame["ticker"].astype(str) + "|" + frame["date"].astype(str)


def main():
    CURRENT_STEP.write_text("load_core_gap_ledger", encoding="utf-8")
    gap_path = CORE / "p3_all80_continuous_adjusted_HLC_gap_ledger.csv.gz"
    requirement_path = CORE / "p3_all80_continuous_adjusted_HLC_requirement_ledger.csv.gz"
    gap = pd.read_csv(gap_path, dtype={"ticker": str})
    gap["ticker"] = gap["ticker"].str.zfill(4)
    gap["key"] = key_series(gap)
    gap["year_month"] = gap["date"].str[:7]
    tickers = set(gap["ticker"])

    CURRENT_STEP.write_text("load_local_reusable_sources", encoding="utf-8")
    raw_paths = sorted((P3 / "compact" / "price").glob("*.csv.gz")) + sorted((WARMUP / "compact" / "raw_hlc_warmup").glob("*.csv.gz"))
    factor_paths = sorted((P3 / "compact" / "adjusted").glob("*.csv.gz"))
    direct_paths = [
        RANK1 / "rank1_adjusted_analysis_hlc_factor_compact.csv.gz",
        CURRENT / "ridge_shadow_current_adjusted_analysis_ohlc_factor_rows.csv.gz",
    ]
    raw = load_frames(raw_paths, tickers, ["ticker", "date", "name", "market", "open", "high", "low", "close", "source_quality", "source_url", "source_hash"])
    raw = raw.dropna(subset=["open", "high", "low", "close"]).drop_duplicates(["ticker", "date"], keep="last")
    factor = load_frames(factor_paths, tickers, ["ticker", "date", "name", "market", "adjusted_close", "raw_close_comparator", "source_quality", "source_url", "source_hash"])
    factor["adjustment_factor"] = pd.to_numeric(factor["adjusted_close"], errors="coerce") / pd.to_numeric(factor["raw_close_comparator"], errors="coerce")
    factor = factor[factor["adjustment_factor"].gt(0)].drop_duplicates(["ticker", "date"], keep="last")
    direct = load_frames(direct_paths, tickers, ["ticker", "date", "name", "market", "adjusted_high", "adjusted_low", "adjusted_close", "adjustment_factor", "adjusted_source_quality", "source_url", "source_hash"])
    direct = direct.dropna(subset=["adjusted_high", "adjusted_low", "adjusted_close"]).drop_duplicates(["ticker", "date"], keep="last")

    raw_keys = set(key_series(raw))
    factor_keys = set(key_series(factor))
    direct_keys = set(key_series(direct))
    gap["local_raw_HLC_ready"] = gap["key"].isin(raw_keys)
    gap["local_factor_ready"] = gap["key"].isin(factor_keys)
    gap["local_direct_adjusted_HLC_ready"] = gap["key"].isin(direct_keys)
    gap["reconstructable_after_local_reuse"] = gap["local_direct_adjusted_HLC_ready"] | (gap["local_raw_HLC_ready"] & gap["local_factor_ready"])

    proven_no_rows_path = WARMUP / "p3_exact_primary80_raw_hlc_warmup_blocked_ledger.csv"
    proven_no_rows = pd.read_csv(proven_no_rows_path, dtype={"ticker": str})
    proven_no_rows["ticker"] = proven_no_rows["ticker"].str.zfill(4)
    proven_no_rows["key"] = key_series(proven_no_rows)
    proven_no_rows_keys = set(proven_no_rows.loc[proven_no_rows["classification"] == "official_zero_or_not_applicable", "key"])
    gap["official_no_row_proven"] = gap["key"].isin(proven_no_rows_keys)

    raw_ranges = raw.groupby("ticker")["date"].agg(["min", "max"]).to_dict("index")
    factor_ranges = factor.groupby("ticker")["date"].agg(["min", "max"]).to_dict("index")
    factor_tickers = set(factor["ticker"])

    def classify(row):
        if row["reconstructable_after_local_reuse"]:
            return "reconstructable_from_local_reuse"
        if row["official_no_row_proven"]:
            return "official_zero_or_not_applicable_proven"
        raw_ready, factor_ready = row["local_raw_HLC_ready"], row["local_factor_ready"]
        if not factor_ready and row["ticker"] not in factor_tickers:
            return "symbol_or_source_structural_factor_blocked"
        if raw_ready and not factor_ready:
            return "factor_true_gap"
        if not raw_ready and factor_ready:
            return "raw_true_gap"
        if not raw_ready and not factor_ready:
            date = row["date"]
            raw_min = raw_ranges.get(row["ticker"], {}).get("min", "")
            factor_min = factor_ranges.get(row["ticker"], {}).get("min", "")
            if (raw_min and date < raw_min) or (factor_min and date < factor_min):
                return "pre_listing_or_short_history_candidate_review"
            return "raw_and_factor_true_gap"
        return "unclassified_blocked"

    gap["classification"] = gap.apply(classify, axis=1)
    gap["raw_used_as_adjusted"] = False
    gap["silent_fill_used"] = False
    gap["corporate_action_factor_policy"] = "trusted factor remains research diagnostic; event ambiguity requires human review"
    gap["future_data_violation_count"] = 0
    for key, value in GOVERNANCE.items(): gap[key] = value
    for key, value in FLAGS.items(): gap[key] = value
    write_csv(OUT / "all80_adjusted_hlc_gap_reuse_classification.csv.gz", gap.drop(columns=["key"]))
    sample = pd.concat([group.head(3) for _, group in gap.groupby("classification")], ignore_index=True)
    sample.drop(columns=["key"]).to_csv(OUT / "all80_adjusted_hlc_gap_classification_sample.csv", index=False, encoding="utf-8-sig")

    CURRENT_STEP.write_text("build_routes_and_cost_estimate", encoding="utf-8")
    unresolved = gap[~gap["reconstructable_after_local_reuse"] & ~gap["official_no_row_proven"]].copy()
    meta_parts = []
    for frame in (raw, factor, direct):
        if len(frame) and "market" in frame.columns:
            meta_parts.append(frame[[column for column in ("ticker", "name", "market") if column in frame.columns]])
    meta = pd.concat(meta_parts, ignore_index=True).dropna(subset=["ticker"]).drop_duplicates("ticker", keep="last") if meta_parts else pd.DataFrame(columns=["ticker", "name", "market"])
    unresolved = unresolved.merge(meta, on="ticker", how="left", suffixes=("", "_meta"))
    route_rows = []
    for (ticker, month), group in unresolved.groupby(["ticker", "year_month"]):
        classes = set(group["classification"])
        need_raw = bool(classes & {"raw_true_gap", "raw_and_factor_true_gap", "pre_listing_or_short_history_candidate_review", "symbol_or_source_structural_factor_blocked"}) and bool((~group["local_raw_HLC_ready"]).any())
        need_factor = bool((~group["local_factor_ready"]).any())
        market = next((str(value) for value in group.get("market", pd.Series(dtype=str)).dropna() if str(value)), "")
        route_rows.append({
            "ticker": ticker, "market": market, "year_month": month, "required_gap_rows": len(group),
            "raw_gap_rows": int((~group["local_raw_HLC_ready"]).sum()), "factor_gap_rows": int((~group["local_factor_ready"]).sum()),
            "need_official_selected_ticker_month_route": need_raw,
            "official_raw_route": "TWSE STOCK_DAY selected month" if market == "TWSE" else "TPEx tradingStock selected month" if market == "TPEx" else "market_mapping_review_required",
            "need_trusted_adjusted_ticker_route": need_factor,
            "trusted_factor_route": "Yahoo chart one bounded ticker request; no raw-as-adjusted" if need_factor else "reuse_ready",
            "classification_set": "|".join(sorted(classes)), "download_executed": False,
            "future_data_violation_count": 0, **GOVERNANCE, **FLAGS,
        })
    routes = pd.DataFrame(route_rows).sort_values(["ticker", "year_month"])
    routes.to_csv(OUT / "all80_adjusted_hlc_unique_ticker_month_routes.csv", index=False, encoding="utf-8-sig")

    summary_rows = []
    for classification, group in gap.groupby("classification"):
        summary_rows.append({
            "classification": classification, "gap_rows": len(group), "unique_tickers": group["ticker"].nunique(),
            "unique_ticker_months": group[["ticker", "year_month"]].drop_duplicates().shape[0],
            "requires_new_download": classification not in {"reconstructable_from_local_reuse", "official_zero_or_not_applicable_proven"},
            **GOVERNANCE, **FLAGS,
        })
    write_csv(OUT / "all80_adjusted_hlc_gap_classification_summary.csv", summary_rows)

    true_new_rows = len(unresolved)
    proven_no_rows_total = int(gap["official_no_row_proven"].sum())
    proven_no_rows_exclusive = int((gap["classification"] == "official_zero_or_not_applicable_proven").sum())
    route_count = len(routes)
    factor_ticker_routes = unresolved.loc[~unresolved["local_factor_ready"], "ticker"].nunique()
    raw_route_count = int(routes["need_official_selected_ticker_month_route"].sum()) if len(routes) else 0
    projected_transfer_mb = round(raw_route_count * 0.060 + factor_ticker_routes * 0.300, 3)
    projected_compact_mb = round(true_new_rows * 260 / 1_000_000, 3)
    estimated_runtime_minutes = round(raw_route_count * 0.45 / 60 + factor_ticker_routes * 1.2 / 60, 2)
    cost = [{
        "input_gap_rows": len(gap), "locally_reconstructable_rows": int(gap["reconstructable_after_local_reuse"].sum()),
        "official_zero_or_not_applicable_proven_rows": proven_no_rows_exclusive,
        "official_zero_or_not_applicable_evidence_rows_total": proven_no_rows_total,
        "projected_new_rows": true_new_rows, "unique_ticker_month_routes": route_count,
        "official_raw_month_routes": raw_route_count, "trusted_adjusted_ticker_routes": factor_ticker_routes,
        "projected_transfer_mb": projected_transfer_mb, "projected_compact_mb": projected_compact_mb,
        "estimated_runtime_minutes_sequential_with_retries": estimated_runtime_minutes,
        "row_stop_gate": ROW_STOP_GATE, "route_stop_gate": ROUTE_STOP_GATE,
        "row_budget_pass": true_new_rows <= ROW_STOP_GATE, "route_budget_pass": route_count <= ROUTE_STOP_GATE,
        "download_executed": False, "estimate_basis": "60KB/official ticker-month, 300KB/trusted ticker chart, 0.45s/official route, 1.2s/trusted route",
        **GOVERNANCE, **FLAGS,
    }]
    write_csv(OUT / "all80_adjusted_hlc_route_cost_estimate.csv", cost)

    structural = unresolved[unresolved["classification"].isin(["symbol_or_source_structural_factor_blocked", "pre_listing_or_short_history_candidate_review"])].groupby(["ticker", "classification"]).agg(
        blocked_rows=("date", "size"), start_date=("date", "min"), end_date=("date", "max"), ticker_months=("year_month", "nunique")
    ).reset_index()
    structural["blocked_reason"] = structural["classification"].map({
        "symbol_or_source_structural_factor_blocked": "no trusted adjusted factor series exists for ticker; no successor/current symbol substitution",
        "pre_listing_or_short_history_candidate_review": "required date precedes observed local raw/factor history; official listing/no-row proof required before NA",
    })
    structural["raw_used_as_adjusted"] = False
    structural["future_data_violation_count"] = 0
    for key, value in GOVERNANCE.items(): structural[key] = value
    for key, value in FLAGS.items(): structural[key] = value
    structural.to_csv(OUT / "all80_adjusted_hlc_structural_blocker_ledger.csv", index=False, encoding="utf-8-sig")

    source_manifest = []
    source_groups = {
        "core_gap_ledger": [gap_path, requirement_path],
        "p3_official_raw_compact": raw_paths,
        "p3_trusted_adjusted_factor": factor_paths,
        "bounded_direct_adjusted_hlc": direct_paths,
        "official_no_row_evidence": [proven_no_rows_path],
    }
    for family, paths in source_groups.items():
        for path in paths:
            source_manifest.append({
                "family": family, "source_path": str(path), "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0, "sha256": sha256_file(path) if path.exists() else "",
                "role": "reuse_feasibility_only_no_new_download", **GOVERNANCE, **FLAGS,
            })
    write_csv(OUT / "all80_adjusted_hlc_reuse_source_manifest.csv", source_manifest)
    write_csv(OUT / "all80_adjusted_hlc_future_data_audit.csv", [{
        "check": "exact_key_reuse_only", "status": "pass", "violation_count": 0,
        "notes": "No current/static backfill, future outcome, P3-2 outcome, neighbor substitution, raw-as-adjusted, state, NAV, or performance read.",
        **GOVERNANCE, **FLAGS,
    }])

    stop_gate_pass = true_new_rows <= ROW_STOP_GATE and route_count <= ROUTE_STOP_GATE
    readiness = {
        "task_id": TASK_ID,
        "status": "all80_adjusted_hlc_delta_feasibility_ready_below_stop_gate_no_download_executed" if stop_gate_pass else "blocked_above_bounded_download_stop_gate_strategy_authorization_required",
        "source": "exact-key local compact/cache reuse audit against Core all80 gap ledger",
        "coverage": {
            "input_gap_rows": len(gap), "input_gap_tickers": gap["ticker"].nunique(),
            "locally_reconstructable_rows": int(gap["reconstructable_after_local_reuse"].sum()),
            "locally_reconstructable_share": round(float(gap["reconstructable_after_local_reuse"].mean()), 10),
            "official_zero_or_not_applicable_proven_rows": proven_no_rows_exclusive,
            "official_zero_or_not_applicable_evidence_rows_total": proven_no_rows_total,
            "remaining_rows_requiring_source_or_policy": true_new_rows,
            "unique_ticker_month_routes": route_count, "raw_month_routes": raw_route_count,
            "trusted_factor_ticker_routes": factor_ticker_routes,
        },
        "future_data_violation_count": 0,
        "bounded_stop_gate_pass": stop_gate_pass,
        "download_executed": False,
        "ready_for_bounded_delta_acquisition_planning": stop_gate_pass,
        "ready_for_core_all80_adjusted_hlc_delta_planning_absorption": True,
        "ready_for_core_rerun": False,
        "ready_for_experiments": False,
        **GOVERNANCE, **FLAGS,
    }
    write_json(OUT / "readiness_for_core_all80_adjusted_hlc_delta_feasibility.json", readiness)
    CURRENT_STEP.write_text("completed_feasibility_below_stop_gate_no_download" if stop_gate_pass else "completed_blocked_above_stop_gate", encoding="utf-8")
    write_json(OUT / "checkpoint.json", {"task_id": TASK_ID, "current_step": CURRENT_STEP.read_text(encoding="utf-8"), "resume_command": "python -X utf8 build_feasibility.py", "updated_at": now()})

    summary = f"""# P3 all80 continuous lifecycle adjusted-HLC delta feasibility

- Core gap: {len(gap):,} rows / {gap['ticker'].nunique()} tickers。
- Local exact-key reuse reconstructable: {int(gap['reconstructable_after_local_reuse'].sum()):,} rows ({gap['reconstructable_after_local_reuse'].mean():.2%})。
- Official no-row/not-applicable exclusive unresolved proof: {proven_no_rows_exclusive:,} rows；total evidence hits {proven_no_rows_total:,}（其中可與local reconstructable重疊）。
- Remaining source/policy rows: {true_new_rows:,}。
- Unique ticker-month routes: {route_count:,}；raw routes {raw_route_count:,}；trusted factor ticker routes {factor_ticker_routes}。
- Estimated transfer: {projected_transfer_mb} MB；compact {projected_compact_mb} MB；sequential runtime約 {estimated_runtime_minutes} minutes。
- Stop gate: {'PASS' if stop_gate_pass else 'BLOCKED'}（rows <= {ROW_STOP_GATE:,}、routes <= {ROUTE_STOP_GATE:,}）。
- 本輪未下載；只交 Core/Strategy 決定 bounded delta acquisition。
- adjusted analysis與official raw execution分欄；future_data_violation_count=0。
- 此包代表 intended all80 Layer5 state supply，但未授權state/performance/P3-2 outcome/Top3。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    artifacts = []
    for path in sorted(OUT.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_json(OUT / "manifest.json", {"task_id": TASK_ID, "generated_at": now(), "artifacts": artifacts, "readiness": readiness, **GOVERNANCE, **FLAGS})


if __name__ == "__main__":
    main()
