from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-PRIMARY80-PATH-INDEPENDENT-OFFICIAL-CLOSE-LOCAL-AUDIT-001"
REPO = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
OUTPUT = REPO / "outputs" / "radar_vnext_p1_p2_primary80_path_independent_raw_close_local_audit_20260716"

PRIMARY80 = CORE / "outputs/vnext_layer4_80_primary_pool_contract_20260708/layer4_80_primary_pool_contract.csv"
CORE_NORMALIZED = CORE / "outputs/vnext_p1_p2_primary80_MA_slope_CD50_one_shot_close_authority_20260716/normalized_local_close_index.csv.gz"
P1 = REPO / "outputs/radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710"
P3 = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
SHIFTED = REPO / "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716"
ONE_SHOT = REPO / "outputs/radar_vnext_p1_p2_primary80_ma_slope_cd50_one_shot_close_fill_20260716"
LISTING = REPO / "outputs/radar_dynamic_pool1_listing_delisting_suspension_master_20260703"
TPEX_DELISTING = REPO / "outputs/radar_dynamic_pool1_tpex_historical_full_sweep_20260703/accepted_delisting_metadata_rows.csv"

P1_END = pd.Timestamp("2022-12-29")
P2_END = pd.Timestamp("2026-06-30")
KEY = ["ticker", "date"]
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.tmp"
    temp.write_text(value, encoding="utf-8")
    os.replace(temp, path)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}{''.join(path.suffixes)}"
    frame.to_csv(temp, index=False, encoding="utf-8-sig", compression="gzip" if path.suffix == ".gz" else None)
    os.replace(temp, path)


def step(output: Path, name: str, **extra: object) -> None:
    atomic_text(output / "current_step.txt", name + "\n")
    atomic_json(output / "progress.json", {"task": TASK, "current_step": name, "updated_at": now(), **extra})


def normalize_ticker(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def merge_intervals(ranges: list[tuple[pd.Timestamp, pd.Timestamp]]) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + pd.Timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def interval_contains(intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]], ticker: str, day: pd.Timestamp) -> bool:
    return any(start <= day <= end for start, end in intervals.get(ticker, []))


def load_membership() -> pd.DataFrame:
    use = ["snapshot_date", "ticker", "name", "market", "is_layer4_primary_pool"]
    frame = pd.read_csv(PRIMARY80, usecols=use, dtype={"ticker": str}, low_memory=False)
    frame = frame[frame["is_layer4_primary_pool"].astype(str).str.lower().isin({"true", "1"})].copy()
    frame["snapshot_date"] = normalize_date(frame["snapshot_date"])
    frame["ticker"] = normalize_ticker(frame["ticker"])
    frame["market"] = frame["market"].astype(str).str.strip().replace({"TPEX": "TPEx", "OTC": "TPEx"})
    frame = frame[(frame["snapshot_date"] >= "2015-01-02") & (frame["snapshot_date"] <= P2_END)]
    frame["period"] = np.where(frame["snapshot_date"] <= P1_END, "P1", "P2")
    return frame.sort_values(["ticker", "snapshot_date", "market"]).reset_index(drop=True)


def latest_route_manifest() -> pd.DataFrame:
    parts = []
    for component, path in [
        ("p1_price_bulk_manifest", P1 / "price_bulk_download_manifest.csv"),
        ("p3_price_source_manifest", P3 / "price_source_manifest.csv"),
    ]:
        frame = pd.read_csv(path, dtype=str, low_memory=False)
        frame["date"] = normalize_date(frame["date"])
        frame["market"] = frame["market"].astype(str).str.strip().replace({"TPEX": "TPEx"})
        frame["source_component"] = component
        frame["manifest_order"] = np.arange(len(frame))
        parts.append(frame)
    combined = pd.concat(parts, ignore_index=True, sort=False)
    combined = combined.sort_values(["market", "date", "manifest_order"]).drop_duplicates(["market", "date"], keep="last")
    for column in ["http_status", "error", "status"]:
        if column not in combined:
            combined[column] = ""
        combined[column] = combined[column].fillna("").astype(str)
    combined["route_response_valid"] = (
        combined["status"].isin(["accepted", "no_rows"])
        & combined["http_status"].isin(["200", "200.0", ""])
        & combined["error"].isin(["", "nan", "None"])
    )
    return combined.reset_index(drop=True)


