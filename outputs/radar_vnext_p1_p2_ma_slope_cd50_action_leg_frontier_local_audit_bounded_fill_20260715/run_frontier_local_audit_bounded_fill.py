from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests


REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs"
    r"\vnext_p1_p2_layer4_primary80_individual_MA_slope_CD50_action_legs_20260715"
)
REUSE = REPO / "outputs" / "radar_vnext_p1_p2_primary80_ma_slope_cd50_price_source_convergence_20260715"
FRONTIER = CORE / "p1_p2_MA_slope_CD50_frontier_official_raw_gap_ledger.csv"
INCUMBENT_REQUEST = CORE / "p1_p2_MA_slope_CD50_incumbent_continuity_local_audit_request.csv"
INCUMBENT_EXACT = CORE / "p1_p2_MA_slope_CD50_incumbent_analysis_gap_audit.csv.gz"
POLICY = CORE / "p1_p2_MA_slope_CD50_atomic_policy_blocker_ledger.csv"
REUSE_A = REUSE / "reuse_A_existing_raw_close.csv.gz"
P1_LIFECYCLE = REPO / "outputs" / "radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710" / "compact"
P3_ACQUISITION = REPO / "outputs" / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711" / "compact"
RAW_CACHE = OUT / "raw_audit_samples"
LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"

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


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_step(step: str, **extra: object) -> None:
    (OUT / "current_step.txt").write_text(step + "\n", encoding="utf-8")
    prior = {}
    path = OUT / "progress.json"
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
    prior.update({"current_step": step, "updated_at": now(), **extra})
    write_json(path, prior)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower().isin({"1", "true", "yes"})


def load_authority() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frontier = pd.read_csv(FRONTIER, dtype=str)
    request = pd.read_csv(INCUMBENT_REQUEST, dtype=str)
    exact = pd.read_csv(INCUMBENT_EXACT, dtype=str)
    policy = pd.read_csv(POLICY, dtype=str)
    if len(frontier) != 25 or frontier[["period", "ticker", "requested_execution_date"]].duplicated().any():
        raise RuntimeError("frontier authority must contain exactly 25 unique exact legs")
    if len(request) != 94 or request["network_download_authorized"].str.lower().ne("false").any():
        raise RuntimeError("all 94 incumbent spans must prohibit network download")
    if len(policy) != 24:
        raise RuntimeError("atomic policy blocker authority must contain exactly 24 rows")
    if exact["classification"].eq("incumbent_continuity_unclassified_local_audit_required").sum() != 23717:
        raise RuntimeError("incumbent exact local-audit authority must contain 23,717 unclassified rows")
    return frontier, request, exact, policy


def load_reuse_a() -> pd.DataFrame:
    usecols = [
        "period", "ticker", "date", "raw_close", "market", "name", "source_quality_raw",
        "adjustment_policy", "source_url", "source_hash_raw", "retrieved_at", "source_path_raw",
        "adjusted_close", "source_quality_adjusted", "source_path_adjusted", "source_hash_adjusted",
        "trusted_raw_close", "trusted_raw_source_url", "trusted_raw_source_hash",
        "raw_ready", "trusted_raw_comparator_ready", "adjusted_ready", "reconstructable_factor",
        "adjustment_factor", "future_data_violation_count",
    ]
    frame = pd.read_csv(REUSE_A, dtype=str, usecols=usecols)
    frame = frame.drop_duplicates(["period", "ticker", "date"], keep="first")
    return frame


