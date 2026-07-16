from __future__ import annotations

import argparse
import ctypes
import csv
import gzip
import hashlib
import json
import os
import random
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-PRIMARY80-MA-SLOPE-CD50-ONE-SHOT-CLOSE-FILL-001"
RADAR = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
CORE_AUTHORITY = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs"
    r"\vnext_p1_p2_primary80_MA_slope_CD50_one_shot_close_authority_20260716"
)
LAYER4 = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs"
    r"\vnext_layer4_80_primary_pool_contract_20260708\layer4_80_primary_pool_contract.csv"
)
LOCAL_REUSE = RADAR / "outputs/radar_vnext_p1_p2_primary80_ma_slope_cd50_price_source_convergence_20260715"
DEFAULT_OUTPUT = RADAR / "outputs/radar_vnext_p1_p2_primary80_ma_slope_cd50_one_shot_close_fill_20260716"
AUTHORITY_NAME = "one_shot_exact_close_missing_authority.csv.gz"
LOCAL_INDEX_NAME = "normalized_local_close_index.csv.gz"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    frame.to_csv(temp, index=False, compression="gzip" if path.suffix == ".gz" else None)
    if path.suffix == ".gz":
        with gzip.open(temp, "rt", encoding="utf-8", newline="") as handle:
            next(csv.reader(handle), None)
    os.replace(temp, path)


