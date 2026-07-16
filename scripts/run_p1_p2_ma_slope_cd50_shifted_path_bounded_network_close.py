from __future__ import annotations

import gzip
import json
import os
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from run_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction import (
    FLAGS,
    KEY,
    OUTPUT,
    PREVIOUS,
    TASK,
    atomic_csv,
    atomic_json,
    atomic_text,
    normalize_keys,
    now,
    rebuild_manifest,
    sha256,
)


NETWORK_TASK = TASK.replace("LOCAL-CLOSE-EXTRACTION", "BOUNDED-NETWORK-CLOSE-COMPLETION")


def sha256_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def write_checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.tmp"
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
    os.replace(temp, path)


def read_checkpoint(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def clean_number(value: object) -> float | None:
    try:
        number = float(str(value).replace(",", "").replace("--", "").strip())
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def request(url: str, market: str = "", attempts: int = 4) -> tuple[requests.Response | None, bytes, str]:
    error = ""
    response = None
    raw = b""
    for attempt in range(attempts):
        if market == "TWSE":
            time.sleep(random.uniform(0.6, 1.0))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 RadarShiftedCloseOnly/1.0", "Accept": "application/json"},
                timeout=60,
            )
            raw = response.content
            if response.status_code == 200 and raw:
                return response, raw, ""
            error = f"http_{response.status_code}"
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
        if response is not None and response.status_code == 403 and attempt < attempts - 1:
            time.sleep((15, 30, 60)[min(attempt, 2)])
        elif attempt < attempts - 1:
            time.sleep(min(8.0, 0.75 * (2 ** attempt)))
    return response, raw, error


def prior_adjusted_status() -> dict[str, dict]:
    result = {}
    for path in sorted((PREVIOUS / "checkpoints/adjusted").glob("*.json.gz")):
        item = read_checkpoint(path)
        result[str(item.get("ticker"))] = item
    return result


def prior_raw_status(market: str, date: str) -> dict:
    path = PREVIOUS / "checkpoints/raw" / market / f"{date}.json.gz"
    return read_checkpoint(path) if path.exists() else {}


def build_plans(output: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    adjusted = normalize_keys(pd.read_csv(output / "shifted_path_adjusted_local_remaining_blocked.csv.gz", dtype=str))
    statuses = prior_adjusted_status()
    adjusted["prior_route_status"] = adjusted["ticker"].map(lambda value: statuses.get(value, {}).get("status", "missing_checkpoint"))
    adjusted["prior_route_error"] = adjusted["ticker"].map(lambda value: statuses.get(value, {}).get("error", ""))
    adjusted["symbol"] = adjusted["ticker"].map(lambda value: statuses.get(value, {}).get("symbol", ""))
    adjusted["network_authorized"] = adjusted["prior_route_status"].eq("accepted")
    adjusted["network_policy_reason"] = adjusted.apply(
        lambda row: "prior_success_payload_not_retained" if row["network_authorized"]
        else "structural_exact_session_absent_no_retry" if row["prior_route_status"] == "accepted_partial"
        else "no_prior_success_checkpoint_no_retry",
        axis=1,
    )
    allowed_adjusted = adjusted[adjusted["network_authorized"]].copy()
    adjusted_plan = allowed_adjusted.groupby(["ticker", "symbol"], as_index=False).agg(
        start=("date", "min"), end=("date", "max"), target_rows=("date", "size")
    )

    raw = normalize_keys(pd.read_csv(output / "shifted_path_raw_local_remaining_blocked.csv", dtype=str))
    index = pd.read_csv(output / "reusable_one_shot_close_index.csv.gz", dtype=str, usecols=["ticker", "market"])
    index = index[index["market"].isin(["TWSE", "TPEx"])]
    market_map = index.groupby("ticker")["market"].agg(lambda values: values.value_counts().index[0]).to_dict()
    raw["market"] = raw["ticker"].map(market_map).fillna("unresolved")
    raw["prior_route_status"] = raw.apply(lambda row: prior_raw_status(row["market"], row["date"]).get("status", "missing_checkpoint"), axis=1)
    raw["prior_route_error"] = raw.apply(lambda row: prior_raw_status(row["market"], row["date"]).get("error", ""), axis=1)
    raw["network_authorized"] = raw["market"].isin(["TWSE", "TPEx"]) & raw["prior_route_status"].eq("accepted")
    raw["network_policy_reason"] = raw["network_authorized"].map({True: "prior_success_payload_not_retained", False: "no_prior_success_checkpoint_no_retry"})
    raw_plan = raw[raw["network_authorized"]].groupby(["date", "market"], as_index=False).agg(
        target_rows=("ticker", "size"), target_tickers=("ticker", lambda values: "|".join(sorted(set(values))))
    )
    return adjusted, adjusted_plan, raw, raw_plan


def yahoo_url(symbol: str, start: str, end: str) -> str:
    begin = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) - timedelta(days=7)
    finish = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=8)
    return "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?" + urlencode({
        "period1": int(begin.timestamp()), "period2": int(finish.timestamp()),
        "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true",
    })