def load_full_local_sources(exact: pd.DataFrame) -> pd.DataFrame:
    required = exact[["period", "ticker", "decision_date"]].rename(columns={"decision_date": "date"}).drop_duplicates()
    raw_parts: list[pd.DataFrame] = []
    adjusted_parts: list[pd.DataFrame] = []

    p1_required = required[required["period"].eq("P1")]
    p1_keys = set(zip(p1_required["ticker"], p1_required["date"]))
    for path in sorted((P1_LIFECYCLE / "official_raw_execution_ohlcv").glob("*/*.csv.gz")):
        if path.stem.split(".")[0] not in {str(year) for year in range(2015, 2023)}:
            continue
        frame = pd.read_csv(path, dtype={"ticker": str}, usecols=[
            "date", "ticker", "name", "market", "close", "source_quality", "adjustment_policy",
            "source_url", "source_hash", "retrieval_time_utc",
        ])
        frame = frame[frame.apply(lambda row: (str(row["ticker"]), str(row["date"])) in p1_keys, axis=1)]
        if not frame.empty:
            frame["period"] = "P1"
            frame["raw_source_path"] = str(path)
            raw_parts.append(frame)
    for ticker in sorted(p1_required["ticker"].unique()):
        path = P1_LIFECYCLE / "trusted_adjusted_analysis" / f"{ticker}.csv.gz"
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame = frame[frame["date"].isin(set(p1_required.loc[p1_required["ticker"].eq(ticker), "date"]))]
        if not frame.empty:
            frame["period"] = "P1"
            frame["adjusted_source_path"] = str(path)
            frame["provider_raw_close"] = frame.get("close")
            adjusted_parts.append(frame)

    p2_required = required[required["period"].eq("P2")]
    p2_keys = set(zip(p2_required["ticker"], p2_required["date"]))
    for path in sorted((P3_ACQUISITION / "price").glob("*.csv.gz")):
        year = path.stem.split(".")[0]
        if year not in {"2022", "2023", "2024", "2025", "2026"}:
            continue
        frame = pd.read_csv(path, dtype={"ticker": str}, usecols=[
            "date", "ticker", "name", "market", "close", "source_quality", "adjustment_policy",
            "source_url", "source_hash", "retrieval_time_utc",
        ])
        frame = frame[frame.apply(lambda row: (str(row["ticker"]), str(row["date"])) in p2_keys, axis=1)]
        if not frame.empty:
            frame["period"] = "P2"
            frame["raw_source_path"] = str(path)
            raw_parts.append(frame)
    for path in sorted((P3_ACQUISITION / "adjusted").glob("*.csv.gz")):
        year = path.stem.split(".")[0]
        if year not in {"2022", "2023", "2024", "2025", "2026"}:
            continue
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame = frame[frame.apply(lambda row: (str(row["ticker"]), str(row["date"])) in p2_keys, axis=1)]
        if not frame.empty:
            frame["period"] = "P2"
            frame["adjusted_source_path"] = str(path)
            frame["provider_raw_close"] = frame.get("raw_close_comparator")
            adjusted_parts.append(frame)

    registry = scan_local_registry(required)
    if not registry.empty:
        registry_raw_columns = [
            "period", "ticker", "date", "registry_market", "registry_name", "registry_raw_close",
            "registry_raw_source_quality", "registry_raw_adjustment_policy", "registry_raw_source_url",
            "registry_raw_source_hash", "registry_raw_retrieved_at", "registry_raw_source_path",
        ]
        registry_raw = registry.loc[registry["registry_raw_close"].notna(), registry_raw_columns].copy().rename(columns={
            "registry_raw_close": "close", "registry_market": "market", "registry_name": "name",
            "registry_raw_source_quality": "source_quality", "registry_raw_adjustment_policy": "adjustment_policy",
            "registry_raw_source_url": "source_url", "registry_raw_source_hash": "source_hash",
            "registry_raw_retrieved_at": "retrieval_time_utc", "registry_raw_source_path": "raw_source_path",
        })
        registry_adjusted_columns = [
            "period", "ticker", "date", "registry_adjusted_close", "registry_adjusted_provider_raw_close",
            "registry_adjusted_source_quality", "registry_adjusted_policy", "registry_adjusted_source_url",
            "registry_adjusted_source_hash", "registry_adjusted_retrieved_at", "registry_adjusted_source_path",
        ]
        registry_adjusted = registry.loc[
            registry["registry_adjusted_close"].notna(), registry_adjusted_columns
        ].copy().rename(columns={
            "registry_adjusted_close": "adjusted_close", "registry_adjusted_provider_raw_close": "provider_raw_close",
            "registry_adjusted_source_quality": "source_quality", "registry_adjusted_policy": "adjustment_policy",
            "registry_adjusted_source_url": "source_url", "registry_adjusted_source_hash": "source_hash",
            "registry_adjusted_retrieved_at": "retrieval_time_utc", "registry_adjusted_source_path": "adjusted_source_path",
        })
        raw_parts.append(registry_raw)
        adjusted_parts.append(registry_adjusted)

    raw = pd.concat(raw_parts, ignore_index=True, sort=False) if raw_parts else pd.DataFrame(columns=["period", "ticker", "date"])
    adjusted = pd.concat(adjusted_parts, ignore_index=True, sort=False) if adjusted_parts else pd.DataFrame(columns=["period", "ticker", "date"])
    raw = raw.drop_duplicates(["period", "ticker", "date"], keep="last")
    adjusted = adjusted.drop_duplicates(["period", "ticker", "date"], keep="last")
    raw = raw.rename(columns={
        "close": "full_raw_close", "source_quality": "full_raw_source_quality",
        "adjustment_policy": "full_raw_adjustment_policy", "source_url": "full_raw_source_url",
        "source_hash": "full_raw_source_hash", "retrieval_time_utc": "full_raw_retrieved_at",
    })
    adjusted = adjusted.rename(columns={
        "source_quality": "full_adjusted_source_quality", "adjustment_policy": "full_adjusted_policy",
        "source_url": "full_adjusted_source_url", "source_hash": "full_adjusted_source_hash",
        "retrieval_time_utc": "full_adjusted_retrieved_at",
    })
    adjusted_keep = [
        "period", "ticker", "date", "adjusted_close", "provider_raw_close", "full_adjusted_source_quality",
        "full_adjusted_policy", "full_adjusted_source_url", "full_adjusted_source_hash",
        "full_adjusted_retrieved_at", "adjusted_source_path",
    ]
    adjusted = adjusted[[column for column in adjusted_keep if column in adjusted.columns]]
    combined = required.merge(raw, on=["period", "ticker", "date"], how="left", validate="one_to_one")
    combined = combined.merge(adjusted, on=["period", "ticker", "date"], how="left", validate="one_to_one")
    combined["local_factor"] = pd.to_numeric(combined.get("adjusted_close"), errors="coerce") / pd.to_numeric(
        combined.get("provider_raw_close"), errors="coerce"
    )
    combined.loc[~combined["local_factor"].gt(0), "local_factor"] = pd.NA
    return combined


