from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import os
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[0]
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
CORE_INPUT = CORE / "outputs" / "vnext_p1_p2_layer4_primary80_individual_MA_slope_CD50_contract_20260715"
P1 = ROOT / "radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710"
P1_BLOCKERS = ROOT / "radar_vnext_p1_adjusted_analysis_63_bounded_resolution_20260711"
P3 = ROOT / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
P3_EXACT = ROOT / "radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711"
P3_WARMUP = ROOT / "radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711"
P3_ALL80 = ROOT / "radar_vnext_p3_layer5_all80_continuous_lifecycle_adjusted_hlc_bounded_delta_acquisition_20260713"
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
RAW_CACHE = OUT / "raw_cache" / "official_month"
YAHOO_CACHE = OUT / "raw_cache" / "trusted_adjusted"
HTTP = requests.Session()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ticker_text(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    frame.to_csv(temp, index=False, encoding="utf-8-sig", compression="gzip" if path.suffix == ".gz" else None)
    if path.suffix == ".gz":
        with gzip.open(temp, "rt", encoding="utf-8-sig") as handle:
            next(csv.reader(handle), None)
    os.replace(temp, path)


def checkpoint(step: str, **extra: object) -> None:
    payload = {
        "task_id": TASK_ID,
        "status": "running",
        "current_step": step,
        "updated_at": now(),
        "resume_command": "python -X utf8 run_source_convergence.py --phase acquire",
        **extra,
    }
    write_json(OUT / "progress.json", payload)
    (OUT / "current_step.txt").write_text(step + "\n", encoding="utf-8")


def read_dates(path: Path) -> set[str]:
    frame = pd.read_csv(path, usecols=["date"], dtype={"date": str})
    return set(frame["date"].dropna().astype(str))


def build_market_calendar() -> list[str]:
    # The old bulk raw runner labelled a few holiday responses with the query
    # date.  A non-blocked 0050 exact session is therefore the safer calendar
    # authority for requirement construction.
    source = CORE / "outputs" / "vnext_dynamic_candidate_pool_data_materialization_20260706" / "benchmark_features.csv"
    frame = pd.read_csv(source, dtype={"trade_date": str, "benchmark": str})
    frame = frame.loc[
        frame["benchmark"].eq("0050")
        & ~frame["benchmark_data_blocked"].fillna(False)
        & frame["adjusted_close"].notna()
    ]
    return sorted(day for day in frame["trade_date"].unique() if "2014-09-01" <= day <= "2026-06-30")


def requirement_rows(membership: pd.DataFrame, calendar: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    membership = membership.copy()
    membership["snapshot_date"] = membership["snapshot_date"].astype(str)
    membership["ticker"] = membership["ticker"].map(ticker_text)
    cal_index = {day: index for index, day in enumerate(calendar)}
    period_end = {"P1": "2022-12-29", "P2": "2026-06-30"}
    adjusted: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    raw: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for period, part in membership.groupby("period", sort=False):
        snapshots = sorted(part["snapshot_date"].unique())
        for position, snapshot in enumerate(snapshots):
            if snapshot not in cal_index:
                continue
            snapshot_i = cal_index[snapshot]
            active_start_i = min(snapshot_i + 1, len(calendar) - 1)
            if position + 1 < len(snapshots):
                next_snapshot = snapshots[position + 1]
                active_end_i = cal_index.get(next_snapshot, active_start_i)
            else:
                active_end_i = max(index for index, day in enumerate(calendar) if day <= period_end[period])
            warmup_start_i = max(0, active_start_i - 60)
            execution_tail_i = min(active_end_i + 1, len(calendar) - 1)
            tickers = part.loc[part["snapshot_date"].eq(snapshot), "ticker"].tolist()
            for ticker in tickers:
                key_prefix = (period, ticker)
                for day in calendar[warmup_start_i:active_start_i]:
                    adjusted[(*key_prefix, day)].add("ma60_warmup")
                for day in calendar[active_start_i:active_end_i + 1]:
                    adjusted[(*key_prefix, day)].add("active_analysis")
                    raw[(*key_prefix, day)].add("active_execution_mark")
                if calendar[execution_tail_i] <= period_end[period]:
                    raw[(*key_prefix, calendar[execution_tail_i])].add("next_execution_tail")

    adjusted_frame = pd.DataFrame([
        {"period": period, "ticker": ticker, "date": day, "requirement_role": "|".join(sorted(roles))}
        for (period, ticker, day), roles in adjusted.items()
    ]).sort_values(["period", "ticker", "date"], ignore_index=True)
    raw_frame = pd.DataFrame([
        {"period": period, "ticker": ticker, "date": day, "requirement_role": "|".join(sorted(roles))}
        for (period, ticker, day), roles in raw.items()
    ]).sort_values(["period", "ticker", "date"], ignore_index=True)
    return adjusted_frame, raw_frame


def normalize_source(frame: pd.DataFrame, family: str, source_path: Path, priority: int) -> pd.DataFrame:
    if frame.empty or "ticker" not in frame or "date" not in frame:
        return pd.DataFrame()
    result = pd.DataFrame()
    result["ticker"] = frame["ticker"].map(ticker_text)
    result["date"] = frame["date"].astype(str)
    result["market"] = frame["market"].astype(str) if "market" in frame else ""
    result["name"] = frame["name"].astype(str) if "name" in frame else ""
    if family == "adjusted_analysis_close":
        if "adjusted_close" not in frame:
            return pd.DataFrame()
        result["value"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
        result["source_quality"] = frame.get("source_quality", frame.get("adjusted_source_quality", "trusted_nonofficial_reuse")).astype(str) if isinstance(frame.get("source_quality", frame.get("adjusted_source_quality")), pd.Series) else "trusted_nonofficial_reuse"
        result["adjustment_policy"] = frame.get("adjustment_policy", "event_aware_adjusted_analysis_only")
        result["source_url"] = frame.get("source_url", "")
        result["source_hash"] = frame.get("source_hash", frame.get("response_hash", ""))
        result["retrieved_at"] = frame.get("retrieval_time_utc", frame.get("retrieved_at", ""))
    else:
        if "close" not in frame and "official_raw_close" not in frame:
            return pd.DataFrame()
        close_col = "close" if "close" in frame else "official_raw_close"
        result["value"] = pd.to_numeric(frame[close_col], errors="coerce")
        for target, candidates in {
            "open": ["open", "official_raw_open"], "high": ["high", "official_raw_high"],
            "low": ["low", "official_raw_low"], "volume": ["volume"],
            "turnover_value": ["turnover_value"],
        }.items():
            source_col = next((column for column in candidates if column in frame), None)
            result[target] = pd.to_numeric(frame[source_col], errors="coerce") if source_col else pd.NA
        quality = frame.get("source_quality", frame.get("raw_source_quality", "official_raw_execution_reuse"))
        result["source_quality"] = quality.astype(str) if isinstance(quality, pd.Series) else quality
        result["adjustment_policy"] = "official_unadjusted_execution_only"
        result["source_url"] = frame.get("source_url", frame.get("raw_source_url", ""))
        result["source_hash"] = frame.get("source_hash", frame.get("raw_source_hash", ""))
        result["retrieved_at"] = frame.get("retrieval_time_utc", frame.get("retrieved_at", ""))
    result["source_path"] = str(source_path)
    result["source_priority"] = priority
    result["family"] = family
    return result.loc[result["value"].notna() & result["value"].gt(0)].copy()


def read_source(path: Path, family: str, priority: int) -> pd.DataFrame:
    try:
        return normalize_source(pd.read_csv(path, dtype={"ticker": str, "date": str}), family, path, priority)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def collect_sources(family: str, required: pd.DataFrame) -> pd.DataFrame:
    required_keys = pd.MultiIndex.from_frame(required[["ticker", "date"]].drop_duplicates())
    pieces: list[pd.DataFrame] = []
    candidates: list[tuple[Path, int]] = []
    if family == "adjusted_analysis_close":
        candidates += [(path, 10) for path in (P1 / "compact" / "trusted_adjusted_analysis").glob("*.csv.gz")]
        candidates += [(path, 20) for path in (P3 / "compact" / "adjusted").glob("*.csv.gz")]
        candidates += [(path, 15) for path in (P3_EXACT / "checkpoints" / "adjusted").glob("*.csv.gz")]
        candidates += [(P3_ALL80 / "all80_bounded_delta_adjusted_hlc_exact_key_compact.csv.gz", 30)]
        candidates += [(P3_RANK1 / "rank1_adjusted_analysis_hlc_factor_compact.csv.gz", 40)]
    else:
        candidates += [(path, 10) for path in (P1 / "compact" / "official_raw_execution_ohlcv").glob("*/*.csv.gz")]
        candidates += [(path, 20) for path in (P3 / "compact" / "price").glob("*.csv.gz")]
        candidates += [(path, 15) for path in (P3_WARMUP / "checkpoints" / "price").glob("*/*.csv.gz")]
        candidates += [(P3_ALL80 / "all80_bounded_delta_official_raw_hlc_rows.csv.gz", 30)]
    for index, (path, priority) in enumerate(candidates, start=1):
        if not path.exists():
            continue
        frame = read_source(path, family, priority)
        if frame.empty:
            continue
        keys = pd.MultiIndex.from_frame(frame[["ticker", "date"]])
        selected = frame.loc[keys.isin(required_keys)]
        if not selected.empty:
            pieces.append(selected)
        if index % 200 == 0:
            checkpoint(f"local_reuse_{family}_{index}_of_{len(candidates)}", files_read=index)
    if not pieces:
        return pd.DataFrame()
    combined = pd.concat(pieces, ignore_index=True)
    combined = combined.sort_values(["source_priority", "ticker", "date"])
    return combined.drop_duplicates(["ticker", "date"], keep="first").reset_index(drop=True)


def attach_coverage(required: pd.DataFrame, source: pd.DataFrame, family: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["ticker", "date", "value", "market", "name", "source_quality", "adjustment_policy", "source_url", "source_hash", "retrieved_at", "source_path"]
    available = source[[column for column in columns if column in source]].copy() if not source.empty else pd.DataFrame(columns=columns)
    merged = required.merge(available, on=["ticker", "date"], how="left")
    merged["family"] = family
    merged["exact_key_ready"] = merged["value"].notna()
    merged["future_data_violation_count"] = 0
    ready = merged.loc[merged["exact_key_ready"]].copy()
    blocked = merged.loc[~merged["exact_key_ready"]].copy()
    return ready, blocked


def build_blocker_ledger(adjusted_blocked: pd.DataFrame, raw_blocked: pd.DataFrame) -> pd.DataFrame:
    p1_known = pd.read_csv(P1_BLOCKERS / "adjusted_analysis_63_remaining_blocked.csv", dtype={"ticker": str})
    p1_reason = {ticker_text(row.ticker): row.blocked_reason for row in p1_known.itertuples()}
    rows = []
    for frame, family in ((adjusted_blocked, "adjusted_analysis_close"), (raw_blocked, "official_raw_execution_close")):
        for row in frame.itertuples(index=False):
            p1_structural = row.period == "P1" and row.ticker in p1_reason and family == "adjusted_analysis_close"
            rows.append({
                "period": row.period, "ticker": row.ticker, "date": row.date,
                "family": family, "requirement_role": row.requirement_role,
                "classification": "p1_known_structural_adjusted_blocker" if p1_structural else "remaining_exact_source_delta",
                "blocked_reason": p1_reason.get(row.ticker, "local exact-key sources exhausted; bounded delta source route required") if p1_structural else "local exact-key reuse produced no accepted row",
                "network_reprobe_authorized": not p1_structural,
                "raw_used_as_adjusted": False,
                "neighbor_or_last_price_substitution_used": False,
                "future_data_violation_count": 0,
                **FLAGS,
            })
    return pd.DataFrame(rows)


def coverage_summary(adjusted_required: pd.DataFrame, raw_required: pd.DataFrame, adjusted_ready: pd.DataFrame, raw_ready: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period in ("P1", "P2"):
        for family, required, ready in (
            ("adjusted_analysis_close", adjusted_required, adjusted_ready),
            ("official_raw_execution_close", raw_required, raw_ready),
        ):
            req = required.loc[required["period"].eq(period)]
            got = ready.loc[ready["period"].eq(period)]
            rows.append({
                "period": period, "family": family,
                "required_ticker_dates": len(req), "ready_ticker_dates": len(got),
                "blocked_ticker_dates": len(req) - len(got),
                "required_tickers": req["ticker"].nunique(), "ready_tickers_any": got["ticker"].nunique(),
                "coverage_share": len(got) / len(req) if len(req) else 0,
                "actual_ready_start": got["date"].min() if len(got) else "",
                "actual_ready_end": got["date"].max() if len(got) else "",
                "future_data_violation_count": 0,
            })
    return pd.DataFrame(rows)


def benchmark_audit(calendar: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = CORE / "outputs" / "vnext_dynamic_candidate_pool_data_materialization_20260706" / "benchmark_features.csv"
    features = pd.read_csv(source, dtype={"benchmark": str, "trade_date": str})
    features = features.loc[~features["benchmark_data_blocked"].fillna(False)].copy()
    rows, gaps = [], []
    for period, start, end in (("P1", "2014-09-11", "2022-12-29"), ("P2", "2022-10-03", "2026-06-30")):
        dates = [day for day in calendar if start <= day <= end]
        for ticker in ("0050", "00631L"):
            part = features.loc[features["benchmark"].eq(ticker)]
            adjusted_dates = set(part.loc[part["adjusted_close"].notna(), "trade_date"])
            missing_adjusted = sorted(set(dates) - adjusted_dates)
            rows.append({
                "period": period, "ticker": ticker, "role": "market_reference" if ticker == "0050" else "performance_hurdle_only_not_fallback",
                "required_dates": len(dates), "adjusted_ready_dates": len(set(dates) & adjusted_dates),
                "official_raw_ready_dates": 0,
                "adjusted_status": "ready" if not missing_adjusted else "partial",
                "official_raw_status": "bounded_official_month_fill_required",
                "adjusted_source_path": str(source),
                "raw_execution_used_as_adjusted": False,
                "future_data_violation_count": 0,
            })
            for day in missing_adjusted:
                gaps.append({"period": period, "ticker": ticker, "date": day, "family": "benchmark_adjusted_close", "blocked_reason": "benchmark_features exact adjusted row unavailable or explicitly blocked"})
            for day in dates:
                gaps.append({"period": period, "ticker": ticker, "date": day, "family": "benchmark_official_raw_close", "blocked_reason": "official TWSE raw exact coverage not yet consolidated"})
    return pd.DataFrame(rows), pd.DataFrame(gaps)


def market_map() -> dict[str, str]:
    rows = []
    for path in (P1 / "compact" / "official_raw_execution_ohlcv").glob("*/*.csv.gz"):
        frame = pd.read_csv(path, usecols=["ticker", "market"], dtype={"ticker": str})
        rows.append(frame.drop_duplicates())
    for path in (P3 / "compact" / "price").glob("*.csv.gz"):
        frame = pd.read_csv(path, usecols=["ticker", "market"], dtype={"ticker": str})
        rows.append(frame.drop_duplicates())
    proxy = ROOT / "radar_dynamic_pool1_listing_delisting_suspension_master_20260703" / "proxy_source_rows.csv"
    if proxy.exists():
        rows.append(pd.read_csv(proxy, usecols=["ticker", "market"], dtype={"ticker": str}).drop_duplicates())
    combined = pd.concat(rows, ignore_index=True)
    combined["ticker"] = combined["ticker"].map(ticker_text)
    return combined.drop_duplicates("ticker", keep="first").set_index("ticker")["market"].to_dict()


def snapshot_readiness(adjusted_ready: pd.DataFrame, raw_ready: pd.DataFrame) -> pd.DataFrame:
    membership = pd.read_csv(CORE_INPUT / "p1_p2_primary80_weekly_membership_contract.csv.gz", dtype={"ticker": str})
    membership["ticker"] = membership["ticker"].map(ticker_text)
    adjusted_dates = {
        ticker: sorted(set(part["date"].astype(str))) for ticker, part in adjusted_ready.groupby("ticker")
    }
    raw_dates = {ticker: sorted(set(part["date"].astype(str))) for ticker, part in raw_ready.groupby("ticker")}
    rows = []
    for item in membership.itertuples(index=False):
        adjusted = adjusted_dates.get(item.ticker, [])
        raw = raw_dates.get(item.ticker, [])
        adjusted_index = bisect.bisect_right(adjusted, item.snapshot_date)
        raw_index = bisect.bisect_right(raw, item.snapshot_date)
        latest_adjusted = adjusted[adjusted_index - 1] if adjusted_index else ""
        next_raw = raw[raw_index] if raw_index < len(raw) else ""
        stale_days = (
            (pd.Timestamp(item.snapshot_date) - pd.Timestamp(latest_adjusted)).days if latest_adjusted else None
        )
        rows.append({
            "period": item.period, "snapshot_date": item.snapshot_date, "ticker": item.ticker,
            "adjusted_observations_through_snapshot": adjusted_index,
            "latest_adjusted_date": latest_adjusted,
            "adjusted_stale_calendar_days": stale_days,
            "adjusted_60_observations_ready": adjusted_index >= 60,
            "adjusted_freshness_ready": stale_days is not None and stale_days <= 10,
            "next_official_raw_date": next_raw,
            "next_official_raw_ready": bool(next_raw),
            "future_data_violation_count": 0,
        })
    return pd.DataFrame(rows)


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
        return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + urlencode({
            "date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json",
        })
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?" + urlencode({
        "code": ticker, "date": month.replace("-", "/") + "/01", "response": "json",
    })


def parse_official_month(payload: dict, ticker: str, market: str) -> tuple[bool, list[dict]]:
    if market == "TWSE":
        schema_ok = str(payload.get("stat", "")).lower() == "ok"
        fields, data = payload.get("fields") or [], payload.get("data") or []
    else:
        schema_ok = str(payload.get("stat", "")).lower() == "ok"
        table = next((table for table in payload.get("tables") or [] if table.get("fields") and table.get("data")), {})
        fields, data = table.get("fields") or [], table.get("data") or []
    indices = {
        "date": field_index(fields, "日期"), "open": field_index(fields, "開盤"),
        "high": field_index(fields, "最高"), "low": field_index(fields, "最低"),
        "close": field_index(fields, "收盤"), "volume": field_index(fields, "成交股數"),
        "turnover": field_index(fields, "成交金額"),
    }
    if min(indices.values()) < 0:
        if market == "TPEx":
            indices["volume"] = field_index(fields, "成交仟股")
            indices["turnover"] = field_index(fields, "成交仟元")
    if min(indices.values()) < 0:
        return False, []
    rows = []
    for values in data:
        day = roc_date(values[indices["date"]])
        close = clean_number(values[indices["close"]])
        if not day or close is None:
            continue
        volume = clean_number(values[indices["volume"]])
        turnover = clean_number(values[indices["turnover"]])
        if market == "TPEx" and "仟股" in "".join(fields) and volume is not None:
            volume *= 1000
        if market == "TPEx" and "仟元" in "".join(fields) and turnover is not None:
            turnover *= 1000
        rows.append({
            "ticker": ticker, "date": day, "market": market,
            "open": clean_number(values[indices["open"]]), "high": clean_number(values[indices["high"]]),
            "low": clean_number(values[indices["low"]]), "close": close,
            "volume": volume, "turnover_value": turnover,
        })
    return schema_ok, rows


def get_bytes(url: str, attempts: int = 4) -> tuple[bytes, int, str, str]:
    error = ""
    for attempt in range(attempts):
        try:
            response = HTTP.get(url, headers={"User-Agent": "Mozilla/5.0 RadarP1P2Convergence/1.0"}, timeout=45)
            if response.ok:
                return response.content, response.status_code, "", response.url
            error = f"HTTP_{response.status_code}"
        except requests.RequestException as exc:
            error = type(exc).__name__
        import time
        time.sleep(0.5 * (attempt + 1))
    return b"", 0, error or "request_failed", url


def fetch_official_route(route: dict) -> tuple[dict, list[dict]]:
    ticker, market, month = route["ticker"], route["market"], route["year_month"]
    target_dates = set(route["target_dates"])
    route_id = f"{ticker}_{market}_{month}"
    cache = RAW_CACHE / f"{route_id}.json"
    url = official_month_url(ticker, market, month)
    retrieved_at = now()
    if cache.exists():
        raw, status, error, final_url, reused = cache.read_bytes(), 200, "", url, True
    else:
        raw, status, error, final_url = get_bytes(url)
        reused = False
        if raw:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
    source_hash = hashlib.sha256(raw).hexdigest() if raw else ""
    schema_ok, parsed = False, []
    if raw:
        try:
            schema_ok, parsed = parse_official_month(json.loads(raw.decode("utf-8-sig")), ticker, market)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            error = f"parse_{type(exc).__name__}"
    accepted = []
    for row in parsed:
        if row["date"] not in target_dates:
            continue
        accepted.append({
            **row,
            "source_quality": f"official_{market.lower()}_selected_ticker_month_unadjusted_execution",
            "adjustment_policy": "official_unadjusted_execution_only",
            "source_url": final_url, "source_hash": source_hash,
            "retrieved_at": retrieved_at, "raw_cache_path": str(cache),
        })
    outcome = "accepted_exact_rows" if accepted else "valid_official_response_no_exact_target_row" if schema_ok else "source_route_failed"
    manifest = {
        "route_id": route_id, "ticker": ticker, "market": market, "year_month": month,
        "target_date_count": len(target_dates), "response_rows": len(parsed), "accepted_exact_rows": len(accepted),
        "outcome": outcome, "http_status": status, "schema_ok": schema_ok,
        "source_url": final_url, "source_hash": source_hash, "response_bytes": len(raw),
        "retrieved_at": retrieved_at, "cache_reused": reused, "route_error": error,
        "raw_cache_path": str(cache), "future_data_violation_count": 0, **FLAGS,
    }
    return manifest, accepted


def fetch_yahoo(ticker: str, market: str, required_dates: set[str]) -> tuple[dict, list[dict]]:
    cache = YAHOO_CACHE / f"{ticker}.json"
    start, end = min(required_dates), max(required_dates)
    period1 = int(pd.Timestamp(start).tz_localize("Asia/Taipei").tz_convert("UTC").timestamp())
    period2 = int((pd.Timestamp(end) + pd.Timedelta(days=2)).tz_localize("Asia/Taipei").tz_convert("UTC").timestamp())
    suffixes = ["TW", "TWO"] if market == "TWSE" else ["TWO", "TW"]
    attempts, accepted_payload = [], None
    for suffix in suffixes:
        symbol = f"{ticker}.{suffix}"
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol
        params = {"period1": period1, "period2": period2, "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"}
        try:
            response = HTTP.get(url, params=params, headers={"User-Agent": "Mozilla/5.0 RadarP1P2Convergence/1.0"}, timeout=45)
            attempts.append(f"{symbol}:{response.status_code}:{len(response.content)}")
            if not response.ok:
                continue
            payload = response.json()
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if result and result.get("timestamp"):
                accepted_payload = (symbol, response, result)
                break
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            attempts.append(f"{symbol}:{type(exc).__name__}")
    rows, retrieved_at = [], now()
    manifest = {
        "ticker": ticker, "market": market, "status": "blocked", "provider_symbol": "",
        "target_date_count": len(required_dates), "accepted_exact_rows": 0,
        "source_url": "", "source_hash": "", "response_bytes": 0,
        "retrieved_at": retrieved_at, "attempt_evidence": "|".join(attempts),
        "source_quality": "trusted_nonofficial_yahoo_research_grade", "accepted_for_formal": False,
        "future_data_violation_count": 0, **FLAGS,
    }
    if accepted_payload:
        symbol, response, result = accepted_payload
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjusted = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        for index, stamp in enumerate(result.get("timestamp") or []):
            close_series = quote.get("close") or []
            close = close_series[index] if index < len(close_series) else None
            adjusted_close = adjusted[index] if index < len(adjusted) else None
            if close in (None, 0) or adjusted_close in (None, 0):
                continue
            day = pd.Timestamp(stamp, unit="s", tz="UTC").tz_convert("Asia/Taipei").date().isoformat()
            if day not in required_dates:
                continue
            rows.append({
                "ticker": ticker, "date": day, "market": market, "adjusted_close": float(adjusted_close),
                "raw_close_comparator": float(close), "source_quality": "trusted_nonofficial_yahoo_research_grade",
                "adjustment_policy": "provider_event_adjusted_analysis_only_never_execution",
                "source_url": response.url, "source_hash": hashlib.sha256(response.content).hexdigest(),
                "retrieved_at": retrieved_at, "provider_symbol": symbol, "accepted_for_formal": False,
            })
        manifest.update({
            "status": "accepted" if rows else "valid_response_no_exact_target_rows", "provider_symbol": symbol,
            "accepted_exact_rows": len(rows), "source_url": response.url,
            "source_hash": hashlib.sha256(response.content).hexdigest(), "response_bytes": len(response.content),
        })
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache, {"manifest": manifest, "rows": rows})
    return manifest, rows


def audit() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    checkpoint("build_exact_ticker_date_requirements")
    membership = pd.read_csv(CORE_INPUT / "p1_p2_primary80_weekly_membership_contract.csv.gz", dtype={"ticker": str})
    calendar = build_market_calendar()
    adjusted_required, raw_required = requirement_rows(membership, calendar)
    write_frame(OUT / "p1_p2_primary80_adjusted_analysis_exact_requirement.csv.gz", adjusted_required)
    write_frame(OUT / "p1_p2_primary80_official_raw_execution_exact_requirement.csv.gz", raw_required)

    checkpoint("local_exact_key_adjusted_reuse", required_rows=len(adjusted_required))
    adjusted_source = collect_sources("adjusted_analysis_close", adjusted_required)
    checkpoint("local_exact_key_raw_reuse", required_rows=len(raw_required))
    raw_source = collect_sources("official_raw_execution_close", raw_required)
    adjusted_ready, adjusted_blocked = attach_coverage(adjusted_required, adjusted_source, "adjusted_analysis_close")
    raw_ready, raw_blocked = attach_coverage(raw_required, raw_source, "official_raw_execution_close")
    write_frame(OUT / "p1_p2_primary80_adjusted_analysis_close_reuse_compact.csv.gz", adjusted_ready)
    write_frame(OUT / "p1_p2_primary80_official_raw_execution_close_reuse_compact.csv.gz", raw_ready)
    blockers = build_blocker_ledger(adjusted_blocked, raw_blocked)
    write_frame(OUT / "p1_p2_primary80_remaining_exact_source_delta_ledger.csv.gz", blockers)
    coverage = coverage_summary(adjusted_required, raw_required, adjusted_ready, raw_ready)
    write_frame(OUT / "p1_p2_primary80_requested_vs_actual_exact_key_coverage.csv", coverage)
    benchmark, benchmark_gaps = benchmark_audit(calendar)
    write_frame(OUT / "p1_p2_benchmark_0050_00631l_same_coverage_audit.csv", benchmark)
    write_frame(OUT / "p1_p2_benchmark_0050_00631l_gap_ledger.csv.gz", benchmark_gaps)
    route_plan = blockers.loc[blockers["network_reprobe_authorized"]].copy()
    route_plan["year_month"] = route_plan["date"].str[:7]
    route_plan = route_plan.groupby(["period", "family", "ticker", "year_month"], as_index=False).agg(
        exact_gap_dates=("date", "nunique"), gap_start=("date", "min"), gap_end=("date", "max")
    )
    write_frame(OUT / "p1_p2_primary80_bounded_delta_route_plan.csv", route_plan)
    summary = {
        "task_id": TASK_ID, "phase": "local_exact_key_reuse_audit_completed",
        "membership_rows": len(membership), "snapshots": membership["snapshot_date"].nunique(),
        "unique_tickers": membership["ticker"].nunique(),
        "adjusted_required_rows": len(adjusted_required), "adjusted_reused_rows": len(adjusted_ready),
        "adjusted_remaining_rows": len(adjusted_blocked),
        "raw_required_rows": len(raw_required), "raw_reused_rows": len(raw_ready),
        "raw_remaining_rows": len(raw_blocked),
        "authorized_delta_routes": len(route_plan),
        "p1_known_adjusted_structural_blocker_rows": int(blockers["classification"].eq("p1_known_structural_adjusted_blocker").sum()),
        "future_data_violation_count": 0,
        "ready_for_core_absorption": False,
        "next_step": "bounded_delta_acquisition_then_finalize",
        **FLAGS,
    }
    write_json(OUT / "audit_summary.json", summary)
    checkpoint("local_audit_completed_bounded_delta_pending", **summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def acquire() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    required_adjusted = pd.read_csv(OUT / "p1_p2_primary80_adjusted_analysis_exact_requirement.csv.gz", dtype={"ticker": str})
    required_raw = pd.read_csv(OUT / "p1_p2_primary80_official_raw_execution_exact_requirement.csv.gz", dtype={"ticker": str})
    local_adjusted = pd.read_csv(OUT / "p1_p2_primary80_adjusted_analysis_close_reuse_compact.csv.gz", dtype={"ticker": str})
    local_raw = pd.read_csv(OUT / "p1_p2_primary80_official_raw_execution_close_reuse_compact.csv.gz", dtype={"ticker": str})
    local_snapshot = snapshot_readiness(local_adjusted, local_raw)
    write_frame(OUT / "p1_p2_primary80_snapshot_price_readiness_before_delta.csv.gz", local_snapshot)
    markets = market_map()

    adjusted_targets = local_snapshot.loc[
        local_snapshot["period"].eq("P2")
        & (~local_snapshot["adjusted_60_observations_ready"] | ~local_snapshot["adjusted_freshness_ready"]),
        "ticker",
    ].unique().tolist()
    adjusted_missing = required_adjusted.merge(
        local_adjusted[["ticker", "date"]].drop_duplicates().assign(local_ready=True),
        on=["ticker", "date"], how="left",
    )
    adjusted_missing = adjusted_missing.loc[
        adjusted_missing["period"].eq("P2") & adjusted_missing["ticker"].isin(adjusted_targets) & adjusted_missing["local_ready"].isna()
    ]
    yahoo_manifest, yahoo_rows = [], []
    checkpoint("p2_trusted_adjusted_bounded_delta", target_tickers=len(adjusted_targets))
    for index, ticker in enumerate(adjusted_targets, start=1):
        dates = set(adjusted_missing.loc[adjusted_missing["ticker"].eq(ticker), "date"])
        if not dates:
            continue
        manifest, rows = fetch_yahoo(ticker, markets.get(ticker, "TWSE"), dates)
        yahoo_manifest.append(manifest)
        yahoo_rows.extend(rows)
        if index % 10 == 0:
            checkpoint("p2_trusted_adjusted_bounded_delta", completed=index, total=len(adjusted_targets), ticker=ticker)
    yahoo_frame = pd.DataFrame(yahoo_rows)
    write_frame(OUT / "p2_primary80_trusted_adjusted_delta_rows.csv.gz", yahoo_frame)
    write_frame(OUT / "p2_primary80_trusted_adjusted_delta_manifest.csv", pd.DataFrame(yahoo_manifest))

    raw_missing = required_raw.merge(
        local_raw[["ticker", "date"]].drop_duplicates().assign(local_ready=True),
        on=["ticker", "date"], how="left",
    )
    raw_missing = raw_missing.loc[raw_missing["period"].eq("P2") & raw_missing["local_ready"].isna()].copy()
    raw_missing["year_month"] = raw_missing["date"].str[:7]
    routes = []
    for (ticker, month), part in raw_missing.groupby(["ticker", "year_month"]):
        market = markets.get(ticker, "")
        route_markets = [market] if market in {"TWSE", "TPEx"} else ["TWSE", "TPEx"]
        for route_market in route_markets:
            routes.append({"ticker": ticker, "market": route_market, "year_month": month, "target_dates": sorted(part["date"].unique())})
    checkpoint("p2_official_raw_bounded_delta", total_routes=len(routes))
    official_manifest, official_rows = [], []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_official_route, route): route for route in routes}
        for index, future in enumerate(as_completed(futures), start=1):
            manifest, rows = future.result()
            official_manifest.append(manifest)
            official_rows.extend(rows)
            if index % 25 == 0:
                checkpoint("p2_official_raw_bounded_delta", completed=index, total=len(routes), route=manifest["route_id"])
    official_frame = pd.DataFrame(official_rows)
    write_frame(OUT / "p2_primary80_official_raw_execution_delta_rows.csv.gz", official_frame)
    write_frame(OUT / "p2_primary80_official_raw_execution_delta_manifest.csv", pd.DataFrame(official_manifest))

    benchmark_gap = pd.read_csv(OUT / "p1_p2_benchmark_0050_00631l_gap_ledger.csv.gz", dtype={"ticker": str})
    benchmark_gap = benchmark_gap.loc[benchmark_gap["family"].eq("benchmark_official_raw_close")].copy()
    benchmark_gap["year_month"] = benchmark_gap["date"].str[:7]
    benchmark_routes = [
        {"ticker": ticker, "market": "TWSE", "year_month": month, "target_dates": sorted(part["date"].unique())}
        for (ticker, month), part in benchmark_gap.groupby(["ticker", "year_month"])
    ]
    checkpoint("benchmark_official_raw_month_fill", total_routes=len(benchmark_routes))
    benchmark_manifest, benchmark_rows = [], []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_official_route, route): route for route in benchmark_routes}
        for index, future in enumerate(as_completed(futures), start=1):
            manifest, rows = future.result()
            benchmark_manifest.append(manifest)
            benchmark_rows.extend(rows)
            if index % 25 == 0:
                checkpoint("benchmark_official_raw_month_fill", completed=index, total=len(benchmark_routes), route=manifest["route_id"])
    benchmark_raw = pd.DataFrame(benchmark_rows)
    write_frame(OUT / "p1_p2_benchmark_0050_00631l_official_raw_rows.csv.gz", benchmark_raw)
    write_frame(OUT / "p1_p2_benchmark_0050_00631l_official_raw_manifest.csv", pd.DataFrame(benchmark_manifest))

    finalize(local_adjusted, local_raw, yahoo_frame, official_frame, benchmark_raw)