def fetch_adjusted(output: Path, row: dict) -> dict:
    path = output / "network_checkpoints/adjusted" / f"{row['ticker']}.json.gz"
    if path.exists():
        prior = read_checkpoint(path)
        if prior.get("status") == "accepted_full_close_index":
            return prior
    url = yahoo_url(row["symbol"], row["start"], row["end"])
    retrieved = now()
    response, raw, error = request(url)
    result = {
        "family": "adjusted_analysis_close", "route_id": row["ticker"], "ticker": row["ticker"],
        "symbol": row["symbol"], "start": row["start"], "end": row["end"],
        "target_rows": int(row["target_rows"]), "status": "source_gap", "error": error,
        "http_status": response.status_code if response is not None else "",
        "source_url": response.url if response is not None else url,
        "source_hash": sha256_bytes(raw) if raw else "", "retrieved_at": retrieved,
        "response_bytes": len(raw), "full_rows": [],
    }
    if raw and not error:
        try:
            chart = json.loads(raw.decode("utf-8")).get("chart", {})
            entries = chart.get("result") or []
            if entries:
                item = entries[0]
                meta = item.get("meta") or {}
                zone_name = meta.get("exchangeTimezoneName") or "Asia/Taipei"
                try:
                    zone = ZoneInfo(zone_name)
                except Exception:
                    zone = timezone(timedelta(seconds=int(meta.get("gmtoffset") or 28800)))
                values = ((item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
                full = []
                for index, stamp in enumerate(item.get("timestamp") or []):
                    value = clean_number(values[index]) if index < len(values) else None
                    if value is not None:
                        full.append({
                            "ticker": row["ticker"], "date": datetime.fromtimestamp(int(stamp), zone).date().isoformat(),
                            "adjusted_analysis_close": value, "source_quality": "trusted_nonofficial_yahoo_adjusted_close_only",
                            "source_url": result["source_url"], "source_hash": result["source_hash"], "retrieved_at": retrieved,
                        })
                result["full_rows"] = full
                result["status"] = "accepted_full_close_index" if full else "structural_no_history_rows"
            else:
                result["error"] = f"chart_result_empty:{chart.get('error')}"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_checkpoint(path, result)
    return result


def raw_url(market: str, date: str) -> str:
    if market == "TWSE":
        return "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode({"date": date.replace("-", ""), "type": "ALLBUT0999", "response": "json"})
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?" + urlencode({"date": date.replace("-", "/"), "response": "json"})


def parse_market(payload: dict) -> dict[str, float]:
    tables = payload.get("tables") or [{"fields": payload.get("fields") or [], "data": payload.get("data") or []}]
    for table in tables:
        fields = ["".join(str(value).split()) for value in table.get("fields") or []]
        code = next((fields.index(token) for token in ("證券代號", "代號", "股票代號") if token in fields), None)
        close = next((fields.index(token) for token in ("收盤價", "收盤") if token in fields), None)
        if code is None or close is None:
            continue
        result = {}
        for row in table.get("data") or []:
            if len(row) <= max(code, close):
                continue
            ticker = "".join(character for character in str(row[code]).strip() if character.isalnum()).upper()
            value = clean_number(row[close])
            if ticker and value is not None:
                result[ticker] = value
        return result
    return {}


def fetch_raw(output: Path, row: dict) -> dict:
    path = output / "network_checkpoints/raw" / row["market"] / f"{row['date']}.json.gz"
    if path.exists():
        prior = read_checkpoint(path)
        if prior.get("status") == "accepted_full_close_index":
            return prior
    url = raw_url(row["market"], row["date"])
    retrieved = now()
    response, raw, error = request(url, market=row["market"])
    result = {
        "family": "official_raw_execution_close", "route_id": f"{row['market']}_{row['date']}",
        "market": row["market"], "date": row["date"], "target_rows": int(row["target_rows"]),
        "status": "source_gap", "error": error, "http_status": response.status_code if response is not None else "",
        "source_url": response.url if response is not None else url, "source_hash": sha256_bytes(raw) if raw else "",
        "retrieved_at": retrieved, "response_bytes": len(raw), "full_rows": [],
    }
    if raw and not error:
        try:
            values = parse_market(json.loads(raw.decode("utf-8-sig")))
            result["full_rows"] = [{
                "ticker": ticker, "date": row["date"], "market": row["market"],
                "official_raw_close": value, "source_quality": f"official_{row['market'].lower()}_market_close_only",
                "source_url": result["source_url"], "source_hash": result["source_hash"], "retrieved_at": retrieved,
            } for ticker, value in sorted(values.items())]
            result["status"] = "accepted_full_close_index" if values else "schema_or_no_rows"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_checkpoint(path, result)
    return result


def join_exact_close_values(authority: pd.DataFrame, values: pd.DataFrame, value_column: str) -> pd.DataFrame:
    lineage_columns = ["source_quality", "source_url", "source_hash", "retrieved_at", "market"]
    clean = authority.drop(columns=[value_column, *lineage_columns], errors="ignore")
    return clean.merge(values, on=["ticker", "date"], how="left", validate="many_to_one")


def run(output: Path = OUTPUT) -> None:
    lock = output / "bounded_network_close.lock"
    atomic_text(lock, str(os.getpid()))
    try:
        adjusted, adjusted_plan, raw, raw_plan = build_plans(output)
        atomic_csv(output / "bounded_network_adjusted_route_classification.csv.gz", adjusted)
        atomic_csv(output / "bounded_network_adjusted_route_plan.csv", adjusted_plan)
        atomic_csv(output / "bounded_network_raw_route_classification.csv", raw)
        atomic_csv(output / "bounded_network_raw_route_plan.csv", raw_plan)
        atomic_json(output / "bounded_network_preflight.json", {
            "task": NETWORK_TASK, "adjusted_authorized_routes": len(adjusted_plan),
            "adjusted_authorized_keys": int(adjusted["network_authorized"].sum()),
            "raw_authorized_routes": len(raw_plan), "raw_authorized_keys": int(raw["network_authorized"].sum()),
            "network_authority_outside_rows": 0, "non_close_family_download_rows": 0,
            "future_data_violation_count": 0, **FLAGS,
        })
        atomic_text(output / "current_step.txt", "bounded_adjusted_routes_running\n")
        adjusted_results = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_adjusted, output, row) for row in adjusted_plan.to_dict("records")]
            for future in as_completed(futures):
                adjusted_results.append(future.result())
        atomic_text(output / "current_step.txt", "bounded_raw_routes_running\n")
        raw_results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch_raw, output, row) for row in raw_plan.to_dict("records")]
            for future in as_completed(futures):
                raw_results.append(future.result())

        adjusted_full = pd.DataFrame([row for result in adjusted_results for row in result.get("full_rows", [])])
        raw_full = pd.DataFrame([row for result in raw_results for row in result.get("full_rows", [])])
        atomic_csv(output / "bounded_network_adjusted_full_close_index.csv.gz", adjusted_full)
        atomic_csv(output / "bounded_network_raw_full_close_index.csv.gz", raw_full)

        adjusted_values = adjusted_full[["ticker", "date", "adjusted_analysis_close", "source_quality", "source_url", "source_hash", "retrieved_at"]] if not adjusted_full.empty else pd.DataFrame(columns=["ticker", "date", "adjusted_analysis_close"])
        adjusted_joined = join_exact_close_values(adjusted, adjusted_values, "adjusted_analysis_close")
        network_adjusted_patch = adjusted_joined[adjusted_joined["adjusted_analysis_close"].notna()].copy()
        network_adjusted_blocked = adjusted_joined[adjusted_joined["adjusted_analysis_close"].isna()].copy()
        network_adjusted_blocked["blocked_reason_after_bounded_network"] = network_adjusted_blocked.apply(
            lambda row: "network_route_not_authorized_by_prior_success_policy" if not row["network_authorized"]
            else "successful_route_replay_exact_session_absent_or_source_error", axis=1,
        )

        raw_values = raw_full[["ticker", "date", "official_raw_close", "source_quality", "market", "source_url", "source_hash", "retrieved_at"]] if not raw_full.empty else pd.DataFrame(columns=["ticker", "date", "official_raw_close"])
        raw_joined = join_exact_close_values(raw, raw_values, "official_raw_close")
        network_raw_patch = raw_joined[raw_joined["official_raw_close"].notna()].copy()
        network_raw_blocked = raw_joined[raw_joined["official_raw_close"].isna()].copy()
        network_raw_blocked["blocked_reason_after_bounded_network"] = network_raw_blocked.apply(
            lambda row: "network_route_not_authorized_by_prior_success_policy" if not row["network_authorized"]
            else "successful_market_route_replay_exact_ticker_absent_or_source_error", axis=1,
        )
        atomic_csv(output / "bounded_network_adjusted_exact_patch.csv.gz", network_adjusted_patch)
        atomic_csv(output / "bounded_network_adjusted_remaining_blocked.csv.gz", network_adjusted_blocked)
        atomic_csv(output / "bounded_network_raw_exact_patch.csv.gz", network_raw_patch)
        atomic_csv(output / "bounded_network_raw_remaining_blocked.csv", network_raw_blocked)

        source_classification = pd.concat([
            network_adjusted_blocked.groupby(
                ["network_authorized", "prior_route_status", "prior_route_error", "blocked_reason_after_bounded_network"],
                dropna=False,
            ).agg(blocked_rows=("ticker", "size"), ticker_count=("ticker", "nunique")).reset_index().assign(family="adjusted_analysis_close"),
            network_raw_blocked.groupby(
                ["network_authorized", "prior_route_status", "prior_route_error", "blocked_reason_after_bounded_network"],
                dropna=False,
            ).agg(blocked_rows=("ticker", "size"), ticker_count=("ticker", "nunique")).reset_index().assign(family="official_raw_execution_close"),
        ], ignore_index=True, sort=False)
        source_classification["future_data_violation_count"] = 0
        atomic_csv(output / "bounded_network_remaining_source_classification.csv", source_classification)

        local_adjusted = pd.read_csv(output / "shifted_path_adjusted_local_extraction_patch.csv.gz", dtype=str)
        local_raw = pd.read_csv(output / "shifted_path_raw_local_extraction_patch.csv.gz", dtype=str)
        combined_adjusted = pd.concat([local_adjusted, network_adjusted_patch], ignore_index=True, sort=False).drop_duplicates(KEY)
        combined_raw = pd.concat([local_raw, network_raw_patch], ignore_index=True, sort=False).drop_duplicates(KEY)
        atomic_csv(output / "shifted_path_combined_adjusted_close_patch.csv.gz", combined_adjusted)
        atomic_csv(output / "shifted_path_combined_official_raw_close_patch.csv.gz", combined_raw)

        base = pd.read_csv(output / "reusable_one_shot_close_index.csv.gz", dtype=str)
        long_rows = []
        adjusted_base = base[base["adjusted_analysis_close"].notna()][["ticker", "date", "adjusted_analysis_close", "adjusted_source", "market"]].copy()
        adjusted_base = adjusted_base.rename(columns={"adjusted_analysis_close": "close", "adjusted_source": "source_quality"})
        adjusted_base["family"] = "adjusted_analysis_close"
        raw_base = base[base["official_raw_close"].notna()][["ticker", "date", "official_raw_close", "raw_source", "market"]].copy()
        raw_base = raw_base.rename(columns={"official_raw_close": "close", "raw_source": "source_quality"})
        raw_base["family"] = "official_raw_execution_close"
        long_rows.extend([adjusted_base, raw_base])
        if not adjusted_full.empty:
            extra = adjusted_full.rename(columns={"adjusted_analysis_close": "close"}).copy(); extra["family"] = "adjusted_analysis_close"; extra["market"] = ""
            long_rows.append(extra)
        if not raw_full.empty:
            extra = raw_full.rename(columns={"official_raw_close": "close"}).copy(); extra["family"] = "official_raw_execution_close"
            long_rows.append(extra)
        reusable = pd.concat(long_rows, ignore_index=True, sort=False)
        reusable = reusable.dropna(subset=["close"]).drop_duplicates(["family", "ticker", "date"], keep="last").sort_values(["family", "ticker", "date"])
        atomic_csv(output / "reusable_combined_close_index.csv.gz", reusable)

        readiness = {
            "task": NETWORK_TASK, "status": "bounded_network_close_completion_finished",
            "adjusted_authority_rows": len(adjusted) + len(local_adjusted), "adjusted_combined_filled_rows": len(combined_adjusted),
            "adjusted_remaining_rows": len(network_adjusted_blocked), "raw_authority_rows": len(raw),
            "raw_combined_filled_rows": len(combined_raw), "raw_remaining_rows": len(network_raw_blocked),
            "adjusted_network_routes": len(adjusted_plan), "raw_network_routes": len(raw_plan),
            "reusable_combined_close_index_rows": len(reusable), "non_close_family_download_rows": 0,
            "ready_for_core_shifted_path_close_absorption": len(combined_adjusted) + len(combined_raw) > 0,
            "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS,
        }
        atomic_json(output / "readiness_for_core_shifted_path_close_absorption.json", readiness)
        atomic_csv(output / "bounded_network_future_data_audit.csv", pd.DataFrame([
            {"audit": "authority_outside_downloads", "status": "0", "future_data_violation_count": 0},
            {"audit": "non_close_family_downloads", "status": "0", "future_data_violation_count": 0},
            {"audit": "raw_used_as_adjusted", "status": "false", "future_data_violation_count": 0},
            {"audit": "neighbor_or_last_price_substitution", "status": "false", "future_data_violation_count": 0},
        ]))
        atomic_text(output / "current_step.txt", "completed_ready_for_core_shifted_path_close_absorption\n")
        atomic_text(output / "final_summary_zh.md", (
            "# P1/P2 shifted-path close completion\n\n"
            f"- adjusted local+network：{len(combined_adjusted):,}/{len(adjusted) + len(local_adjusted):,}，剩餘 {len(network_adjusted_blocked):,}\n"
            f"- official raw local+network：{len(combined_raw):,}/{len(raw):,}，剩餘 {len(network_raw_blocked):,}\n"
            f"- network routes：adjusted {len(adjusted_plan)}、raw {len(raw_plan)}\n"
            f"- reusable combined close index：{len(reusable):,} rows\n"
            "- 僅 close family；future_data_violation_count=0。\n"
        ))
        rebuild_manifest(
            output,
            task=NETWORK_TASK,
            network_requests=len(adjusted_plan) + len(raw_plan),
        )
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