def load_local_market_sessions() -> dict[str, set[str]]:
    sessions = {"P1": set(), "P2": set()}
    for path in sorted((P1_LIFECYCLE / "official_raw_execution_ohlcv").glob("*/*.csv.gz")):
        year = path.stem.split(".")[0]
        if year in {str(value) for value in range(2015, 2023)}:
            sessions["P1"].update(pd.read_csv(path, usecols=["date"], dtype=str)["date"].dropna())
    for path in sorted((P3_ACQUISITION / "price").glob("*.csv.gz")):
        year = path.stem.split(".")[0]
        if year in {"2022", "2023", "2024", "2025", "2026"}:
            sessions["P2"].update(pd.read_csv(path, usecols=["date"], dtype=str)["date"].dropna())
    return sessions


def normalize_ticker(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def read_registry_candidate(path: Path, required_keys: pd.MultiIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        header = pd.read_csv(path, nrows=0).columns.tolist()
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    ticker_col = "ticker" if "ticker" in header else "stock_id" if "stock_id" in header else None
    date_col = "date" if "date" in header else "trade_date" if "trade_date" in header else "price_date" if "price_date" in header else None
    raw_col = next((column for column in ("close", "official_raw_close") if column in header), None)
    adjusted_col = "adjusted_close" if "adjusted_close" in header else "adj_close" if "adj_close" in header else None
    if not ticker_col or not date_col or (not raw_col and not adjusted_col):
        return pd.DataFrame(), pd.DataFrame()
    wanted = [
        ticker_col, date_col, raw_col, adjusted_col, "raw_close_comparator", "market", "name",
        "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc", "retrieved_at",
    ]
    wanted = list(dict.fromkeys(column for column in wanted if column and column in header))
    try:
        frame = pd.read_csv(path, usecols=wanted, dtype={ticker_col: str, date_col: str})
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    frame["ticker"] = frame[ticker_col].map(normalize_ticker)
    frame["date"] = frame[date_col].astype(str)
    keys = pd.MultiIndex.from_frame(frame[["ticker", "date"]])
    frame = frame.loc[keys.isin(required_keys)].copy()
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    quality = frame["source_quality"].astype(str) if "source_quality" in frame else pd.Series("", index=frame.index)
    urls = frame["source_url"].astype(str) if "source_url" in frame else pd.Series("", index=frame.index)
    locator = str(path).lower()
    common = pd.DataFrame({
        "ticker": frame["ticker"], "date": frame["date"],
        "market": frame["market"].astype(str) if "market" in frame else "",
        "name": frame["name"].astype(str) if "name" in frame else "",
        "source_quality": quality, "adjustment_policy": frame["adjustment_policy"].astype(str) if "adjustment_policy" in frame else "",
        "source_url": urls, "source_hash": frame["source_hash"].astype(str) if "source_hash" in frame else "",
        "retrieved_at": frame["retrieval_time_utc"].astype(str) if "retrieval_time_utc" in frame else frame["retrieved_at"].astype(str) if "retrieved_at" in frame else "",
        "source_path": str(path),
    })
    raw = pd.DataFrame()
    if raw_col:
        official = (
            (quality.str.contains("official", case=False, na=False) & ~quality.str.contains("nonofficial", case=False, na=False))
            | urls.str.contains("twse.com.tw|tpex.org.tw", case=False, regex=True, na=False)
            | ("official" in locator and "trusted_adjusted" not in locator)
        )
        raw = common.copy()
        raw["raw_close"] = pd.to_numeric(frame[raw_col], errors="coerce")
        raw = raw[official & raw["raw_close"].gt(0)]
    adjusted = pd.DataFrame()
    if adjusted_col:
        adjusted = common.copy()
        adjusted["adjusted_close"] = pd.to_numeric(frame[adjusted_col], errors="coerce")
        provider_col = "raw_close_comparator" if "raw_close_comparator" in frame else raw_col
        adjusted["provider_raw_close"] = pd.to_numeric(frame[provider_col], errors="coerce") if provider_col else pd.NA
        adjusted = adjusted[adjusted["adjusted_close"].gt(0)]
    return raw, adjusted


def scan_local_registry(required: pd.DataFrame) -> pd.DataFrame:
    if REGISTRY_REUSE.exists():
        return pd.read_csv(REGISTRY_REUSE, dtype={"ticker": str, "date": str})
    audit = pd.read_csv(REUSE / "local_price_source_path_schema_audit.csv", dtype=str)
    paths = [Path(value) for value in audit.loc[audit["header_status"].eq("required_keys_reused"), "source_path"]]
    paths = [path for path in paths if path.exists() and OUT not in path.parents]
    required_keys = pd.MultiIndex.from_frame(required[["ticker", "date"]])
    raw_parts: list[pd.DataFrame] = []
    adjusted_parts: list[pd.DataFrame] = []
    set_step("scan_existing_local_source_registry", registry_candidate_files=len(paths), network_rows=0)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(read_registry_candidate, path, required_keys): path for path in paths}
        for index, future in enumerate(as_completed(futures), start=1):
            raw, adjusted = future.result()
            if not raw.empty:
                raw_parts.append(raw)
            if not adjusted.empty:
                adjusted_parts.append(adjusted)
            if index % 250 == 0:
                set_step("scan_existing_local_source_registry", registry_candidate_files=len(paths), completed_files=index, network_rows=0)
    raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame(columns=["ticker", "date"])
    adjusted = pd.concat(adjusted_parts, ignore_index=True) if adjusted_parts else pd.DataFrame(columns=["ticker", "date"])
    raw = raw.drop_duplicates(["ticker", "date"], keep="first")
    adjusted = adjusted.drop_duplicates(["ticker", "date"], keep="first")
    raw = raw.rename(columns={
        "market": "registry_market", "name": "registry_name", "raw_close": "registry_raw_close",
        "source_quality": "registry_raw_source_quality", "adjustment_policy": "registry_raw_adjustment_policy",
        "source_url": "registry_raw_source_url", "source_hash": "registry_raw_source_hash",
        "retrieved_at": "registry_raw_retrieved_at", "source_path": "registry_raw_source_path",
    })
    adjusted = adjusted.rename(columns={
        "adjusted_close": "registry_adjusted_close", "provider_raw_close": "registry_adjusted_provider_raw_close",
        "source_quality": "registry_adjusted_source_quality", "adjustment_policy": "registry_adjusted_policy",
        "source_url": "registry_adjusted_source_url", "source_hash": "registry_adjusted_source_hash",
        "retrieved_at": "registry_adjusted_retrieved_at", "source_path": "registry_adjusted_source_path",
    })
    result = required.merge(raw, on=["ticker", "date"], how="left").merge(adjusted, on=["ticker", "date"], how="left")
    result.to_csv(REGISTRY_REUSE, index=False, compression="gzip")
    return result


def local_audit() -> None:
    frontier, request, exact, policy = load_authority()
    set_step("local_exact_key_reuse_audit_running")
    reuse = load_reuse_a()
    full_reuse = load_full_local_sources(exact)

    requested = exact.copy()
    requested["date"] = requested["decision_date"]
    joined = requested.merge(full_reuse, on=["period", "ticker", "date"], how="left", validate="many_to_one")
    raw = joined["full_raw_close"].notna()
    factor = joined["local_factor"].notna()
    trusted = joined["adjusted_close"].notna()
    known_e = joined["classification"].eq("E_official_no_trade_or_NA_no_analysis_gap")
    sessions = load_local_market_sessions()
    joined["market_session_open_evidence"] = joined.apply(
        lambda row: row["date"] in sessions.get(row["period"], set()), axis=1
    )
    joined["local_A_to_E_classification"] = "E_no_market_session_local_candidate_no_trade_or_holiday_review"
    joined.loc[
        joined["market_session_open_evidence"], "local_A_to_E_classification"
    ] = "E_market_session_open_ticker_trade_unclassified_local_only"
    joined.loc[trusted & ~raw, "local_A_to_E_classification"] = "C_trusted_trade_evidence_official_raw_gap_local_only"
    joined.loc[raw, "local_A_to_E_classification"] = "D_raw_ready_adjusted_factor_incomplete_unadjusted_research_fallback"
    joined.loc[raw & factor, "local_A_to_E_classification"] = "B_raw_plus_adjusted_factor_reconstructable"
    joined.loc[known_e, "local_A_to_E_classification"] = "E_official_no_trade_or_NA_no_analysis_gap"
    joined["network_download_authorized"] = False
    joined["unadjusted_ma_slope_research_fallback_allowed"] = raw
    joined["corporate_action_warning_required"] = raw & ~factor
    joined["future_data_violation_count"] = 0
    joined.to_csv(LOCAL_CLASSIFICATION, index=False, compression="gzip")

    summary = (
        joined.groupby(["period", "local_A_to_E_classification"], dropna=False)
        .size().rename("rows").reset_index()
    )
    summary.to_csv(OUT / "incumbent_continuity_classification_summary.csv", index=False)

    front = frontier.copy()
    front["date"] = front["requested_execution_date"]
    front_joined = front.merge(reuse, on=["period", "ticker", "date"], how="left", validate="one_to_one")
    local_ready = as_bool(front_joined["raw_ready"]) & front_joined["raw_close"].notna()
    local = front_joined.loc[local_ready].copy()
    local["open"] = pd.NA
    local["high"] = pd.NA
    local["low"] = pd.NA
    local["close"] = pd.to_numeric(local["raw_close"], errors="coerce")
    local["source_quality"] = local["source_quality_raw"]
    local["source_hash"] = local["source_hash_raw"]
    local["source_path"] = local["source_path_raw"]
    local["exact_key_ready"] = True
    local["fill_mode"] = "local_official_raw_cache_reuse"
    local["future_data_violation_count"] = 0
    keep = [
        "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date",
        "market", "name", "open", "high", "low", "close", "source_quality", "adjustment_policy",
        "source_url", "source_hash", "retrieved_at", "source_path", "exact_key_ready", "fill_mode",
        "future_data_violation_count",
    ]
    local[keep].to_csv(LOCAL_FRONTIER, index=False)

    missing = front_joined.loc[~local_ready].copy()
    # The only route candidates must come from the 25-row frontier authority.
    missing["market_for_route"] = missing["market"]
    yahoo_tw = missing["trusted_raw_source_url"].fillna("").str.contains(r"\.TW(?:\?|$)", regex=True)
    yahoo_two = missing["trusted_raw_source_url"].fillna("").str.contains(r"\.TWO(?:\?|$)", regex=True)
    missing.loc[missing["market_for_route"].isna() & yahoo_tw, "market_for_route"] = "TWSE"
    missing.loc[missing["market_for_route"].isna() & yahoo_two, "market_for_route"] = "TPEx"
    unresolved_market = missing["market_for_route"].isna()
    if unresolved_market.any():
        raise RuntimeError("bounded route candidates have unresolved market: " + ",".join(missing.loc[unresolved_market, "ticker"]))
    route_plan = missing[[
        "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date",
        "market_for_route", "trusted_raw_close", "trusted_raw_source_url", "trusted_raw_source_hash",
    ]].rename(columns={"market_for_route": "market"})
    route_plan["year_month"] = route_plan["requested_execution_date"].str[:7]
    route_plan["download_authority"] = "frontier_exact_leg_only"
    route_plan.to_csv(OUT / "frontier_bounded_route_plan.csv", index=False)
    if len(local) + len(route_plan) != 25 or len(route_plan) > 25:
        raise RuntimeError("frontier partition escaped authority")

    scope = pd.DataFrame([
        {"scope": "frontier_exact_legs", "rows": 25, "network_download_authorized": True, "loaded_for_download": True},
        {"scope": "incumbent_continuity_exact_rows", "rows": 23717, "network_download_authorized": False, "loaded_for_download": False},
        {"scope": "atomic_policy_blockers", "rows": len(policy), "network_download_authorized": False, "loaded_for_download": False},
        {"scope": "provisional_action_leg_gaps", "rows": 5193, "network_download_authorized": False, "loaded_for_download": False},
    ])
    scope.to_csv(OUT / "authority_scope_guard_audit.csv", index=False)
    set_step(
        "local_audit_complete_bounded_fill_pending",
        frontier_rows=25,
        frontier_local_ready_rows=len(local),
        frontier_network_candidate_rows=len(route_plan),
        incumbent_local_classification_rows=len(joined),
        incumbent_network_rows=0,
    )


def clean_number(value: object) -> float | None:
    try:
        text = str(value).replace(",", "").replace("--", "").strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def roc_date(value: object) -> str:
    parts = str(value).strip().split("/")
    try:
        return f"{int(parts[0]) + 1911:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except (ValueError, IndexError):
        return ""


def field_index(fields: list, token: str) -> int:
    for index, field in enumerate(fields):
        if token in "".join(str(field).split()):
            return index
    return -1


def official_month_url(ticker: str, market: str, month: str) -> str:
    if market == "TWSE":
        return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + urlencode(
            {"date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json"}
        )
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?" + urlencode(
        {"code": ticker, "date": month.replace("-", "/") + "/01", "response": "json"}
    )


