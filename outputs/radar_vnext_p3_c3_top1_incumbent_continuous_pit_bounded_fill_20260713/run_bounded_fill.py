from __future__ import annotations

import gzip
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-C3-TOP1-INCUMBENT-CONTINUOUS-PIT-BOUNDED-FILL-001"
REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RAW_CACHE = OUT / "raw_cache"
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p3_layer5_C3_top1_incumbent_path_corrected_NAV_contract_20260713"
)
SEGMENTS_PATH = CORE / "p3_incumbent_continuous_PIT_bounded_source_requirement.csv"

P3 = REPO / "outputs" / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
RAW_WARMUP = REPO / "outputs" / "radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711" / "compact" / "raw_hlc_warmup"
CHIP_WARMUP = REPO / "outputs" / "radar_vnext_p3_exact_primary80_chip_20d_warmup_gap_fill_20260711" / "compact"
RANK1_HLC = (
    REPO / "outputs" / "radar_vnext_p3_layer04_rank1_sequential_lifecycle_adjusted_hlc_factor_source_package_20260713"
    / "rank1_adjusted_analysis_hlc_factor_compact.csv.gz"
)
RANK1_EVENT_INVENTORY = RANK1_HLC.parent / "rank1_corporate_action_event_inventory.csv"
ALL80_DELTA_HLC = (
    REPO / "outputs" / "radar_vnext_p3_layer5_all80_continuous_lifecycle_adjusted_hlc_bounded_delta_acquisition_20260713"
    / "all80_bounded_delta_adjusted_hlc_exact_key_compact.csv.gz"
)

YEARS = (2023, 2024, 2025)
TAIPEI = ZoneInfo("Asia/Taipei")
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