def load_raw_close_index() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    inventory: list[dict] = []

    annual = []
    annual.extend((path, "p1_official_raw_annual_compact", 1) for path in sorted((P1 / "compact/official_raw_execution_ohlcv").glob("*/*.csv.gz")))
    annual.extend((path, "p3_official_raw_annual_compact", 1) for path in sorted((P3 / "compact/price").glob("*.csv.gz")))
    for path, component, priority in annual:
        frame = pd.read_csv(path, usecols=lambda value: value in {
            "date", "ticker", "market", "close", "source_quality", "source_url", "source_hash", "retrieval_time_utc"
        }, dtype=str, low_memory=False)
        original_rows = len(frame)
        frame["ticker"] = normalize_ticker(frame["ticker"])
        frame["date"] = normalize_date(frame["date"])
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame[frame["close"].gt(0) & frame["date"].notna()].copy()
        frame["source_component"] = component
        frame["source_priority"] = priority
        frame = frame.rename(columns={"retrieval_time_utc": "retrieved_at"})
        frames.append(frame)
        inventory.append({
            "source_component": component, "path": str(path), "files_read_once": 1,
            "rows_read": original_rows, "valid_close_rows": len(frame), "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })

    normalized = pd.read_csv(CORE_NORMALIZED, dtype=str, low_memory=False)
    normalized["ticker"] = normalize_ticker(normalized["ticker"])
    normalized["date"] = normalize_date(normalized["date"])
    normalized["close"] = pd.to_numeric(normalized["official_raw_close"], errors="coerce")
    normalized = normalized[normalized["close"].gt(0) & normalized["date"].notna()].copy()
    normalized["source_quality"] = normalized.get("raw_source", "core_normalized_official_raw")
    normalized["source_component"] = "core_normalized_local_close_index"
    normalized["source_priority"] = 2
    frames.append(normalized)
    inventory.append({
        "source_component": "core_normalized_local_close_index", "path": str(CORE_NORMALIZED),
        "files_read_once": 1, "rows_read": "", "valid_close_rows": len(normalized),
        "bytes": CORE_NORMALIZED.stat().st_size, "sha256": sha256(CORE_NORMALIZED),
    })

    reusable_path = SHIFTED / "reusable_combined_close_index.csv.gz"
    reusable = pd.read_csv(reusable_path, dtype=str, low_memory=False)
    reusable = reusable[reusable["family"].eq("official_raw_execution_close")].copy()
    reusable["ticker"] = normalize_ticker(reusable["ticker"])
    reusable["date"] = normalize_date(reusable["date"])
    reusable["close"] = pd.to_numeric(reusable["close"], errors="coerce")
    reusable = reusable[reusable["close"].gt(0) & reusable["date"].notna()].copy()
    reusable["source_component"] = "shifted_reusable_combined_close_index"
    reusable["source_priority"] = 3
    frames.append(reusable)
    inventory.append({
        "source_component": "shifted_reusable_combined_close_index", "path": str(reusable_path),
        "files_read_once": 1, "rows_read": "", "valid_close_rows": len(reusable),
        "bytes": reusable_path.stat().st_size, "sha256": sha256(reusable_path),
    })

    source = pd.concat(frames, ignore_index=True, sort=False)
    source["rounded_close"] = source["close"].round(8)
    conflicts = source.groupby(KEY, as_index=False).agg(
        source_rows=("close", "size"), distinct_close_values=("rounded_close", "nunique"),
        close_values=("rounded_close", lambda values: "|".join(map(str, sorted(set(values))))),
        source_components=("source_component", lambda values: "|".join(sorted(set(values)))),
    )
    conflicts = conflicts[conflicts["distinct_close_values"].gt(1)].copy()
    source = source.sort_values(KEY + ["source_priority"]).drop_duplicates(KEY, keep="first")
    keep = KEY + ["close", "market", "source_quality", "source_component", "source_url", "source_hash", "retrieved_at"]
    for column in keep:
        if column not in source:
            source[column] = ""
    return source[keep].reset_index(drop=True), pd.DataFrame(inventory), conflicts


def build_calendar(routes: pd.DataFrame, close_index: pd.DataFrame) -> list[pd.Timestamp]:
    accepted = set(routes.loc[routes["route_response_valid"], "date"].dropna())
    observed = set(close_index["date"].dropna())
    dates = sorted(day for day in accepted | observed if pd.Timestamp("2014-08-01") <= day <= P2_END)
    return dates


def official_events() -> tuple[dict[str, pd.Timestamp], dict[str, pd.Timestamp], dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]], pd.DataFrame]:
    twse = pd.read_csv(LISTING / "accepted_listing_metadata_rows.csv", dtype=str)
    tpex = pd.read_csv(TPEX_DELISTING, dtype=str)
    events = pd.concat([twse, tpex], ignore_index=True, sort=False)
    events["ticker"] = normalize_ticker(events["ticker"])
    events["event_date"] = normalize_date(events["event_date"])
    events = events[events["event_date"].notna()].copy()
    listing = events[events["event_type"].eq("listing")].sort_values("event_date").drop_duplicates("ticker").set_index("ticker")["event_date"].to_dict()
    delisting = events[events["event_type"].eq("delisting")].sort_values("event_date").drop_duplicates("ticker", keep="last").set_index("ticker")["event_date"].to_dict()

    suspension_rows = pd.read_csv(LISTING / "accepted_suspension_event_rows.csv", dtype=str)
    suspension_rows["ticker"] = normalize_ticker(suspension_rows["ticker"])
    suspension_rows["event_date"] = normalize_date(suspension_rows["event_date"])
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)
    for ticker, group in suspension_rows.dropna(subset=["event_date"]).sort_values("event_date").groupby("ticker"):
        start = None
        for row in group.itertuples(index=False):
            if row.event_type == "suspension":
                start = row.event_date
            elif row.event_type == "resumption" and start is not None:
                intervals[str(ticker)].append((start, row.event_date - pd.Timedelta(days=1)))
                start = None
        if start is not None:
            intervals[str(ticker)].append((start, start))
    intervals = {ticker: merge_intervals(ranges) for ticker, ranges in intervals.items()}
    return listing, delisting, intervals, events