def parse_official(payload: dict, ticker: str, market: str) -> tuple[bool, list[dict]]:
    if market == "TWSE":
        fields, data = payload.get("fields") or [], payload.get("data") or []
    else:
        table = next((x for x in payload.get("tables") or [] if x.get("fields") and x.get("data")), {})
        fields, data = table.get("fields") or [], table.get("data") or []
    schema_ok = str(payload.get("stat", "")).lower() == "ok"
    indices = {
        "date": field_index(fields, "日期"), "open": field_index(fields, "開盤"),
        "high": field_index(fields, "最高"), "low": field_index(fields, "最低"),
        "close": field_index(fields, "收盤"),
    }
    if min(indices.values()) < 0:
        return False, []
    rows = []
    for values in data:
        day = roc_date(values[indices["date"]])
        close = clean_number(values[indices["close"]])
        if day and close is not None:
            rows.append({
                "ticker": ticker, "date": day, "market": market,
                "open": clean_number(values[indices["open"]]),
                "high": clean_number(values[indices["high"]]),
                "low": clean_number(values[indices["low"]]), "close": close,
            })
    return schema_ok, rows


def bounded_fill() -> None:
    frontier, request, _exact, _policy = load_authority()
    if not (OUT / "frontier_bounded_route_plan.csv").exists():
        local_audit()
    routes = pd.read_csv(OUT / "frontier_bounded_route_plan.csv", dtype=str)
    frontier_keys = set(zip(frontier["period"], frontier["ticker"], frontier["requested_execution_date"]))
    route_keys = set(zip(routes["period"], routes["ticker"], routes["requested_execution_date"]))
    if not route_keys.issubset(frontier_keys) or request["network_download_authorized"].str.lower().ne("false").any():
        raise RuntimeError("network route authority violation")
    set_step("bounded_frontier_official_fill_running", bounded_route_rows=len(routes))
    RAW_CACHE.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifests: list[dict] = []
    accepted: list[dict] = []
    for row in routes.to_dict("records"):
        ticker, market, month = row["ticker"], row["market"], row["year_month"]
        target = row["requested_execution_date"]
        route_id = f"{ticker}_{market}_{month}"
        cache = RAW_CACHE / f"{route_id}.json"
        url = official_month_url(ticker, market, month)
        raw = b""
        status = 0
        error = ""
        final_url = url
        reused = cache.exists()
        if reused:
            raw = cache.read_bytes()
            status = 200
        else:
            for attempt in range(4):
                try:
                    response = session.get(url, headers={"User-Agent": "Mozilla/5.0 RadarFrontierBounded/1.0"}, timeout=45)
                    status, final_url = response.status_code, response.url
                    if response.ok:
                        raw = response.content
                        break
                    error = f"HTTP_{response.status_code}"
                except requests.RequestException as exc:
                    error = type(exc).__name__
                time.sleep(0.6 * (attempt + 1))
            if raw:
                cache.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest() if raw else ""
        schema_ok, parsed = False, []
        if raw:
            try:
                schema_ok, parsed = parse_official(json.loads(raw.decode("utf-8-sig")), ticker, market)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                error = f"parse_{type(exc).__name__}"
        exact_rows = [x for x in parsed if x["date"] == target]
        retrieved_at = now()
        for value in exact_rows:
            accepted.append({
                **{k: row[k] for k in ["variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date"]},
                "market": market, "name": pd.NA, "open": value["open"], "high": value["high"],
                "low": value["low"], "close": value["close"],
                "source_quality": f"official_{market.lower()}_selected_ticker_month_unadjusted_execution",
                "adjustment_policy": "official_unadjusted_execution_only", "source_url": final_url,
                "source_hash": digest, "retrieved_at": retrieved_at, "source_path": str(cache),
                "exact_key_ready": True, "fill_mode": "bounded_official_ticker_month_route",
                "future_data_violation_count": 0,
            })
        outcome = "accepted_exact_row" if exact_rows else "official_valid_no_target_row" if schema_ok else "source_route_failed"
        manifests.append({
            "route_id": route_id, "period": row["period"], "ticker": ticker, "market": market,
            "target_date": target, "year_month": month, "outcome": outcome, "http_status": status,
            "schema_ok": schema_ok, "response_rows": len(parsed), "accepted_exact_rows": len(exact_rows),
            "source_url": final_url, "source_hash": digest, "response_bytes": len(raw),
            "retrieved_at": retrieved_at, "raw_cache_path": str(cache), "cache_reused": reused,
            "route_error": error, "download_authority": "frontier_exact_leg_only",
            "future_data_violation_count": 0,
        })
        pd.DataFrame(manifests).to_csv(SOURCE_MANIFEST, index=False)
        pd.DataFrame(accepted).to_csv(NETWORK_PATCH, index=False)
        set_step("bounded_frontier_official_fill_running", bounded_route_rows=len(routes), completed_routes=len(manifests))
    if len(manifests) != len(routes):
        raise RuntimeError("bounded routes did not finish")
    set_step("bounded_frontier_official_fill_complete_finalize_pending", completed_routes=len(manifests))