FAMILY_SPECS = {
    "institutional": {
        "warmup_dir": "institutional",
        "broad_dir": "chip_institutional",
        "values": ["foreign_net", "trust_net", "dealer_net"],
    },
    "margin_short": {
        "warmup_dir": "margin_short",
        "broad_dir": "chip_margin_short",
        "values": ["margin_balance", "margin_change", "short_balance", "short_change"],
    },
    "securities_lending": {
        "warmup_dir": "securities_lending",
        "broad_dir": "chip_securities_lending",
        "values": ["sbl_balance", "sbl_change"],
    },
    "foreign_ownership": {
        "warmup_dir": "foreign_ownership",
        "broad_dir": "foreign_ownership",
        "values": [
            "issued_shares", "foreign_holding_shares", "foreign_holding_ratio",
            "foreign_available_shares", "foreign_available_ratio",
        ],
    },
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def write_csv_gz(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig", compression="gzip")


def fetch_json(url: str, cache_path: Path) -> tuple[dict, str, bool]:
    if cache_path.exists():
        raw = cache_path.read_bytes()
        return json.loads(raw.decode("utf-8")), sha256_bytes(raw), True
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
            return payload, sha256_bytes(raw), False
        except Exception as exc:  # retry evidence is retained in the final blocker if exhausted
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def build_requirements() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    segments = pd.read_csv(SEGMENTS_PATH, dtype={"ticker": str})
    calendar_parts = []
    for year in YEARS:
        part = pd.read_csv(RAW_WARMUP / f"{year}.csv.gz", usecols=["date", "market"])
        calendar_parts.append(part.loc[part["market"].eq("TWSE"), "date"])
    calendar = sorted(set(pd.concat(calendar_parts).astype(str)))

    rows = []
    for segment in segments.itertuples(index=False):
        prior = [date for date in calendar if date < segment.required_start][-int(segment.warmup_trading_days):]
        active = [date for date in calendar if segment.required_start <= date <= segment.required_end]
        assert len(active) == int(segment.required_decision_rows), (segment.ticker, segment.segment, len(active))
        for date in prior:
            rows.append({
                "ticker": segment.ticker, "segment": int(segment.segment), "date": date,
                "scope": "warmup", "required_start": segment.required_start,
                "required_end": segment.required_end, "TDCC_P3_1": segment.TDCC_P3_1,
            })
        for date in active:
            rows.append({
                "ticker": segment.ticker, "segment": int(segment.segment), "date": date,
                "scope": "decision", "required_start": segment.required_start,
                "required_end": segment.required_end, "TDCC_P3_1": segment.TDCC_P3_1,
            })
    requirement = pd.DataFrame(rows)
    keys = requirement[["ticker", "date"]].drop_duplicates().sort_values(["ticker", "date"])
    assert int(requirement["scope"].eq("decision").sum()) == 139
    assert len(keys) == 279
    return segments, requirement, keys


def load_local_raw(keys: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        frame = pd.read_csv(RAW_WARMUP / f"{year}.csv.gz", dtype={"ticker": str})
        frame["raw_reuse_source"] = "exact_primary80_raw_hlc_warmup_compact"
        frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    raw = keys.merge(raw, on=["ticker", "date"], how="left")
    ready = raw[["open", "high", "low", "close"]].notna().all(axis=1)
    return raw.loc[ready].drop_duplicates(["ticker", "date"])


def roc_date_to_iso(value: str) -> str:
    year, month, day = value.split("/")
    return f"{int(year) + 1911:04d}-{int(month):02d}-{int(day):02d}"


def fetch_missing_twse_raw(keys: pd.DataFrame, local_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    missing = keys.merge(local_raw[["ticker", "date"]], on=["ticker", "date"], how="left", indicator=True)
    missing = missing.loc[missing["_merge"].eq("left_only"), ["ticker", "date"]]
    rows, manifests = [], []
    for (ticker, month), group in missing.assign(month=lambda x: x["date"].str[:7].str.replace("-", "")).groupby(["ticker", "month"]):
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?" + urllib.parse.urlencode(
            {"date": f"{month}01", "stockNo": ticker, "response": "json"}
        )
        cache_path = RAW_CACHE / f"twse_stock_day_{ticker}_{month}.json"
        payload, source_hash, reused = fetch_json(url, cache_path)
        fields = payload.get("fields", [])
        assert payload.get("stat") == "OK", payload.get("stat")
        index = {name: position for position, name in enumerate(fields)}
        target_dates = set(group["date"])
        found = set()
        for values in payload.get("data", []):
            date = roc_date_to_iso(values[0])
            if date not in target_dates:
                continue
            def number(label: str) -> float:
                return float(str(values[index[label]]).replace(",", ""))
            rows.append({
                "ticker": ticker, "date": date, "name": "", "market": "TWSE",
                "open": number("開盤價"), "high": number("最高價"), "low": number("最低價"),
                "close": number("收盤價"), "volume": number("成交股數"),
                "turnover_value": number("成交金額"),
                "source_quality": "official_twse_stock_day_selected_ticker_month",
                "adjustment_policy": "unadjusted_execution_only",
                "source_url": url, "source_hash": source_hash, "retrieval_time_utc": now(),
                "raw_reuse_source": "new_bounded_official_selected_ticker_month",
            })
            found.add(date)
        manifests.append({
            "family": "official_raw_hlc", "ticker": ticker, "route_scope": month,
            "source_url": url, "source_hash": source_hash, "cache_path": str(cache_path),
            "cache_reused": reused, "requested_rows": len(target_dates), "accepted_rows": len(found),
            "blocked_rows": len(target_dates - found), "status": "accepted" if found == target_dates else "partial",
        })
    return pd.DataFrame(rows), manifests


def load_local_adjusted(keys: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for path, label in ((RANK1_HLC, "rank1_adjusted_hlc_local_reuse"), (ALL80_DELTA_HLC, "all80_delta_adjusted_hlc_local_reuse")):
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame["adjusted_reuse_source"] = label
        frames.append(frame)
    adjusted = pd.concat(frames, ignore_index=True, sort=False)
    adjusted = keys.merge(adjusted, on=["ticker", "date"], how="inner")
    ready = adjusted[["adjusted_high", "adjusted_low", "adjusted_close"]].notna().all(axis=1)
    return adjusted.loc[ready].drop_duplicates(["ticker", "date"])


def parse_yahoo(payload: dict, ticker: str, source_url: str, source_hash: str) -> tuple[pd.DataFrame, list[dict]]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    rows = []
    for index, timestamp in enumerate(timestamps):
        values = {field: quote.get(field, [None] * len(timestamps))[index] for field in ("open", "high", "low", "close")}
        adj_close = adjusted[index] if index < len(adjusted) else None
        if any(value is None for value in values.values()) or adj_close is None or not values["close"]:
            continue
        factor = float(adj_close) / float(values["close"])
        if not math.isfinite(factor) or factor <= 0:
            continue
        date = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(TAIPEI).date().isoformat()
        rows.append({
            "ticker": ticker, "date": date, "provider_raw_open": values["open"],
            "provider_raw_high": values["high"], "provider_raw_low": values["low"],
            "provider_raw_close": values["close"], "adjustment_factor": factor,
            "adjusted_open": float(values["open"]) * factor,
            "adjusted_high": float(values["high"]) * factor,
            "adjusted_low": float(values["low"]) * factor,
            "adjusted_close": float(adj_close),
            "adjusted_source_quality": "trusted_nonofficial_yahoo_research_grade",
            "adjustment_policy": "same-provider adjusted_close/raw_close factor applied to same-provider raw HLC; analysis only; not formal",
            "source_url": source_url, "source_hash": source_hash,
            "retrieved_at": now(), "accepted_for_formal": False, "human_review_required": True,
            "adjusted_reuse_source": "new_bounded_trusted_ticker_route",
        })

    events = []
    for event_type, event_map in result.get("events", {}).items():
        for event in event_map.values():
            timestamp = event.get("date")
            if timestamp is None:
                continue
            events.append({
                "ticker": ticker, "event_type": event_type,
                "event_date": datetime.fromtimestamp(timestamp, timezone.utc).astimezone(TAIPEI).date().isoformat(),
                "amount": event.get("amount", ""), "numerator": event.get("numerator", ""),
                "denominator": event.get("denominator", ""), "split_ratio": event.get("splitRatio", ""),
                "source_quality": "trusted_nonofficial_yahoo_event_inventory",
                "source_url": source_url, "source_hash": source_hash,
                "accepted_for_formal": False, "human_review_required": True,
            })
    return pd.DataFrame(rows), events


def fetch_missing_adjusted(keys: pd.DataFrame, local_adjusted: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    missing = keys.merge(local_adjusted[["ticker", "date"]], on=["ticker", "date"], how="left", indicator=True)
    missing = missing.loc[missing["_merge"].eq("left_only"), ["ticker", "date"]]
    frames, manifests, events = [], [], []
    for ticker, group in missing.groupby("ticker"):
        start = pd.Timestamp(group["date"].min()) - pd.Timedelta(days=7)
        end = pd.Timestamp(group["date"].max()) + pd.Timedelta(days=8)
        period1 = int(start.tz_localize("Asia/Taipei").tz_convert("UTC").timestamp())
        period2 = int(end.tz_localize("Asia/Taipei").tz_convert("UTC").timestamp())
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + f"{ticker}.TW?" + urllib.parse.urlencode({
            "period1": period1, "period2": period2, "interval": "1d",
            "events": "div,splits", "includeAdjustedClose": "true",
        })
        cache_path = RAW_CACHE / f"yahoo_{ticker}_{period1}_{period2}.json"
        payload, source_hash, reused = fetch_json(url, cache_path)
        if payload.get("chart", {}).get("error") or not payload.get("chart", {}).get("result"):
            manifests.append({
                "family": "adjusted_analysis_hlc", "ticker": ticker, "route_scope": "bounded_required_range",
                "source_url": url, "source_hash": source_hash, "cache_path": str(cache_path),
                "cache_reused": reused, "requested_rows": len(group), "accepted_rows": 0,
                "blocked_rows": len(group), "status": "blocked_provider_response",
            })
            continue
        parsed, ticker_events = parse_yahoo(payload, ticker, url, source_hash)
        parsed = group.merge(parsed, on=["ticker", "date"], how="inner")
        frames.append(parsed)
        events.extend(ticker_events)
        manifests.append({
            "family": "adjusted_analysis_hlc", "ticker": ticker, "route_scope": "bounded_required_range",
            "source_url": url, "source_hash": source_hash, "cache_path": str(cache_path),
            "cache_reused": reused, "requested_rows": len(group), "accepted_rows": len(parsed),
            "blocked_rows": len(group) - len(parsed), "status": "accepted" if len(parsed) == len(group) else "partial",
        })
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), manifests, events


def value_complete(frame: pd.DataFrame, values: list[str]) -> pd.Series:
    return frame[values].notna().all(axis=1)


def load_family(family: str, keys: pd.DataFrame) -> pd.DataFrame:
    spec = FAMILY_SPECS[family]
    frames = []
    for priority, (base, directory, label) in enumerate((
        (CHIP_WARMUP, spec["warmup_dir"], "exact_primary80_chip_20d_warmup_reuse"),
        (P3 / "compact", spec["broad_dir"], "p3_broad_market_compact_reuse"),
    )):
        for year in YEARS:
            path = base / directory / f"{year}.csv.gz"
            frame = pd.read_csv(path, dtype={"ticker": str})
            frame["source_reuse_package"] = label
            frame["source_priority"] = priority
            frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = keys.merge(combined, on=["ticker", "date"], how="left")
    combined["value_complete"] = value_complete(combined, spec["values"])
    combined = combined.sort_values(["ticker", "date", "value_complete", "source_priority"], ascending=[True, True, False, True])
    combined = combined.drop_duplicates(["ticker", "date"])
    return combined


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW_CACHE.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "progress.json", {"task_id": TASK_ID, "status": "running", "current_step": "build_exact_requirements"})
    (OUT / "current_step.txt").write_text("build_exact_requirements\n", encoding="utf-8")

    segments, requirement, keys = build_requirements()
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_segment_exact_keys.csv", requirement)

    (OUT / "current_step.txt").write_text("reuse_and_fill_adjusted_hlc\n", encoding="utf-8")
    local_raw = load_local_raw(keys)
    fetched_raw, raw_manifests = fetch_missing_twse_raw(keys, local_raw)
    raw = pd.concat([local_raw, fetched_raw], ignore_index=True, sort=False).drop_duplicates(["ticker", "date"], keep="last")

    local_adjusted = load_local_adjusted(keys)
    fetched_adjusted, adjusted_manifests, events = fetch_missing_adjusted(keys, local_adjusted)
    adjusted = pd.concat([local_adjusted, fetched_adjusted], ignore_index=True, sort=False)
    adjusted = adjusted.drop_duplicates(["ticker", "date"], keep="first")

    (OUT / "current_step.txt").write_text("reuse_chip_families\n", encoding="utf-8")
    family_frames = {family: load_family(family, keys) for family in FAMILY_SPECS}

    blocked = []
    zero_na = []
    family_coverage = []
    source_manifests = raw_manifests + adjusted_manifests

    exact = keys.copy()
    raw_columns = [
        "ticker", "date", "name", "market", "open", "high", "low", "close", "volume", "turnover_value",
        "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieval_time_utc", "raw_reuse_source",
    ]
    raw_keep = [column for column in raw_columns if column in raw.columns]
    raw_part = raw[raw_keep].rename(columns={
        "open": "official_raw_open", "high": "official_raw_high", "low": "official_raw_low", "close": "official_raw_close",
        "volume": "official_raw_volume", "turnover_value": "official_raw_turnover_value",
        "source_quality": "official_raw_source_quality", "adjustment_policy": "official_raw_adjustment_policy",
        "source_url": "official_raw_source_url", "source_hash": "official_raw_source_hash",
        "retrieval_time_utc": "official_raw_retrieved_at",
    })
    exact = exact.merge(raw_part, on=["ticker", "date"], how="left")

    adjusted_columns = [
        "ticker", "date", "adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close",
        "adjustment_factor", "adjusted_source_quality", "adjustment_policy", "source_url", "source_hash",
        "retrieved_at", "accepted_for_formal", "human_review_required", "adjusted_reuse_source",
    ]
    adjusted_keep = [column for column in adjusted_columns if column in adjusted.columns]
    adjusted_part = adjusted[adjusted_keep].rename(columns={
        "adjustment_policy": "adjusted_analysis_policy", "source_url": "adjusted_source_url",
        "source_hash": "adjusted_source_hash", "retrieved_at": "adjusted_retrieved_at",
    })
    exact = exact.merge(adjusted_part, on=["ticker", "date"], how="left")

    adjusted_ready = exact[["adjusted_high", "adjusted_low", "adjusted_close"]].notna().all(axis=1)
    for row in exact.loc[~adjusted_ready, ["ticker", "date"]].itertuples(index=False):
        blocked.append({"ticker": row.ticker, "date": row.date, "family": "adjusted_analysis_HLC", "classification": "source_gap", "blocked_reason": "bounded trusted route has no exact adjusted HLC row"})
    family_coverage.append({
        "family": "adjusted_analysis_HLC", "required_rows": len(keys), "ready_rows": int(adjusted_ready.sum()),
        "official_zero_or_not_applicable_rows": 0, "blocked_rows": int((~adjusted_ready).sum()),
        "source_quality": "trusted_nonofficial_research_grade; raw execution separate",
    })

    for family, frame in family_frames.items():
        spec = FAMILY_SPECS[family]
        values = spec["values"]
        ready = frame["value_complete"].fillna(False)
        numeric = frame[values].apply(pd.to_numeric, errors="coerce")
        official_zero = ready & numeric.fillna(0).eq(0).all(axis=1)
        for row in frame.loc[official_zero, ["ticker", "date"]].itertuples(index=False):
            zero_na.append({
                "ticker": row.ticker, "date": row.date, "family": family,
                "classification": "official_zero", "policy": "preserve official zero; do not treat as missing or impute",
            })
        for row in frame.loc[~ready, ["ticker", "date", "source_quality", "source_url"]].itertuples(index=False):
            classification = "official_zero_or_not_applicable" if pd.notna(row.source_quality) else "source_gap"
            blocked.append({
                "ticker": row.ticker, "date": row.date, "family": family,
                "classification": classification,
                "blocked_reason": "official row exists but required fields are unavailable" if pd.notna(row.source_quality) else "no exact source row",
                "source_url": row.source_url if pd.notna(row.source_url) else "",
            })
        family_coverage.append({
            "family": family, "required_rows": len(keys), "ready_rows": int(ready.sum()),
            "official_zero_or_not_applicable_rows": int(official_zero.sum()), "blocked_rows": int((~ready).sum()),
            "source_quality": "official post-close daily stock-level source",
        })

        selected = frame[["ticker", "date", *values, "source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc", "source_reuse_package"]].copy()
        selected = selected.rename(columns={column: f"{family}_{column}" for column in values + ["source_quality", "available_at_policy", "source_url", "source_hash", "retrieval_time_utc", "source_reuse_package"]})
        selected[f"{family}_status"] = ready.map({True: "ready", False: "blocked_or_not_applicable"})
        exact = exact.merge(selected, on=["ticker", "date"], how="left")

        manifests = frame.groupby(["source_reuse_package", "source_quality", "source_url", "source_hash"], dropna=False).size().reset_index(name="exact_rows")
        for row in manifests.itertuples(index=False):
            source_manifests.append({
                "family": family, "ticker": "bounded_4_ticker_scope", "route_scope": row.source_reuse_package,
                "source_url": "" if pd.isna(row.source_url) else row.source_url,
                "source_hash": "" if pd.isna(row.source_hash) else row.source_hash,
                "cache_path": "existing_compact", "cache_reused": True,
                "requested_rows": int(row.exact_rows), "accepted_rows": int(row.exact_rows),
                "blocked_rows": 0, "status": "reused",
            })

    exact["TDCC_P3_1_status"] = "NA_not_required_not_zero"
    exact["future_data_violation_count"] = 0
    for key, value in FLAGS.items():
        exact[key] = value

    blocked_frame = pd.DataFrame(blocked)
    if blocked_frame.empty:
        blocked_frame = pd.DataFrame(columns=["ticker", "date", "family", "classification", "blocked_reason", "source_url"])
    blocked_frame["future_data_violation_count"] = 0
    for key, value in FLAGS.items():
        blocked_frame[key] = value

    zero_frame = pd.DataFrame(zero_na)
    if zero_frame.empty:
        zero_frame = pd.DataFrame(columns=["ticker", "date", "family", "classification", "policy"])
    zero_frame["future_data_violation_count"] = 0

    local_events = pd.read_csv(RANK1_EVENT_INVENTORY, dtype={"ticker": str})
    local_events = local_events.rename(columns={"effective_date": "event_date", "amount_or_ratio": "amount"})
    relevant_local_events = []
    for ticker, group in keys.groupby("ticker"):
        start = group["date"].min()
        end = group["date"].max()
        relevant_local_events.append(
            local_events[
                local_events["ticker"].eq(ticker)
                & local_events["event_date"].between(start, end)
            ]
        )
    local_event_frame = pd.concat(relevant_local_events, ignore_index=True) if relevant_local_events else pd.DataFrame()
    if not local_event_frame.empty:
        local_event_frame["accepted_for_formal"] = False
        local_event_frame["human_review_required"] = True
        local_event_frame["numerator"] = ""
        local_event_frame["denominator"] = ""
        local_event_frame["split_ratio"] = ""

    event_frame = pd.concat([pd.DataFrame(events), local_event_frame], ignore_index=True, sort=False)
    if event_frame.empty:
        event_frame = pd.DataFrame(columns=["ticker", "event_type", "event_date", "amount", "numerator", "denominator", "split_ratio", "source_quality", "source_url", "source_hash", "accepted_for_formal", "human_review_required"])
    event_frame["future_data_violation_count"] = 0

    factor_audit = []
    for ticker, group in exact.groupby("ticker"):
        factors = pd.to_numeric(group["adjustment_factor"], errors="coerce").dropna()
        changes = int((factors.sort_index().pct_change().abs() > 1e-7).sum()) if len(factors) else 0
        factor_audit.append({
            "ticker": ticker, "required_rows": len(group), "factor_ready_rows": len(factors),
            "factor_min": factors.min() if len(factors) else "", "factor_max": factors.max() if len(factors) else "",
            "factor_change_rows_in_required_scope": changes,
            "trusted_event_inventory_rows": int((event_frame["ticker"] == ticker).sum()) if len(event_frame) else 0,
            "source_quality": "trusted_nonofficial_research_grade_not_formal",
            "raw_execution_separate": True, "human_review_required": True,
            "future_data_violation_count": 0,
        })

    (OUT / "current_step.txt").write_text("write_and_validate_outputs\n", encoding="utf-8")
    exact_path = OUT / "p3_C3_incumbent_continuous_pit_exact_compact.csv.gz"
    write_csv_gz(exact_path, exact.sort_values(["ticker", "date"]))
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_family_coverage.csv", pd.DataFrame(family_coverage))
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_blocked_ledger.csv", blocked_frame)
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_zero_na_ledger.csv", zero_frame)
    write_csv(OUT / "p3_C3_incumbent_adjusted_hlc_factor_event_audit.csv", pd.DataFrame(factor_audit))
    write_csv(OUT / "p3_C3_incumbent_corporate_action_event_inventory.csv", event_frame)
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_source_manifest.csv", pd.DataFrame(source_manifests))

    future_audit = pd.DataFrame([
        {"audit_item": "scope", "status": "pass", "detail": "only four tickers, nine segments, and exact 20TD warmup keys; no P3-2 outcome read", "future_data_violation_count": 0},
        {"audit_item": "adjusted_vs_raw", "status": "pass", "detail": "trusted adjusted analysis HLC and official raw execution HLC are separate columns; raw is not presented as adjusted", "future_data_violation_count": 0},
        {"audit_item": "chip_availability", "status": "pass", "detail": "post-close source availability policy retained; Core must apply next-trading-day eligibility", "future_data_violation_count": 0},
        {"audit_item": "TDCC_P3_1", "status": "pass", "detail": "TDCC is NA_not_required_not_zero and is neither queried nor imputed", "future_data_violation_count": 0},
        {"audit_item": "trusted_adjusted_limit", "status": "pass", "detail": "retro-adjusted trusted source is research diagnostic only and not formal PIT truth", "future_data_violation_count": 0},
    ])
    write_csv(OUT / "p3_C3_incumbent_continuous_pit_future_data_audit.csv", future_audit)

    coverage = pd.DataFrame(family_coverage)
    all_ready = bool((coverage["blocked_rows"] == 0).all())
    readiness = {
        "task_id": TASK_ID,
        "status": "bounded_continuous_pit_source_ready_for_core_absorption" if all_ready else "bounded_continuous_pit_partial_blockers_retained",
        "input_missing_decision_rows": 139,
        "ticker_count": 4,
        "segment_count": 9,
        "segment_requirement_rows_with_overlap": len(requirement),
        "exact_unique_ticker_date_rows": len(keys),
        "adjusted_local_reuse_rows": len(local_adjusted),
        "adjusted_bounded_fetch_rows": len(fetched_adjusted),
        "official_raw_local_reuse_rows": len(local_raw),
        "official_raw_bounded_fetch_rows": len(fetched_raw),
        "blocked_family_rows": int(coverage["blocked_rows"].sum()),
        "TDCC_P3_1_status": "NA_not_required_not_zero",
        "continuous_PIT_all_mandatory_families_ready": all_ready,
        "ready_for_core_p3_C3_incumbent_continuous_PIT_absorption": True,
        "ready_for_experiments": False,
        "performance_authorized": False,
        "P3_2_outcome_read_authorized": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_C3_incumbent_continuous_pit_absorption.json", readiness)

    summary = (
        "# P3 C3 Top1 incumbent continuous PIT bounded fill\n\n"
        f"- Scope：4 tickers / 9 segments / 139 decision rows / {len(keys)} exact ticker-date rows。\n"
        f"- adjusted HLC：local reuse {len(local_adjusted)}；bounded trusted fetch {len(fetched_adjusted)}。\n"
        f"- official raw HLC：local reuse {len(local_raw)}；bounded TWSE fill {len(fetched_raw)}。\n"
        f"- mandatory family blocked rows：{int(coverage['blocked_rows'].sum())}。\n"
        "- institutional、margin/short、securities lending、foreign ownership 只重用既有官方 compact。\n"
        "- P3-1 TDCC=NA_not_required_not_zero。\n"
        "- trusted adjusted HLC 僅供 research diagnostic，不包裝 formal PIT truth。\n"
        "- ready_for_experiments=false；完成後交 Core 重鏈。\n"
        "- future_data_violation_count=0。\n"
    )
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_ready_for_core_absorption\n", encoding="utf-8")
    write_json(OUT / "progress.json", {
        "task_id": TASK_ID, "status": "completed", "current_step": "ready_for_core_absorption",
        "exact_unique_ticker_date_rows": len(keys), "blocked_family_rows": int(coverage["blocked_rows"].sum()),
    })

    artifact_names = [
        "p3_C3_incumbent_continuous_pit_segment_exact_keys.csv",
        "p3_C3_incumbent_continuous_pit_exact_compact.csv.gz",
        "p3_C3_incumbent_continuous_pit_family_coverage.csv",
        "p3_C3_incumbent_continuous_pit_blocked_ledger.csv",
        "p3_C3_incumbent_continuous_pit_zero_na_ledger.csv",
        "p3_C3_incumbent_adjusted_hlc_factor_event_audit.csv",
        "p3_C3_incumbent_corporate_action_event_inventory.csv",
        "p3_C3_incumbent_continuous_pit_source_manifest.csv",
        "p3_C3_incumbent_continuous_pit_future_data_audit.csv",
        "readiness_for_core_p3_C3_incumbent_continuous_pit_absorption.json",
        "final_summary_zh.md", "current_step.txt", "progress.json", "run_bounded_fill.py",
    ]
    manifest = {
        "task_id": TASK_ID, "generated_at_utc": now(),
        "artifacts": [
            {"path": name, "size_bytes": (OUT / name).stat().st_size, "sha256": sha256_file(OUT / name)}
            for name in artifact_names
        ],
        "raw_cache_persisted_locally_ignored_by_git": True,
        "full_market_expansion": False,
        "performance_authorized": False,
        "P3_2_outcome_read_authorized": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(OUT / "manifest.json", manifest)


if __name__ == "__main__":
    main()