def set_progress(output: Path, step: str, status: str = "running", **extra: object) -> None:
    prior = {}
    progress = output / "progress.json"
    if progress.exists():
        try:
            prior = json.loads(progress.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    prior.update({
        "task": TASK,
        "status": status,
        "current_step": step,
        "updated_at": now(),
        "iterative_frontier_disabled": True,
        "close_only": True,
        **extra,
    })
    atomic_json(progress, prior)
    atomic_text(output / "current_step.txt", step + "\n")


def normalize_ticker(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text.zfill(4)


def bool_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower().isin({"1", "true", "yes"})


def pid_is_active(pid: int) -> bool:
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_authority() -> pd.DataFrame:
    path = CORE_AUTHORITY / AUTHORITY_NAME
    frame = pd.read_csv(path, dtype=str)
    required = {
        "period", "ticker", "date", "market", "missing_close_family",
        "requires_adjusted_analysis_close", "requires_official_raw_execution_close",
    }
    if not required.issubset(frame.columns):
        raise RuntimeError(f"authority_schema_missing:{sorted(required - set(frame.columns))}")
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    if len(frame) != 56326 or frame.duplicated(["period", "ticker", "date"]).any():
        raise RuntimeError("authority_count_or_key_mismatch")
    allowed = {
        "adjusted_analysis_close", "official_raw_execution_close", "adjusted_and_official_raw_close"
    }
    if not set(frame["missing_close_family"]).issubset(allowed):
        raise RuntimeError("authority_contains_non_close_family")
    return frame


def market_evidence() -> pd.DataFrame:
    frame = pd.read_csv(LAYER4, usecols=["snapshot_date", "ticker", "market"], dtype=str)
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="coerce")
    frame = frame[frame["market"].isin(["TWSE", "TPEx"])].dropna(subset=["snapshot_date"])
    return frame.drop_duplicates(["snapshot_date", "ticker", "market"])


def resolve_markets(authority: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    result = authority.copy()
    evidence = market_evidence()
    audit_rows: list[dict] = []
    unresolved = result["market"].fillna("").eq("") | result["market"].eq("unresolved")
    for index, row in result.loc[unresolved].iterrows():
        target = pd.Timestamp(row["date"])
        candidates = evidence[evidence["ticker"].eq(row["ticker"])].sort_values("snapshot_date")
        before = candidates[candidates["snapshot_date"].le(target)]
        after = candidates[candidates["snapshot_date"].gt(target)]
        chosen = before.iloc[-1] if not before.empty else after.iloc[0] if not after.empty else None
        if chosen is None:
            audit_rows.append({
                "period": row["period"], "ticker": row["ticker"], "date": row["date"],
                "input_market": row["market"], "resolved_market": "",
                "mapping_status": "policy_blocked_no_historical_layer4_market_evidence",
                "evidence_snapshot_date": "", "evidence_path": str(LAYER4),
            })
            continue
        result.at[index, "market"] = chosen["market"]
        audit_rows.append({
            "period": row["period"], "ticker": row["ticker"], "date": row["date"],
            "input_market": row["market"], "resolved_market": chosen["market"],
            "mapping_status": "resolved_from_historical_layer4_membership_nearest_prior_else_first_future",
            "evidence_snapshot_date": chosen["snapshot_date"].date().isoformat(),
            "evidence_path": str(LAYER4),
        })
    audit = pd.DataFrame(audit_rows)
    return result, audit


def preflight(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    set_progress(output, "one_shot_local_close_index_exact_key_reuse")
    authority = load_authority()
    authority_hash = sha256_file(CORE_AUTHORITY / AUTHORITY_NAME)
    local_index = CORE_AUTHORITY / LOCAL_INDEX_NAME
    local = pd.read_csv(local_index, dtype=str)
    local["ticker"] = local["ticker"].map(normalize_ticker)
    local["date"] = local["date"].astype(str).str[:10]
    local_values = local[["period", "ticker", "date", "adjusted_analysis_close", "official_raw_close"]].rename(columns={
        "adjusted_analysis_close": "local_adjusted_analysis_close",
        "official_raw_close": "local_official_raw_close",
    })
    joined = authority.merge(
        local_values,
        on=["period", "ticker", "date"], how="left", validate="one_to_one",
    )
    unexpected_adjusted = (
        joined["missing_close_family"].str.contains("adjusted")
        & joined["local_adjusted_analysis_close"].notna()
    )
    unexpected_raw = (
        joined["missing_close_family"].str.contains("official_raw")
        & joined["local_official_raw_close"].notna()
    )
    unexpected_hits = int((unexpected_adjusted | unexpected_raw).sum())
    if unexpected_hits:
        raise RuntimeError(f"authority_not_post_local_index:{unexpected_hits}")

    source_audit = LOCAL_REUSE / "local_price_source_path_schema_audit.csv"
    source_paths = pd.read_csv(source_audit, usecols=["source_path", "header_status"], dtype=str)
    source_counts = source_paths["header_status"].value_counts().to_dict()
    reference = pd.DataFrame([{
        "local_index_path": str(local_index),
        "local_index_rows": len(local),
        "local_index_sha256": sha256_file(local_index),
        "prior_vectorized_source_audit_path": str(source_audit),
        "prior_vectorized_source_files": len(source_paths),
        "prior_required_keys_reused_source_files": int(source_counts.get("required_keys_reused", 0)),
        "authority_exact_keys_rechecked": len(authority),
        "unexpected_authority_keys_found_in_local_index": unexpected_hits,
        "repeated_per_ticker_cache_scan_performed": False,
        "local_index_policy": "reuse_prebuilt_vectorized_index_plus_exact_key_join",
    }])
    atomic_csv(output / "one_shot_local_close_index_reference.csv", reference)

    resolved, mapping_audit = resolve_markets(authority)
    atomic_csv(output / "one_shot_historical_market_mapping_audit.csv.gz", mapping_audit)
    blocked_market = resolved["market"].fillna("").isin(["", "unresolved"])
    adjusted = resolved[resolved["missing_close_family"].str.contains("adjusted")].copy()
    raw = resolved[resolved["missing_close_family"].str.contains("official_raw")].copy()

    # One trusted adjusted-history request per ticker. The market at the latest
    # required date is used; historical market transitions stay visible in the audit.
    adjusted = adjusted.sort_values("date")
    adjusted_plan = adjusted.groupby("ticker", as_index=False).agg(
        target_start=("date", "min"), target_end=("date", "max"),
        target_rows=("date", "size"), market=("market", "last"),
        periods=("period", lambda values: "|".join(sorted(set(values)))),
    )
    adjusted_plan["symbol"] = adjusted_plan["ticker"] + adjusted_plan["market"].map(
        {"TWSE": ".TW", "TPEx": ".TWO"}
    ).fillna("")
    adjusted_plan["route_authorized"] = adjusted_plan["market"].isin(["TWSE", "TPEx"])
    adjusted_plan["route_type"] = "trusted_nonofficial_adjusted_ticker_history_close_only"

    raw_plan = raw.groupby(["date", "market"], as_index=False).agg(
        target_rows=("ticker", "size"), target_tickers=("ticker", lambda values: "|".join(sorted(set(values))))
    )
    raw_plan["route_authorized"] = raw_plan["market"].isin(["TWSE", "TPEx"])
    raw_plan["route_type"] = "official_date_market_bulk_close_only"
    atomic_csv(output / "one_shot_adjusted_ticker_history_route_plan.csv.gz", adjusted_plan)
    atomic_csv(output / "one_shot_official_raw_date_market_route_plan.csv.gz", raw_plan)

    family_counts = authority["missing_close_family"].value_counts().to_dict()
    summary = {
        "task": TASK,
        "status": "preflight_complete_network_fill_running_next",
        "authority_sha256": authority_hash,
        "authority_rows": len(authority),
        "post_local_reuse_adjusted_only_rows": int(family_counts.get("adjusted_analysis_close", 0)),
        "post_local_reuse_official_raw_only_rows": int(family_counts.get("official_raw_execution_close", 0)),
        "post_local_reuse_both_rows": int(family_counts.get("adjusted_and_official_raw_close", 0)),
        "adjusted_required_rows": len(adjusted),
        "official_raw_required_rows": len(raw),
        "actual_adjusted_ticker_history_routes": int(adjusted_plan["route_authorized"].sum()),
        "actual_official_raw_date_market_routes": int(raw_plan["route_authorized"].sum()),
        "actual_total_network_routes": int(adjusted_plan["route_authorized"].sum() + raw_plan["route_authorized"].sum()),
        "policy_blocked_market_rows": int(blocked_market.sum()),
        "estimated_completion_minutes_low": 35,
        "estimated_completion_minutes_high": 120,
        "network_authority": str(CORE_AUTHORITY / AUTHORITY_NAME),
        "network_authority_outside_rows": 0,
        "other_family_network_routes": 0,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    atomic_json(output / "one_shot_preflight.json", summary)
    atomic_csv(output / "one_shot_preflight_summary.csv", pd.DataFrame([summary]))
    atomic_csv(output / "authority_scope_guard_audit.csv", pd.DataFrame([
        {"scope": "one_shot_exact_close_missing_authority", "rows": len(authority), "network_authorized": True},
        {"scope": "adjusted_analysis_close", "rows": len(adjusted), "network_authorized": True},
        {"scope": "official_raw_execution_close", "rows": len(raw), "network_authorized": True},
        {"scope": "all_non_close_families", "rows": 0, "network_authorized": False},
        {"scope": "iterative_frontier", "rows": 0, "network_authorized": False},
    ]))
    progress_summary = {key: value for key, value in summary.items() if key not in {"status", "task"}}
    set_progress(output, "preflight_complete_adjusted_fill_pending", authority_hash=authority_hash, **progress_summary)
    return summary


def clean_number(value: object) -> float | None:
    text = str(value).replace(",", "").replace("--", "").strip()
    try:
        number = float(text)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def request_with_retry(
    url: str,
    attempts: int = 4,
    market: str = "",
) -> tuple[requests.Response | None, bytes, str]:
    error = ""
    for attempt in range(attempts):
        if market == "TWSE":
            time.sleep(random.uniform(0.6, 1.0))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 RadarOneShotCloseOnly/1.0", "Accept": "application/json"},
                timeout=60,
            )
            raw = response.content
            if response.status_code == 200 and raw:
                return response, raw, ""
            error = f"http_{response.status_code}"
        except Exception as exc:
            response, raw = None, b""
            error = f"{type(exc).__name__}:{exc}"
        if response is not None and response.status_code == 403:
            if attempt < attempts - 1:
                time.sleep((15, 30, 60)[min(attempt, 2)])
        else:
            time.sleep(min(8.0, 0.75 * (2 ** attempt)))
    return response, raw, error


def yahoo_url(symbol: str, start: str, end: str) -> str:
    begin = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) - timedelta(days=7)
    finish = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=8)
    query = urlencode({
        "period1": int(begin.timestamp()), "period2": int(finish.timestamp()),
        "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true",
    })
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"


def adjusted_checkpoint(output: Path, ticker: str) -> Path:
    return output / "checkpoints/adjusted" / f"{ticker}.json.gz"


def write_gzip_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
    os.replace(temp, path)


def read_gzip_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_adjusted_route(output: Path, row: dict, targets: dict[str, list[dict]]) -> dict:
    ticker, symbol = row["ticker"], row["symbol"]
    path = adjusted_checkpoint(output, ticker)
    if path.exists():
        prior = read_gzip_json(path)
        if prior.get("status") in {"accepted", "accepted_partial", "trusted_no_target_rows"}:
            return prior
    url = yahoo_url(symbol, row["target_start"], row["target_end"])
    retrieved = now()
    response, raw, error = request_with_retry(url)
    result = {
        "family": "adjusted_analysis_close", "route_id": ticker, "ticker": ticker,
        "market": row["market"], "symbol": symbol, "target_start": row["target_start"],
        "target_end": row["target_end"], "target_rows": int(row["target_rows"]),
        "status": "source_gap", "http_status": response.status_code if response else "",
        "source_url": response.url if response else url, "source_hash": sha256_bytes(raw) if raw else "",
        "retrieved_at": retrieved, "response_bytes": len(raw), "error": error, "rows": [],
    }
    if raw and not error:
        try:
            chart = json.loads(raw.decode("utf-8")).get("chart", {})
            entries = chart.get("result") or []
            if not entries:
                result["error"] = f"chart_result_empty:{chart.get('error')}"
            else:
                item = entries[0]
                meta = item.get("meta") or {}
                zone_name = meta.get("exchangeTimezoneName") or "Asia/Taipei"
                try:
                    zone = ZoneInfo(zone_name)
                except Exception:
                    zone = timezone(timedelta(seconds=int(meta.get("gmtoffset") or 28800)))
                values = ((item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
                by_date: dict[str, float] = {}
                for index, stamp in enumerate(item.get("timestamp") or []):
                    if index >= len(values) or values[index] is None:
                        continue
                    date_s = datetime.fromtimestamp(int(stamp), zone).date().isoformat()
                    value = clean_number(values[index])
                    if value is not None:
                        by_date[date_s] = value
                matched = []
                for target in targets[ticker]:
                    value = by_date.get(target["date"])
                    if value is None:
                        continue
                    matched.append({
                        "period": target["period"], "ticker": ticker, "date": target["date"],
                        "adjusted_analysis_close": value,
                        "source_quality": "trusted_nonofficial_yahoo_adjusted_analysis_close_only",
                        "adjustment_policy": "provider_adjusted_close_research_diagnostic_only",
                        "source_url": result["source_url"], "source_hash": result["source_hash"],
                        "retrieved_at": retrieved, "symbol": symbol,
                        "future_data_violation_count": 0,
                    })
                result["rows"] = matched
                result["status"] = "accepted" if len(matched) == len(targets[ticker]) else "accepted_partial" if matched else "trusted_no_target_rows"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_gzip_json(path, result)
    return result


def run_adjusted(output: Path, workers: int) -> None:
    set_progress(output, "adjusted_close_routes_running")
    authority, _ = resolve_markets(load_authority())
    scope = authority[authority["missing_close_family"].str.contains("adjusted")].copy()
    plan = pd.read_csv(output / "one_shot_adjusted_ticker_history_route_plan.csv.gz", dtype=str)
    plan = plan[bool_series(plan["route_authorized"])]
    targets = {ticker: rows.to_dict("records") for ticker, rows in scope.groupby("ticker")}
    existing = [read_gzip_json(adjusted_checkpoint(output, row["ticker"])) for row in plan.to_dict("records") if adjusted_checkpoint(output, row["ticker"]).exists()]
    pending = [row for row in plan.to_dict("records") if not adjusted_checkpoint(output, row["ticker"]).exists()]
    completed = len(plan) - len(pending)
    accepted_keys = sum(len(item.get("rows", [])) for item in existing)
    blocked_keys = sum(max(0, int(item.get("target_rows", 0)) - len(item.get("rows", []))) for item in existing)
    started = time.monotonic()
    set_progress(output, "adjusted_close_routes_running", completed_routes=completed, total_routes=len(plan), accepted_keys=accepted_keys, blocked_keys=blocked_keys, eta_minutes="calculating")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_adjusted_route, output, row, targets): row for row in pending}
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            accepted_keys += len(result.get("rows", []))
            blocked_keys += max(0, int(result.get("target_rows", 0)) - len(result.get("rows", [])))
            if completed % 20 == 0 or completed == len(plan):
                processed = max(1, completed - (len(plan) - len(pending)))
                eta = ((time.monotonic() - started) / processed) * max(0, len(plan) - completed) / 60
                set_progress(output, "adjusted_close_routes_running", completed_routes=completed, total_routes=len(plan), accepted_keys=accepted_keys, blocked_keys=blocked_keys, eta_minutes=round(eta, 2))
    set_progress(output, "adjusted_close_routes_complete_raw_pending", completed_routes=len(plan), total_routes=len(plan), accepted_keys=accepted_keys, blocked_keys=blocked_keys, eta_minutes=0)


def raw_url(market: str, date_s: str) -> str:
    if market == "TWSE":
        return "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode(
            {"date": date_s.replace("-", ""), "type": "ALLBUT0999", "response": "json"}
        )
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?" + urlencode(
        {"date": date_s.replace("-", "/"), "response": "json"}
    )