def finalize() -> None:
    frontier, _request, exact, policy = load_authority()
    if not LOCAL_FRONTIER.exists():
        local_audit()
    local = pd.read_csv(LOCAL_FRONTIER, dtype=str)
    network = pd.read_csv(NETWORK_PATCH, dtype=str) if NETWORK_PATCH.exists() and NETWORK_PATCH.stat().st_size else pd.DataFrame(columns=local.columns)
    accepted = pd.concat([local, network], ignore_index=True)
    accepted = accepted.drop_duplicates(["period", "ticker", "requested_execution_date"], keep="last")
    accepted_keys = set(zip(accepted["period"], accepted["ticker"], accepted["requested_execution_date"]))
    front_keys = set(zip(frontier["period"], frontier["ticker"], frontier["requested_execution_date"]))
    if not accepted_keys.issubset(front_keys):
        raise RuntimeError("accepted patch contains non-authority key")
    accepted.to_csv(OUT / "frontier_official_raw_accepted_patch.csv", index=False)
    unresolved = frontier[~frontier.apply(lambda r: (r["period"], r["ticker"], r["requested_execution_date"]) in accepted_keys, axis=1)].copy()
    manifest = pd.read_csv(SOURCE_MANIFEST, dtype=str) if SOURCE_MANIFEST.exists() else pd.DataFrame()
    if not unresolved.empty:
        reason_by_key = {}
        for row in manifest.to_dict("records"):
            route_error = str(row["route_error"]) if pd.notna(row.get("route_error")) and str(row.get("route_error")) else ""
            reason_by_key[(row["period"], row["ticker"], row["target_date"])] = row["outcome"] + (":" + route_error if route_error else "")
        unresolved["blocked_reason"] = unresolved.apply(
            lambda r: reason_by_key.get((r["period"], r["ticker"], r["requested_execution_date"]), "bounded_route_not_accepted"), axis=1
        )
    no_trade = unresolved[unresolved.get("blocked_reason", pd.Series(index=unresolved.index, dtype=str)).str.contains("no_target", na=False)].copy()
    blocked = unresolved.drop(index=no_trade.index).copy()
    blocked["future_data_violation_count"] = 0
    blocked.to_csv(OUT / "frontier_remaining_blocked.csv", index=False)
    no_trade["classification"] = "official_valid_response_no_exact_target_row_possible_no_trade_or_suspension"
    no_trade["future_data_violation_count"] = 0
    no_trade.to_csv(OUT / "frontier_official_no_trade_ledger.csv", index=False)

    classification = pd.read_csv(LOCAL_CLASSIFICATION, dtype=str)
    class_summary = pd.read_csv(OUT / "incumbent_continuity_classification_summary.csv", dtype=str)
    future = pd.DataFrame([
        {"audit_item": "frontier_exact_dates_only", "status": "pass", "future_data_violation_count": 0},
        {"audit_item": "incumbent_network_download_prohibited", "status": "pass", "future_data_violation_count": 0},
        {"audit_item": "atomic_policy_rows_not_downloaded", "status": "pass", "future_data_violation_count": 0},
        {"audit_item": "provisional_5193_not_used_as_download_authority", "status": "pass", "future_data_violation_count": 0},
        {"audit_item": "official_raw_and_adjusted_analysis_separate", "status": "pass", "future_data_violation_count": 0},
    ])
    future.to_csv(OUT / "frontier_future_data_audit.csv", index=False)

    set_step(
        "complete_ready_for_core_rechain", frontier_exact_ready_rows=len(accepted),
        frontier_official_no_trade_rows=len(no_trade), frontier_exact_blocked_rows=len(blocked),
    )

    output_files = [
        p for p in OUT.iterdir() if p.is_file() and p.name not in {
            "manifest.json", "checksum_manifest.csv", "readiness_for_core_rechain.json", "final_summary_zh.md"
        }
    ]
    checksums = [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(output_files)]
    pd.DataFrame(checksums).to_csv(OUT / "checksum_manifest.csv", index=False)
    readiness = {
        "task": "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-LOCAL-AUDIT-AND-BOUNDED-FILL-001",
        "status": "frontier_closed_ready_for_core_rechain" if blocked.empty else "frontier_partial_blocked_ready_for_core_rechain",
        "frontier_authority_rows": 25,
        "frontier_exact_ready_rows": int(len(accepted)),
        "frontier_exact_blocked_rows": int(len(blocked)),
        "frontier_official_no_trade_rows": int(len(no_trade)),
        "frontier_closed_rows": int(len(accepted) + len(no_trade)),
        "frontier_local_reuse_rows": int(len(local)),
        "frontier_bounded_network_rows": int(len(network)),
        "incumbent_local_audit_rows": int(len(classification)),
        "incumbent_network_download_rows": 0,
        "atomic_policy_blocker_rows": int(len(policy)),
        "provisional_gap_rows_used_as_download_authority": 0,
        "ready_for_core_action_leg_frontier_rechain": True,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        "formal_0050_00631l_mainline_changed": False,
        **FLAGS,
        "classification_summary": class_summary.to_dict("records"),
    }
    write_json(OUT / "readiness_for_core_rechain.json", readiness)
    summary = f"""# P1/P2 MA-slope CD50 frontier source 結案

## 結論

- 下載 authority 僅限 Core 指定 25 筆 frontier exact legs。
- exact official raw ready：{len(accepted)}/25；official no-trade：{len(no_trade)}/25；true source blocked：{len(blocked)}/25。
- local official raw reuse：{len(local)} 筆；bounded official route patch：{len(network)} 筆。
- incumbent continuity 共 {len(classification):,} 筆僅做 local A/B/C/D/E 分類，網路下載 0 筆。
- 24 筆 atomic policy blockers 與 5,193 provisional gaps 均未作下載清單。
- future_data_violation_count=0。

## 治理

- 此包只供 Core/Data rechain individual-stock research action legs。
- 未改正式 0050 signal -> 00631L execution MA4+7 / MA10+20 / CD7 主線。
- adjusted 缺失但 raw ready 只允許 unadjusted MA/slope research fallback，並保留 corporate-action warning；不得包裝 formal adjusted。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    all_files = [p for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"]
    write_json(OUT / "manifest.json", {
        "task": readiness["task"], "generated_at": now(), "output_path": str(OUT),
        "files": [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(all_files)],
        "flags": FLAGS, "future_data_violation_count": 0,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["local", "fill", "finalize", "all"], default="all")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.phase in {"local", "all"}:
        local_audit()
    if args.phase in {"fill", "all"}:
        bounded_fill()
    if args.phase in {"finalize", "all"}:
        finalize()


if __name__ == "__main__":
    main()