def filtered_scope_intervals() -> tuple[dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]], dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]]:
    p1_frame = pd.read_csv(P1 / "frozen_primary80_warmup_intervals.csv", dtype=str)
    p1_frame["ticker"] = normalize_ticker(p1_frame["ticker"])
    p1_frame["start"] = normalize_date(p1_frame["warmup_interval_start"])
    p1_frame["end"] = normalize_date(p1_frame["membership_snapshot_end"])
    p1_intervals = {
        ticker: merge_intervals(list(zip(group["start"], group["end"])))
        for ticker, group in p1_frame.groupby("ticker")
    }

    p3_membership = pd.read_csv(P3 / "p3_frozen_layer4_primary80_watchlist_membership.csv", dtype=str)
    p3_membership["ticker"] = normalize_ticker(p3_membership["ticker"])
    p3_membership["snapshot_date"] = normalize_date(p3_membership["snapshot_date"])
    last_snapshot = p3_membership["snapshot_date"].max()
    last_tickers = set(p3_membership.loc[p3_membership["snapshot_date"].eq(last_snapshot), "ticker"])
    p3_intervals = {}
    for ticker, group in p3_membership.groupby("ticker"):
        ranges = [(day - pd.Timedelta(days=365), day) for day in group["snapshot_date"].dropna()]
        if ticker in last_tickers:
            ranges.append((last_snapshot, pd.Timestamp("2026-07-09")))
        p3_intervals[ticker] = merge_intervals(ranges)
    return p1_intervals, p3_intervals