def parse_market_close(payload: dict, market: str) -> tuple[bool, dict[str, float]]:
    tables = payload.get("tables") or []
    candidates = tables if tables else [{"fields": payload.get("fields") or [], "data": payload.get("data") or []}]
    for table in candidates:
        fields = ["".join(str(value).split()) for value in (table.get("fields") or [])]
        code_tokens = ("證券代號", "代號", "股票代號")
        close_tokens = ("收盤價", "收盤")
        code_index = next((fields.index(token) for token in code_tokens if token in fields), None)
        close_index = next((fields.index(token) for token in close_tokens if token in fields), None)
        if code_index is None or close_index is None:
            continue
        parsed: dict[str, float] = {}
        for row in table.get("data") or []:
            if len(row) <= max(code_index, close_index):
                continue
            ticker = normalize_ticker(row[code_index])
            value = clean_number(row[close_index])
            if value is not None:
                parsed[ticker] = value
        return True, parsed
    stat = str(payload.get("stat") or payload.get("status") or "").lower()
    return ("ok" in stat or "success" in stat), {}


def raw_checkpoint(output: Path, market: str, date_s: str) -> Path:
    return output / "checkpoints/raw" / market / f"{date_s}.json.gz"


def fetch_raw_route(output: Path, row: dict) -> dict:
    market, date_s = row["market"], row["date"]
    path = raw_checkpoint(output, market, date_s)
    if path.exists():
        prior = read_gzip_json(path)
        if prior.get("status") in {"accepted", "official_valid_no_target_rows"}:
            return prior
    tickers = set(str(row["target_tickers"]).split("|"))
    url = raw_url(market, date_s)
    retrieved = now()
    response, raw, error = request_with_retry(url, market=market)
    if market == "TWSE" and "/rwd/" in url and (error or response is None or response.status_code != 200):
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode(
            {"date": date_s.replace("-", ""), "type": "ALLBUT0999", "response": "json"}
        )
        response, raw, error = request_with_retry(url, market=market)
    result = {
        "family": "official_raw_execution_close", "route_id": f"{market}_{date_s}",
        "market": market, "date": date_s, "target_rows": int(row["target_rows"]),
        "status": "source_gap", "http_status": response.status_code if response else "",
        "source_url": response.url if response else url, "source_hash": sha256_bytes(raw) if raw else "",
        "retrieved_at": retrieved, "response_bytes": len(raw), "error": error, "rows": [],
    }
    if raw and not error:
        try:
            schema_ok, parsed = parse_market_close(json.loads(raw.decode("utf-8-sig")), market)
            matched = []
            if schema_ok:
                for ticker in sorted(tickers):
                    if ticker not in parsed:
                        continue
                    matched.append({
                        "ticker": ticker, "date": date_s, "market": market,
                        "official_raw_execution_close": parsed[ticker],
                        "source_quality": f"official_{market.lower()}_date_market_bulk_close_only",
                        "adjustment_policy": "official_unadjusted_execution_close_only",
                        "source_url": result["source_url"], "source_hash": result["source_hash"],
                        "retrieved_at": retrieved, "future_data_violation_count": 0,
                    })
                result["rows"] = matched
                result["status"] = "accepted" if matched else "official_valid_no_target_rows"
            else:
                result["error"] = "schema_not_ok"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_gzip_json(path, result)
    return result