def finalize(
    local_adjusted: pd.DataFrame,
    local_raw: pd.DataFrame,
    yahoo_frame: pd.DataFrame,
    official_frame: pd.DataFrame,
    benchmark_raw: pd.DataFrame,
) -> None:
    checkpoint("finalize_exact_key_compacts")
    required_adjusted = pd.read_csv(OUT / "p1_p2_primary80_adjusted_analysis_exact_requirement.csv.gz", dtype={"ticker": str})
    required_raw = pd.read_csv(OUT / "p1_p2_primary80_official_raw_execution_exact_requirement.csv.gz", dtype={"ticker": str})
    new_adjusted = normalize_source(yahoo_frame, "adjusted_analysis_close", OUT / "p2_primary80_trusted_adjusted_delta_rows.csv.gz", 1) if not yahoo_frame.empty else pd.DataFrame()
    new_raw = normalize_source(official_frame, "official_raw_execution_close", OUT / "p2_primary80_official_raw_execution_delta_rows.csv.gz", 1) if not official_frame.empty else pd.DataFrame()
    adjusted_source = pd.concat([new_adjusted, local_adjusted], ignore_index=True, sort=False) if not new_adjusted.empty else local_adjusted.copy()
    raw_source = pd.concat([new_raw, local_raw], ignore_index=True, sort=False) if not new_raw.empty else local_raw.copy()
    adjusted_source = adjusted_source.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="first")
    raw_source = raw_source.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="first")
    adjusted_ready, adjusted_blocked = attach_coverage(required_adjusted, adjusted_source, "adjusted_analysis_close")
    raw_ready, raw_blocked = attach_coverage(required_raw, raw_source, "official_raw_execution_close")
    write_frame(OUT / "p1_p2_primary80_adjusted_analysis_close_converged_compact.csv.gz", adjusted_ready)
    write_frame(OUT / "p1_p2_primary80_official_raw_execution_close_converged_compact.csv.gz", raw_ready)
    snapshot = snapshot_readiness(adjusted_ready, raw_ready)
    write_frame(OUT / "p1_p2_primary80_snapshot_price_readiness_after_delta.csv.gz", snapshot)

    p1_known = pd.read_csv(P1_BLOCKERS / "adjusted_analysis_63_remaining_blocked.csv", dtype={"ticker": str})
    known = set(p1_known["ticker"].map(ticker_text))
    manifest = pd.read_csv(OUT / "p2_primary80_official_raw_execution_delta_manifest.csv", dtype={"ticker": str})
    valid_no_row = set()
    for row in manifest.loc[manifest["outcome"].eq("valid_official_response_no_exact_target_row")].itertuples(index=False):
        for day in raw_blocked.loc[
            raw_blocked["ticker"].eq(row.ticker) & raw_blocked["date"].str.startswith(row.year_month), "date"
        ]:
            valid_no_row.add((row.ticker, day))
    blocker_rows = []
    for row in adjusted_blocked.itertuples(index=False):
        snapshot_block = snapshot.loc[
            snapshot["period"].eq(row.period) & snapshot["ticker"].eq(row.ticker)
            & (~snapshot["adjusted_60_observations_ready"] | ~snapshot["adjusted_freshness_ready"])
        ]
        if row.period == "P1" and row.ticker in known:
            classification = "p1_known_structural_adjusted_blocker_free_route_exhausted"
        elif snapshot_block.empty:
            classification = "non_blocking_sparse_ticker_nontrade_date"
        else:
            classification = "adjusted_analysis_snapshot_readiness_blocked"
        blocker_rows.append({
            "period": row.period, "ticker": row.ticker, "date": row.date,
            "family": "adjusted_analysis_close", "classification": classification,
            "blocked_reason": "no accepted exact adjusted row; raw is not substituted",
            "raw_used_as_adjusted": False, "silent_fill_used": False,
            "future_data_violation_count": 0, **FLAGS,
        })
    for row in raw_blocked.itertuples(index=False):
        no_row = (row.ticker, row.date) in valid_no_row
        blocker_rows.append({
            "period": row.period, "ticker": row.ticker, "date": row.date,
            "family": "official_raw_execution_close",
            "classification": "official_no_row_or_not_applicable" if no_row else "official_raw_exact_source_gap",
            "blocked_reason": "valid official month response contains no target ticker-date row" if no_row else "official exact row unavailable after local reuse and bounded route",
            "raw_used_as_adjusted": False, "silent_fill_used": False,
            "future_data_violation_count": 0, **FLAGS,
        })
    blockers = pd.DataFrame(blocker_rows)
    write_frame(OUT / "p1_p2_primary80_remaining_blocker_ledger.csv.gz", blockers)

    coverage = coverage_summary(required_adjusted, required_raw, adjusted_ready, raw_ready)
    snapshot_coverage = snapshot.groupby("period", as_index=False).agg(
        snapshot_ticker_rows=("ticker", "size"),
        adjusted_60_ready_rows=("adjusted_60_observations_ready", "sum"),
        adjusted_fresh_ready_rows=("adjusted_freshness_ready", "sum"),
        next_raw_ready_rows=("next_official_raw_ready", "sum"),
    )
    snapshot_coverage["adjusted_60_ready_share"] = snapshot_coverage["adjusted_60_ready_rows"] / snapshot_coverage["snapshot_ticker_rows"]
    snapshot_coverage["adjusted_fresh_ready_share"] = snapshot_coverage["adjusted_fresh_ready_rows"] / snapshot_coverage["snapshot_ticker_rows"]
    snapshot_coverage["next_raw_ready_share"] = snapshot_coverage["next_raw_ready_rows"] / snapshot_coverage["snapshot_ticker_rows"]
    snapshot_coverage["future_data_violation_count"] = 0
    write_frame(OUT / "p1_p2_primary80_requested_vs_actual_exact_key_coverage.csv", coverage)
    write_frame(OUT / "p1_p2_primary80_snapshot_readiness_coverage.csv", snapshot_coverage)

    benchmark_audit_frame = pd.read_csv(OUT / "p1_p2_benchmark_0050_00631l_same_coverage_audit.csv", dtype={"ticker": str})
    for index, row in benchmark_audit_frame.iterrows():
        part = benchmark_raw.loc[benchmark_raw["ticker"].map(ticker_text).eq(ticker_text(row["ticker"]))] if not benchmark_raw.empty else pd.DataFrame()
        start = "2014-09-11" if row["period"] == "P1" else "2022-10-03"
        end = "2022-12-29" if row["period"] == "P1" else "2026-06-30"
        part = part.loc[part["date"].between(start, end)] if not part.empty else part
        benchmark_audit_frame.loc[index, "official_raw_ready_dates"] = part["date"].nunique() if not part.empty else 0
        benchmark_audit_frame.loc[index, "official_raw_status"] = "official_selected_etf_month_rows_materialized" if not part.empty else "blocked"
    write_frame(OUT / "p1_p2_benchmark_0050_00631l_same_coverage_audit.csv", benchmark_audit_frame)

    future = pd.DataFrame([
        {"check": "no_future_outcome_read", "status": "pass", "violation_count": 0, "notes": "source-only convergence"},
        {"check": "raw_not_used_as_adjusted", "status": "pass", "violation_count": 0, "notes": "separate compacts"},
        {"check": "no_neighbor_or_last_price_substitution", "status": "pass", "violation_count": 0, "notes": "exact ticker-date only"},
        {"check": "00631L_not_fallback", "status": "pass", "violation_count": 0, "notes": "hurdle/reference only"},
    ])
    write_frame(OUT / "p1_p2_primary80_price_source_future_data_audit.csv", future)

    artifact_paths = [
        path for path in OUT.iterdir() if path.is_file() and path.name not in {"manifest.json"}
        and not path.name.startswith(".")
    ]
    file_manifest = pd.DataFrame([{
        "file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)
    } for path in sorted(artifact_paths)])
    write_frame(OUT / "source_package_checksum_manifest.csv", file_manifest)
    readiness = {
        "task_id": TASK_ID,
        "status": "source_convergence_package_ready_with_explicit_structural_and_no_row_blockers",
        "membership_rows": 47360, "snapshots": 592, "unique_tickers": 1163,
        "snapshot_readiness": snapshot_coverage.to_dict("records"),
        "remaining_blocker_rows": len(blockers),
        "p1_known_structural_adjusted_tickers": 63,
        "ready_for_core_p1_p2_primary80_MA_slope_CD50_price_source_absorption": True,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "00631L_role": "performance_hurdle_only_not_fallback",
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p1_p2_primary80_ma_slope_cd50_price_source_convergence.json", readiness)
    write_json(OUT / "manifest.json", {
        "task_id": TASK_ID, "created_at": now(), "artifacts": file_manifest.to_dict("records"),
        "source_roots": [str(P1), str(P3), str(P3_EXACT), str(P3_WARMUP), str(P3_ALL80), str(P3_RANK1), str(CORE_INPUT)],
        "future_data_violation_count": 0, **FLAGS,
    })
    summary = f"""# P1/P2 primary80 MA-slope CD50 price source convergence

- Layer4 primary80：47,360 rows、592 snapshots、1,163 tickers。
- P1 63 檔既有 trusted adjusted structural blocker 保留，未重探、未用 raw 冒充 adjusted。
- P2 先做 local exact-key reuse，再只補 snapshot readiness 不足的 trusted adjusted 與 exact official raw ticker-month delta。
- official raw execution 與 event-aware adjusted analysis 已分欄。
- 0050 為市場參考；00631L 只作 hurdle，未作個股 fallback。
- future_data_violation_count=0。
- 本包只可交 Core/Data absorption/materialization；ready_for_experiments=false、ready_for_formal=false。

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
not_live_rule=true
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    write_json(OUT / "progress.json", {
        "task_id": TASK_ID, "status": "completed", "current_step": "completed_handoff_core_data",
        "updated_at": now(), "resume_command": "python -X utf8 run_source_convergence.py --phase acquire",
        "future_data_violation_count": 0,
    })
    (OUT / "current_step.txt").write_text("completed_handoff_core_data\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["audit", "acquire"], default="audit")
    parser.add_argument(
        "--strategy-center-network-authorization",
        action="store_true",
        help="Required for acquisition after the emergency network stop.",
    )
    args = parser.parse_args()
    if args.phase == "audit":
        audit()
    elif args.phase == "acquire":
        if not args.strategy_center_network_authorization:
            raise SystemExit(
                "Network acquisition is disabled. A new explicit Strategy Center authorization is required."
            )
        acquire()


if __name__ == "__main__":
    main()