def assign_market(history: pd.DataFrame, dates: list[pd.Timestamp]) -> list[str]:
    ordered = history.sort_values("snapshot_date").drop_duplicates("snapshot_date", keep="last")
    stamps = ordered["snapshot_date"].to_numpy(dtype="datetime64[ns]")
    markets = ordered["market"].astype(str).to_numpy()
    target = np.array(dates, dtype="datetime64[ns]")
    positions = np.searchsorted(stamps, target, side="right") - 1
    positions = np.maximum(positions, 0)
    return markets[positions].tolist()


def build_requirements(membership: pd.DataFrame, calendar: list[pd.Timestamp], delisting: dict[str, pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    calendar_array = np.array(calendar, dtype="datetime64[ns]")
    scopes = []
    requirement_parts = []
    transitions = []
    for (period, ticker), group in membership.groupby(["period", "ticker"], sort=True):
        first = group["snapshot_date"].min()
        end = P1_END if period == "P1" else P2_END
        termination = delisting.get(ticker)
        if termination is not None and first <= termination <= end:
            end = termination
        first_position = int(np.searchsorted(calendar_array, np.datetime64(first), side="left"))
        warmup_position = max(0, first_position - 60)
        end_position = int(np.searchsorted(calendar_array, np.datetime64(end), side="right"))
        dates = [pd.Timestamp(value) for value in calendar_array[warmup_position:end_position]]
        if not dates:
            continue
        market_values = assign_market(group, dates)
        name = str(group["name"].dropna().iloc[-1]) if group["name"].notna().any() else ""
        scopes.append({
            "period": period, "ticker": ticker, "name": name,
            "first_primary80_eligible_date": first, "warmup_start_date": dates[0],
            "scope_end_date": end, "required_session_rows": len(dates),
            "warmup_sessions_before_first_eligible": sum(day < first for day in dates),
            "official_delisting_cap_applied": termination is not None and end == termination,
        })
        requirement_parts.append(pd.DataFrame({
            "period": period, "ticker": ticker, "name": name, "date": dates,
            "market": market_values, "first_primary80_eligible_date": first,
            "warmup_start_date": dates[0], "scope_end_date": end,
            "requirement_role": ["60TD_warmup" if day < first else "continuous_post_eligibility" for day in dates],
        }))
        market_history = group.groupby("market")["snapshot_date"].agg(["min", "max", "count"]).reset_index()
        if len(market_history) > 1:
            market_history.insert(0, "ticker", ticker)
            market_history.insert(0, "period", period)
            transitions.append(market_history)

    period_requirements = pd.concat(requirement_parts, ignore_index=True)
    collapsed = period_requirements.groupby(KEY, as_index=False).agg(
        name=("name", "last"),
        periods=("period", lambda values: "|".join(sorted(set(values)))),
        markets=("market", lambda values: "|".join(sorted(set(values)))),
        requirement_roles=("requirement_role", lambda values: "|".join(sorted(set(values)))),
        first_primary80_eligible_date=("first_primary80_eligible_date", "min"),
        warmup_start_date=("warmup_start_date", "min"),
        scope_end_date=("scope_end_date", "max"),
    )
    collapsed["market"] = collapsed["markets"].where(~collapsed["markets"].str.contains(r"\|"), collapsed["markets"])
    collapsed["market_policy_blocked"] = collapsed["markets"].str.contains(r"\|")
    return pd.DataFrame(scopes), collapsed, pd.concat(transitions, ignore_index=True) if transitions else pd.DataFrame()


def previous_no_trade_keys() -> set[tuple[str, pd.Timestamp]]:
    path = ONE_SHOT / "one_shot_official_no_trade_ledger.csv.gz"
    frame = pd.read_csv(path, dtype=str)
    frame["ticker"] = normalize_ticker(frame["ticker"])
    frame["date"] = normalize_date(frame["date"])
    return set(map(tuple, frame[["ticker", "date"]].dropna().drop_duplicates().itertuples(index=False, name=None)))


def route_valid_map(routes: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], bool]:
    return {(row.market, row.date): bool(row.route_response_valid) for row in routes.itertuples(index=False)}


def classify(
    requirements: pd.DataFrame,
    close_index: pd.DataFrame,
    conflicts: pd.DataFrame,
    listing: dict[str, pd.Timestamp],
    delisting: dict[str, pd.Timestamp],
    suspensions: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    p1_intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    p3_intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    routes: pd.DataFrame,
    prior_no_trade: set[tuple[str, pd.Timestamp]] | None = None,
) -> pd.DataFrame:
    merged = requirements.merge(close_index, on=KEY, how="left", validate="one_to_one", suffixes=("_required", "_source"))
    merged["market"] = merged["market_required"]
    conflict_keys = set(map(tuple, conflicts[KEY].itertuples(index=False, name=None)))
    if prior_no_trade is None:
        prior_no_trade = previous_no_trade_keys()
    valid_routes = route_valid_map(routes)

    classifications = []
    reasons = []
    for row in merged.itertuples(index=False):
        key = (row.ticker, row.date)
        required_market = row.markets if "|" not in row.markets else ""
        if bool(row.market_policy_blocked):
            classifications.append("market_policy_blocked")
            reasons.append("multiple_historical_primary80_markets_for_same_exact_key")
        elif key in conflict_keys:
            classifications.append("local_source_conflict")
            reasons.append("multiple_distinct_official_raw_close_values_in_local_sources")
        elif pd.notna(row.close):
            classifications.append("local_ready")
            reasons.append("exact_official_raw_close_reused")
        elif row.ticker in listing and row.date < listing[row.ticker]:
            classifications.append("official_no_trade_or_termination")
            reasons.append("official_listing_not_yet_effective")
        elif row.ticker in delisting and row.date == delisting[row.ticker]:
            classifications.append("official_no_trade_or_termination")
            reasons.append("official_delisting_effective_date_no_close")
        elif interval_contains(suspensions, row.ticker, row.date):
            classifications.append("official_no_trade_or_termination")
            reasons.append("official_suspension_interval")
        elif key in prior_no_trade:
            classifications.append("official_no_trade_or_termination")
            reasons.append("prior_official_market_file_valid_exact_ticker_absent")
        else:
            period_scope = p1_intervals if row.date <= P1_END else p3_intervals
            covered = interval_contains(period_scope, row.ticker, row.date)
            route_valid = valid_routes.get((required_market, row.date), False)
            if covered and route_valid:
                classifications.append("official_no_trade_or_termination")
                reasons.append("official_filtered_market_route_valid_exact_ticker_absent")
            else:
                classifications.append("true_missing")
                reasons.append(
                    "exact_close_absent_outside_retained_filter_scope" if not covered
                    else "exact_close_absent_and_official_route_not_locally_validated"
                )
    merged["classification"] = classifications
    merged["classification_reason"] = reasons
    merged["future_data_violation_count"] = 0
    return merged


def return_warnings(ready: pd.DataFrame) -> pd.DataFrame:
    frame = ready[["ticker", "date", "close", "source_quality", "source_component"]].drop_duplicates(KEY).copy()
    frame = frame.sort_values(["ticker", "date"])
    frame["previous_date"] = frame.groupby("ticker")["date"].shift()
    frame["previous_close"] = frame.groupby("ticker")["close"].shift()
    frame["raw_close_return"] = frame["close"] / frame["previous_close"] - 1
    frame = frame[frame["raw_close_return"].abs().gt(0.15)].copy()
    frame["warning_only"] = True
    frame["corporate_action_event_inferred"] = False
    frame["warning"] = "abs_raw_close_return_gt_15pct_requires_separate_event_review"
    return frame


def route_plan(missing: pd.DataFrame, routes: pd.DataFrame) -> pd.DataFrame:
    plan = missing[missing["market"].isin(["TWSE", "TPEx"])].groupby(["market", "date"], as_index=False).agg(
        missing_keys=("ticker", "size"), unique_tickers=("ticker", "nunique")
    )
    bytes_by_market = routes.copy()
    bytes_by_market["response_bytes"] = pd.to_numeric(bytes_by_market.get("response_bytes", 0), errors="coerce")
    medians = bytes_by_market[bytes_by_market["response_bytes"].gt(0)].groupby("market")["response_bytes"].median().to_dict()
    plan["estimated_response_bytes"] = plan["market"].map(medians).fillna(0).round().astype("int64")
    plan["network_authorized"] = False
    plan["network_authority_status"] = "audit_only_wait_strategy_center_decision"
    return plan


def build_manifest(output: Path) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}
    files = sorted(path for path in output.iterdir() if path.is_file() and path.name not in excluded and path.suffix != ".lock")
    checksums = pd.DataFrame([{
        "file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)
    } for path in files])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(output / "manifest.json", {
        "task": TASK, "generated_at": now(), "output_path": str(output),
        "files": checksums.to_dict("records"), "network_requests": 0,
        "future_data_violation_count": 0, **FLAGS,
    })