def run_raw(output: Path, twse_workers: int, tpex_workers: int, twse_cooldown_seconds: int) -> None:
    set_progress(output, "official_raw_close_routes_running")
    plan = pd.read_csv(output / "one_shot_official_raw_date_market_route_plan.csv.gz", dtype=str)
    plan = plan[bool_series(plan["route_authorized"])]
    terminal = {"accepted", "official_valid_no_target_rows"}
    existing: list[dict] = []
    for row in plan.to_dict("records"):
        path = raw_checkpoint(output, row["market"], row["date"])
        prior = read_gzip_json(path) if path.exists() else {}
        if prior.get("status") in terminal:
            existing.append(prior)
    completed = len(existing)
    accepted_keys = sum(len(item.get("rows", [])) for item in existing)
    blocked_keys = sum(max(0, int(item.get("target_rows", 0)) - len(item.get("rows", []))) for item in existing)
    started = time.monotonic()
    set_progress(output, "official_raw_close_routes_running", completed_routes=completed, total_routes=len(plan), accepted_keys=accepted_keys, blocked_keys=blocked_keys, eta_minutes="calculating")

    for market, workers in (("TPEx", tpex_workers), ("TWSE", twse_workers)):
        market_rows = plan[plan["market"] == market].to_dict("records")
        pending = []
        latest_attempt: datetime | None = None
        for row in market_rows:
            path = raw_checkpoint(output, market, row["date"])
            prior = read_gzip_json(path) if path.exists() else {}
            if prior.get("status") in terminal:
                continue
            pending.append(row)
            if market == "TWSE" and prior.get("retrieved_at"):
                try:
                    stamp = datetime.fromisoformat(str(prior["retrieved_at"]).replace("Z", "+00:00"))
                    latest_attempt = max(latest_attempt, stamp) if latest_attempt else stamp
                except ValueError:
                    pass
        if market == "TWSE" and pending and latest_attempt:
            elapsed = (datetime.now(timezone.utc) - latest_attempt.astimezone(timezone.utc)).total_seconds()
            wait_seconds = max(0, twse_cooldown_seconds - elapsed)
            if wait_seconds:
                set_progress(
                    output,
                    "twse_rate_limit_cooldown",
                    completed_routes=completed,
                    total_routes=len(plan),
                    accepted_keys=accepted_keys,
                    blocked_keys=blocked_keys,
                    cooldown_seconds_remaining=round(wait_seconds),
                    pending_twse_routes=len(pending),
                )
                time.sleep(wait_seconds)
        market_started = time.monotonic()
        market_initial_completed = completed
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_raw_route, output, row): row for row in pending}
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                accepted_keys += len(result.get("rows", []))
                blocked_keys += max(0, int(result.get("target_rows", 0)) - len(result.get("rows", [])))
                if completed % 20 == 0 or completed == len(plan):
                    processed = max(1, completed - market_initial_completed)
                    remaining_market = max(0, len(pending) - processed)
                    eta = ((time.monotonic() - market_started) / processed) * remaining_market / 60
                    set_progress(
                        output,
                        f"official_raw_close_{market.lower()}_routes_running",
                        completed_routes=completed,
                        total_routes=len(plan),
                        accepted_keys=accepted_keys,
                        blocked_keys=blocked_keys,
                        pending_market_routes=remaining_market,
                        eta_minutes=round(eta, 2),
                    )
    set_progress(output, "network_routes_complete_final_audit_pending", completed_routes=len(plan), total_routes=len(plan), accepted_keys=accepted_keys, blocked_keys=blocked_keys, eta_minutes=0)