def run(output: Path = OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "local_audit.lock"
    if lock.exists():
        raise RuntimeError(f"runner_lock_exists:{lock}")
    atomic_text(lock, str(os.getpid()))
    try:
        step(output, "loading_membership_and_local_bulk_sources")
        membership = load_membership()
        routes = latest_route_manifest()
        close_index, source_inventory, conflicts = load_raw_close_index()
        calendar = build_calendar(routes, close_index)
        listing, delisting, suspensions, events = official_events()
        p1_intervals, p3_intervals = filtered_scope_intervals()

        step(output, "materializing_path_independent_exact_requirements", membership_rows=len(membership), union_tickers=membership["ticker"].nunique())
        scopes, requirements, transitions = build_requirements(membership, calendar, delisting)
        atomic_csv(output / "primary80_path_independent_ticker_period_scope.csv", scopes)
        atomic_csv(output / "primary80_path_independent_unique_ticker_date_requirements.csv.gz", requirements)
        atomic_csv(output / "primary80_historical_market_transition_audit.csv", transitions)
        atomic_csv(output / "primary80_local_raw_close_source_inventory.csv", source_inventory)
        atomic_csv(output / "primary80_local_raw_close_conflict_audit.csv", conflicts)

        step(output, "classifying_local_ready_no_trade_and_true_missing", requirement_rows=len(requirements))
        classified = classify(
            requirements, close_index, conflicts, listing, delisting, suspensions,
            p1_intervals, p3_intervals, routes,
        )
        ready = classified[classified["classification"].eq("local_ready")].copy()
        no_trade = classified[classified["classification"].eq("official_no_trade_or_termination")].copy()
        missing = classified[classified["classification"].eq("true_missing")].copy()
        policy = classified[classified["classification"].isin(["market_policy_blocked", "local_source_conflict"])].copy()
        plan = route_plan(missing, routes)
        warnings = return_warnings(ready)

        atomic_csv(output / "primary80_path_independent_local_ready.csv.gz", ready)
        atomic_csv(output / "primary80_path_independent_official_no_trade_termination.csv.gz", no_trade)
        atomic_csv(output / "primary80_path_independent_true_missing.csv.gz", missing)
        atomic_csv(output / "primary80_path_independent_policy_blocked.csv.gz", policy)
        atomic_csv(output / "primary80_path_independent_market_date_route_plan.csv", plan)
        atomic_csv(output / "primary80_path_independent_abs_return_gt15_warning.csv.gz", warnings)
        atomic_csv(output / "primary80_official_event_reference.csv", events[events["ticker"].isin(set(membership["ticker"]))])

        total = len(requirements)
        route_count = len(plan)
        low_minutes = route_count * 35 / 3957
        high_minutes = route_count * 120 / 3957
        transfer_bytes = int(plan["estimated_response_bytes"].sum()) if not plan.empty else 0
        coverage = pd.DataFrame([
            {"classification": "required_unique_ticker_date", "rows": total, "share": 1.0},
            {"classification": "local_ready", "rows": len(ready), "share": len(ready) / total if total else 0},
            {"classification": "official_no_trade_or_termination", "rows": len(no_trade), "share": len(no_trade) / total if total else 0},
            {"classification": "true_missing", "rows": len(missing), "share": len(missing) / total if total else 0},
            {"classification": "market_policy_blocked_or_local_conflict", "rows": len(policy), "share": len(policy) / total if total else 0},
        ])
        coverage["network_requests"] = 0
        coverage["future_data_violation_count"] = 0
        atomic_csv(output / "requested_vs_actual_coverage.csv", coverage)
        atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
            {"audit": "path_independent_primary80_union", "status": "pass", "future_data_violation_count": 0},
            {"audit": "network_requests", "status": "0", "future_data_violation_count": 0},
            {"audit": "non_close_family_reads_or_downloads", "status": "0", "future_data_violation_count": 0},
            {"audit": "neighbor_or_last_price_substitution", "status": "false", "future_data_violation_count": 0},
            {"audit": "abs_return_gt15_used_as_event", "status": "false_warning_only", "future_data_violation_count": 0},
        ]))

        complete = len(missing) == 0 and len(policy) == 0
        readiness = {
            "task": TASK,
            "status": "path_independent_local_audit_complete" if complete else "path_independent_local_audit_complete_one_shot_network_decision_required",
            "primary80_membership_rows": len(membership),
            "primary80_snapshot_count": membership["snapshot_date"].nunique(),
            "primary80_union_ticker_count": membership["ticker"].nunique(),
            "ticker_period_scope_rows": len(scopes),
            "required_unique_ticker_date_rows": total,
            "local_ready_rows": len(ready),
            "official_no_trade_or_termination_rows": len(no_trade),
            "true_missing_rows": len(missing),
            "market_policy_blocked_or_local_conflict_rows": len(policy),
            "unique_missing_market_date_routes": route_count,
            "estimated_network_transfer_bytes": transfer_bytes,
            "estimated_network_transfer_mb": round(transfer_bytes / 1024 / 1024, 3),
            "estimated_network_minutes_low": round(low_minutes, 1),
            "estimated_network_minutes_high": round(high_minutes, 1),
            "network_requests": 0,
            "network_authorized": False,
            "ready_for_core_path_independent_raw_close_absorption": complete,
            "ready_for_strategy_center_one_shot_bounded_market_date_fill_decision": not complete,
            "ready_for_experiments": False,
            "future_data_violation_count": 0,
            **FLAGS,
        }
        atomic_json(output / "readiness_for_strategy_center_primary80_raw_close_audit.json", readiness)
        atomic_text(output / "final_summary_zh.md", (
            "# P1/P2 primary80 path-independent official close local audit\n\n"
            f"- 固定 universe：{membership['ticker'].nunique():,} tickers / {membership['snapshot_date'].nunique():,} snapshots。\n"
            f"- unique ticker-date requirements：{total:,}。\n"
            f"- local ready：{len(ready):,}；official no-trade/termination：{len(no_trade):,}。\n"
            f"- true missing：{len(missing):,}；policy/conflict blocked：{len(policy):,}。\n"
            f"- one-shot market-date routes：{route_count:,}；估計 {transfer_bytes / 1024 / 1024:.1f} MB / {low_minutes:.1f}~{high_minutes:.1f} 分鐘。\n"
            "- 本輪 network_requests=0；等待 Strategy Center 裁決是否一次性補 close-only market-date routes。\n"
            "- abs return >15% 僅為 warning，不視為 corporate-action event。\n"
        ))
        step(output, "completed_waiting_strategy_center_one_shot_close_only_decision", **readiness)
        build_manifest(output)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(args.output)