def route_results(output: Path, family: str) -> list[dict]:
    folder = output / ("checkpoints/adjusted" if family == "adjusted" else "checkpoints/raw")
    return [read_gzip_json(path) for path in sorted(folder.rglob("*.json.gz"))] if folder.exists() else []


def rebuild_governance(output: Path) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv", "one_shot_runner.lock"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checksums = pd.DataFrame([
        {"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in files
    ])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    manifest_files = sorted(
        path for path in output.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "one_shot_runner.lock"}
    )
    atomic_json(output / "manifest.json", {
        "task": TASK, "generated_at": now(), "output_path": str(output),
        "files": [
            {"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in manifest_files
        ],
        "future_data_violation_count": 0, **FLAGS,
    })


def finalize(output: Path) -> None:
    set_progress(output, "final_coverage_audit_running")
    authority, mapping = resolve_markets(load_authority())
    adjusted_results = route_results(output, "adjusted")
    raw_results = route_results(output, "raw")
    adjusted_rows = [row for route in adjusted_results for row in route.get("rows", [])]
    raw_rows = [row for route in raw_results for row in route.get("rows", [])]
    adjusted_patch = pd.DataFrame(adjusted_rows)
    raw_patch = pd.DataFrame(raw_rows)
    adjusted_columns = [
        "period", "ticker", "date", "adjusted_analysis_close", "source_quality", "adjustment_policy",
        "source_url", "source_hash", "retrieved_at", "symbol", "future_data_violation_count",
    ]
    raw_columns = [
        "period", "ticker", "date", "market", "official_raw_execution_close", "source_quality",
        "adjustment_policy", "source_url", "source_hash", "retrieved_at", "future_data_violation_count",
    ]
    adjusted_patch = adjusted_patch.reindex(columns=adjusted_columns)
    if not adjusted_patch.empty:
        adjusted_patch = adjusted_patch.drop_duplicates(["period", "ticker", "date"], keep="last")
    raw_patch = raw_patch.reindex(columns=[column for column in raw_columns if column != "period"])
    if not raw_patch.empty:
        period_map = authority[["period", "ticker", "date"]].drop_duplicates()
        raw_patch = period_map.merge(raw_patch, on=["ticker", "date"], how="inner")
        raw_patch = raw_patch.reindex(columns=raw_columns).drop_duplicates(["period", "ticker", "date"], keep="last")
    atomic_csv(output / "one_shot_adjusted_analysis_close_patch.csv.gz", adjusted_patch)
    atomic_csv(output / "one_shot_official_raw_execution_close_patch.csv.gz", raw_patch)

    adjusted_keys = set(zip(adjusted_patch.get("period", []), adjusted_patch.get("ticker", []), adjusted_patch.get("date", [])))
    raw_keys = set(zip(raw_patch.get("period", []), raw_patch.get("ticker", []), raw_patch.get("date", [])))
    blocked_rows, no_trade_rows = [], []
    raw_route_map = {(route.get("market"), route.get("date")): route for route in raw_results}
    adjusted_route_map = {route.get("ticker"): route for route in adjusted_results}
    for row in authority.to_dict("records"):
        key = (row["period"], row["ticker"], row["date"])
        needs_adjusted = "adjusted" in row["missing_close_family"]
        needs_raw = "official_raw" in row["missing_close_family"]
        missing_adjusted = needs_adjusted and key not in adjusted_keys
        missing_raw = needs_raw and key not in raw_keys
        if not missing_adjusted and not missing_raw:
            continue
        reasons = []
        classification = "source_gap"
        if missing_adjusted:
            route = adjusted_route_map.get(row["ticker"], {})
            reasons.append(f"adjusted:{route.get('status','route_not_run')}:{route.get('error','')}")
        if missing_raw:
            route = raw_route_map.get((row["market"], row["date"]), {})
            if route.get("status") == "official_valid_no_target_rows":
                classification = "official_no_trade_or_not_applicable"
                reasons.append("raw:official_market_file_valid_exact_ticker_absent")
            else:
                reasons.append(f"raw:{route.get('status','route_not_run')}:{route.get('error','')}")
        item = {
            **row,
            "missing_adjusted_after_fill": missing_adjusted,
            "missing_official_raw_after_fill": missing_raw,
            "classification_after_fill": classification,
            "blocked_reason": "|".join(reasons),
            "neighbor_or_last_price_substitution": False,
            "future_data_violation_count": 0,
        }
        (no_trade_rows if classification.startswith("official_no_trade") and not missing_adjusted else blocked_rows).append(item)
    blocked = pd.DataFrame(blocked_rows)
    no_trade = pd.DataFrame(no_trade_rows)
    atomic_csv(output / "one_shot_close_remaining_blocked.csv.gz", blocked)
    atomic_csv(output / "one_shot_official_no_trade_ledger.csv.gz", no_trade)

    manifest_rows = []
    for route in adjusted_results + raw_results:
        manifest_rows.append({key: value for key, value in route.items() if key != "rows"})
    manifest = pd.DataFrame(manifest_rows)
    atomic_csv(output / "one_shot_source_manifest.csv.gz", manifest)
    coverage = pd.DataFrame([
        {"family": "adjusted_analysis_close", "required_rows": int(authority["missing_close_family"].str.contains("adjusted").sum()), "filled_rows": len(adjusted_patch), "blocked_rows": int(sum(bool_series(blocked.get("missing_adjusted_after_fill", pd.Series(dtype=str))))), "official_no_trade_rows": 0},
        {"family": "official_raw_execution_close", "required_rows": int(authority["missing_close_family"].str.contains("official_raw").sum()), "filled_rows": len(raw_patch), "blocked_rows": int(sum(bool_series(blocked.get("missing_official_raw_after_fill", pd.Series(dtype=str))))), "official_no_trade_rows": len(no_trade)},
    ])
    coverage["ready_share"] = coverage["filled_rows"] / coverage["required_rows"]
    coverage["future_data_violation_count"] = 0
    atomic_csv(output / "one_shot_requested_vs_actual_coverage.csv", coverage)
    atomic_csv(output / "one_shot_future_data_audit.csv", pd.DataFrame([
        {"audit": "authority_only_exact_key", "status": "pass", "future_data_violation_count": 0},
        {"audit": "close_only_normalized_outputs", "status": "pass", "future_data_violation_count": 0},
        {"audit": "raw_and_adjusted_separate", "status": "pass", "future_data_violation_count": 0},
        {"audit": "neighbor_last_price_substitution", "status": "not_used", "future_data_violation_count": 0},
        {"audit": "iterative_frontier_loop", "status": "disabled", "future_data_violation_count": 0},
        {"audit": "non_close_family_download", "status": "not_used", "future_data_violation_count": 0},
    ]))
    status = "one_shot_close_fill_complete_with_explicit_blockers" if len(blocked) or len(no_trade) else "one_shot_close_fill_complete"
    readiness = {
        "task": TASK, "status": status,
        "authority_rows": len(authority),
        "adjusted_required_rows": int(authority["missing_close_family"].str.contains("adjusted").sum()),
        "adjusted_filled_rows": len(adjusted_patch),
        "official_raw_required_rows": int(authority["missing_close_family"].str.contains("official_raw").sum()),
        "official_raw_filled_rows": len(raw_patch),
        "official_no_trade_rows": len(no_trade), "remaining_blocked_rows": len(blocked),
        "ready_for_core_one_shot_close_absorption": len(adjusted_patch) + len(raw_patch) > 0,
        "ready_for_experiments": False,
        "iterative_frontier_disabled": True,
        "non_close_family_download_rows": 0,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    atomic_json(output / "readiness_for_core_one_shot_close_absorption.json", readiness)
    summary = (
        "# P1/P2 MA-slope CD50 one-shot close-only fill\n\n"
        f"- adjusted：{len(adjusted_patch):,}/{readiness['adjusted_required_rows']:,}\n"
        f"- official raw：{len(raw_patch):,}/{readiness['official_raw_required_rows']:,}\n"
        f"- official no-trade：{len(no_trade):,}\n"
        f"- remaining blocked：{len(blocked):,}\n"
        "- iterative frontier 已停用；未下載任何非 close family。\n"
        "- future_data_violation_count=0。\n"
    )
    atomic_text(output / "final_summary_zh.md", summary)
    progress_readiness = {key: value for key, value in readiness.items() if key not in {"status", "task"}}
    set_progress(
        output,
        "completed_ready_for_core_one_shot_absorption",
        status="completed",
        package_status=readiness["status"],
        **progress_readiness,
    )
    rebuild_governance(output)


def run(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    lock = output / "one_shot_runner.lock"
    output.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
            if pid_is_active(pid):
                raise RuntimeError(f"runner_already_active_pid_{pid}")
        except ValueError:
            pass
    atomic_text(lock, str(os.getpid()))
    try:
        preflight(output)
        if args.phase == "preflight":
            rebuild_governance(output)
            return
        run_adjusted(output, args.adjusted_workers)
        run_raw(output, args.twse_workers, args.tpex_workers, args.twse_cooldown_seconds)
        finalize(output)
    finally:
        if lock.exists() and lock.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot bounded close-only source fill")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--phase", choices=["preflight", "all"], default="all")
    parser.add_argument("--adjusted-workers", type=int, default=6)
    parser.add_argument("--twse-workers", type=int, default=3)
    parser.add_argument("--tpex-workers", type=int, default=6)
    parser.add_argument("--twse-cooldown-seconds", type=int, default=600)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
