from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-AI-CONCENTRATION-DIFFUSION-WEEKLY-SWITCH-CLOSE-FILL-001"
REPO = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
CORE_OUTPUT = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p1_p2_ai_concentration_diffusion_weekly_switch_exact_nav_contract_20260718"
)
AUTHORITY = CORE_OUTPUT / "weekly_switch_bounded_official_raw_execution_gap_ledger.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718"
LOCAL_00631L = (
    REPO
    / "outputs/radar_vnext_daily_incumbent_challenger_00631l_benchmark_price_gap_fill_20260710"
    / "daily_incumbent_challenger_00631L_benchmark_price_unadjusted_close_rows.csv"
)
LISTING_MASTER = (
    REPO
    / "outputs/radar_dynamic_pool1_listing_delisting_suspension_master_20260703"
    / "accepted_listing_metadata_rows.csv"
)
TERMINAL = {"accepted", "official_no_trade_prelisting", "official_valid_no_target"}
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
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


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".csv.gz" if path.suffix == ".gz" else ".csv"
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}{suffix}"
    frame.to_csv(
        temp,
        index=False,
        encoding="utf-8",
        compression="gzip" if path.suffix == ".gz" else None,
    )
    if path.suffix == ".gz":
        with gzip.open(temp, "rt", encoding="utf-8", newline="") as handle:
            next(csv.reader(handle), None)
    os.replace(temp, path)


def checkpoint_path(output: Path, ticker: str, month: str) -> Path:
    return output / "checkpoints" / ticker / f"{month}.json.gz"


def write_checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.json.gz"
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
    os.replace(temp, path)


def read_checkpoint(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def clean_number(value: object) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if text in {"", "-", "--", "---"}:
        return None
    try:
        number = float(text)
        return number if number > 0 else None
    except ValueError:
        return None


def ad_date(value: object) -> str:
    year, month, day = [int(part) for part in str(value).strip().split("/")]
    if year < 1911:
        year += 1911
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_twse_stock_day(payload: dict) -> tuple[bool, dict[str, float]]:
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    lookup = {"".join(str(value).split()): index for index, value in enumerate(fields)}
    if "日期" not in lookup or "收盤價" not in lookup:
        stat = str(payload.get("stat") or "").upper()
        return ("OK" in stat or "沒有符合條件的資料" in stat), {}
    rows: dict[str, float] = {}
    for raw in data:
        try:
            date_s = ad_date(raw[lookup["日期"]])
            close = clean_number(raw[lookup["收盤價"]])
        except (IndexError, TypeError, ValueError):
            continue
        if close is not None:
            rows[date_s] = close
    return True, rows


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    if not {"ticker", "date"}.issubset(frame.columns):
        raise RuntimeError("authority_schema_missing")
    frame = frame[["ticker", "date"]].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    counts = frame.groupby("ticker").size().to_dict()
    if len(frame) != 55 or counts != {"00631L": 48, "6669": 7}:
        raise RuntimeError(f"authority_scope_changed:{len(frame)}:{counts}")
    return frame


def load_6669_listing_evidence(path: Path) -> dict:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    rows = frame[
        frame["ticker"].astype(str).eq("6669")
        & frame["market"].astype(str).eq("TWSE")
        & frame["event_type"].astype(str).eq("listing")
    ].copy()
    if len(rows) != 1 or rows.iloc[0]["event_date"] != "2019-03-27":
        raise RuntimeError("6669_listing_evidence_missing_or_ambiguous")
    row = rows.iloc[0]
    return {
        "listing_date": row["event_date"],
        "source_url": row.get("source_url", ""),
        "source_route": row.get("source_route", ""),
        "source_hash": sha256_file(path),
        "source_path": str(path),
    }


def load_local_00631l(path: Path, authority: pd.DataFrame) -> list[dict]:
    if not path.exists():
        return []
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    target = authority[authority["ticker"].eq("00631L")]
    matched = frame.merge(target, on=["ticker", "date"], how="inner")
    rows = []
    for _, row in matched.iterrows():
        close = clean_number(row.get("close"))
        if close is None:
            continue
        rows.append(
            {
                "ticker": "00631L",
                "date": row["date"],
                "market": "TWSE",
                "close": close,
                "source_quality": row.get("source_quality", "official_twse_selected_etf_month_close"),
                "adjustment_policy": "official_unadjusted_execution_close_only",
                "source_url": row.get("source_url", ""),
                "source_hash": row.get("raw_sha256", ""),
                "retrieved_at": row.get("retrieved_at_utc", ""),
                "source_reuse": "existing_official_selected_etf_package",
                "future_data_violation_count": 0,
            }
        )
    return rows


def route_url(ticker: str, month: str) -> str:
    return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + urlencode(
        {"date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json"}
    )


def request_month(ticker: str, month: str, attempts: int = 4) -> dict:
    url = route_url(ticker, month)
    response: requests.Response | None = None
    raw = b""
    error = ""
    retrieved_at = now()
    for attempt in range(attempts):
        time.sleep(random.uniform(0.7, 1.1))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 RadarWeeklySwitchCloseOnly/1.0"},
                timeout=60,
            )
            raw = response.content
            if response.status_code == 200 and raw:
                error = ""
                break
            error = f"http_{response.status_code}"
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
        if attempt < attempts - 1:
            if response is not None and response.status_code in {403, 429}:
                time.sleep((15, 30, 60)[min(attempt, 2)])
            else:
                time.sleep(min(8.0, 0.75 * (2**attempt)))
    result = {
        "task": TASK,
        "ticker": ticker,
        "month": month,
        "market": "TWSE",
        "source_url": response.url if response is not None else url,
        "http_status": response.status_code if response is not None else "",
        "source_hash": sha256_bytes(raw) if raw else "",
        "retrieved_at": retrieved_at,
        "response_bytes": len(raw),
        "network_attempted": True,
        "status": "temporary_source_gap",
        "error": error,
        "rows": [],
        "future_data_violation_count": 0,
    }
    if raw and not error:
        try:
            schema_ok, rows = parse_twse_stock_day(json.loads(raw.decode("utf-8-sig")))
            if schema_ok:
                result["status"] = "accepted"
                result["error"] = ""
                result["rows"] = [{"date": date_s, "close": close} for date_s, close in rows.items()]
            else:
                result["error"] = "schema_not_ok"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    return result


def build_routes(authority: pd.DataFrame, locally_ready: set[tuple[str, str]], listing_date: str) -> list[tuple[str, str]]:
    pending = authority[
        ~authority.apply(lambda row: (row["ticker"], row["date"]) in locally_ready, axis=1)
    ].copy()
    pending = pending[~((pending["ticker"].eq("6669")) & (pending["date"] < listing_date))]
    pending["month"] = pending["date"].str[:7]
    return sorted({(row.ticker, row.month) for row in pending.itertuples()})


def finalize(
    output: Path,
    authority: pd.DataFrame,
    local_rows: list[dict],
    listing: dict,
    route_results: list[dict],
) -> dict:
    rows = list(local_rows)
    result_lookup = {(item["ticker"], item["month"]): item for item in route_results}
    for item in route_results:
        for row in item.get("rows", []):
            rows.append(
                {
                    "ticker": item["ticker"],
                    "date": row["date"],
                    "market": "TWSE",
                    "close": row["close"],
                    "source_quality": "official_twse_selected_ticker_month_close_only",
                    "adjustment_policy": "official_unadjusted_execution_close_only",
                    "source_url": item["source_url"],
                    "source_hash": item["source_hash"],
                    "retrieved_at": item["retrieved_at"],
                    "source_reuse": "network_authority_ticker_month",
                    "future_data_violation_count": 0,
                }
            )
    patch = pd.DataFrame(rows).reindex(
        columns=[
            "ticker", "date", "market", "close", "source_quality", "adjustment_policy",
            "source_url", "source_hash", "retrieved_at", "source_reuse",
            "future_data_violation_count",
        ]
    )
    if not patch.empty:
        patch = (
            patch.merge(authority, on=["ticker", "date"], how="inner")
            .drop_duplicates(["ticker", "date"], keep="first")
            .sort_values(["ticker", "date"])
        )
    ready_keys = set(zip(patch["ticker"], patch["date"])) if not patch.empty else set()
    no_trade_rows = []
    blocked_rows = []
    for row in authority.itertuples():
        key = (row.ticker, row.date)
        if key in ready_keys:
            continue
        if row.ticker == "6669" and row.date < listing["listing_date"]:
            no_trade_rows.append(
                {
                    "ticker": row.ticker,
                    "date": row.date,
                    "market": "TWSE",
                    "classification": "official_no_trade_prelisting",
                    "reason": f"target_date_before_official_twse_listing_date_{listing['listing_date']}",
                    "source_url": listing["source_url"],
                    "source_hash": listing["source_hash"],
                    "retrieved_at": "",
                    "future_data_violation_count": 0,
                }
            )
            continue
        item = result_lookup.get((row.ticker, row.date[:7]), {})
        classification = (
            "official_valid_no_target"
            if item.get("status") == "accepted"
            else "temporary_source_gap"
        )
        target = no_trade_rows if classification == "official_valid_no_target" else blocked_rows
        target.append(
            {
                "ticker": row.ticker,
                "date": row.date,
                "market": "TWSE",
                "classification": classification,
                "reason": (
                    "exact_ticker_date_absent_from_valid_official_selected_ticker_month_response"
                    if classification == "official_valid_no_target"
                    else item.get("error", "route_not_attempted")
                ),
                "source_url": item.get("source_url", ""),
                "source_hash": item.get("source_hash", ""),
                "retrieved_at": item.get("retrieved_at", ""),
                "future_data_violation_count": 0,
            }
        )
    partition_columns = [
        "ticker", "date", "market", "classification", "reason", "source_url",
        "source_hash", "retrieved_at", "future_data_violation_count",
    ]
    no_trade = pd.DataFrame(no_trade_rows).reindex(columns=partition_columns)
    blocked = pd.DataFrame(blocked_rows).reindex(columns=partition_columns)
    route_manifest = pd.DataFrame(
        [{key: value for key, value in item.items() if key != "rows"} for item in route_results]
    )
    atomic_csv(output / "weekly_switch_exact_official_raw_close_patch.csv.gz", patch)
    atomic_csv(output / "weekly_switch_exact_official_no_trade.csv", no_trade)
    atomic_csv(output / "weekly_switch_exact_official_raw_close_blocked.csv", blocked)
    atomic_csv(output / "weekly_switch_close_source_manifest.csv", route_manifest)
    coverage = pd.DataFrame(
        [
            {"classification": "requested_exact_keys", "rows": len(authority)},
            {"classification": "official_raw_close_ready", "rows": len(patch)},
            {"classification": "official_no_trade_or_no_target", "rows": len(no_trade)},
            {"classification": "blocked", "rows": len(blocked)},
        ]
    )
    coverage["future_data_violation_count"] = 0
    atomic_csv(output / "requested_vs_actual_coverage.csv", coverage)
    atomic_csv(
        output / "future_data_audit.csv",
        pd.DataFrame(
            [
                {"audit": "authority_exact_55_keys_only", "status": "pass", "future_data_violation_count": 0},
                {"audit": "official_raw_close_only", "status": "pass", "future_data_violation_count": 0},
                {"audit": "neighbor_last_benchmark_substitution", "status": "false", "future_data_violation_count": 0},
                {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0},
            ]
        ),
    )
    partition = len(patch) + len(no_trade) + len(blocked)
    readiness = {
        "task": TASK,
        "status": "complete_ready_for_core_absorption" if not len(blocked) else "complete_with_explicit_source_blockers",
        "requested_exact_keys": len(authority),
        "official_raw_close_ready_rows": len(patch),
        "official_no_trade_or_no_target_rows": len(no_trade),
        "blocked_rows": len(blocked),
        "partition_rows": partition,
        "partition_matches_authority": partition == len(authority),
        "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()) if not patch.empty else 0,
        "network_routes": len(route_results),
        "network_outside_authority_rows": 0,
        "non_close_family_download_rows": 0,
        "ready_for_core_weekly_switch_close_absorption": partition == len(authority) and not len(blocked),
        "ready_for_experiments": False,
        "data_readiness_blocked_only": bool(len(blocked)),
        "may_be_used_to_reject_strategy": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    atomic_json(output / "readiness_for_core_weekly_switch_close_absorption.json", readiness)
    atomic_text(
        output / "final_summary_zh.md",
        "# AI集中／大盤擴散 weekly switch exact close fill\n\n"
        f"- authority exact keys：{len(authority)}。\n"
        f"- official raw close ready：{len(patch)}。\n"
        f"- official no-trade/no-target：{len(no_trade)}。\n"
        f"- blocked：{len(blocked)}。\n"
        "- 僅處理 official raw close；未下載其他資料 family，未計績效。\n"
        "- future_data_violation_count=0。\n",
    )
    return readiness


def rebuild_manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv", "runner.lock"}
    files = sorted(
        path for path in output.rglob("*") if path.is_file() and path.name not in excluded
    )
    checksums = pd.DataFrame(
        [
            {
                "file": str(path.relative_to(output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ]
    )
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(
        output / "manifest.json",
        {
            "task": TASK,
            "generated_at": now(),
            "output_path": str(output),
            "authority_path": str(AUTHORITY),
            "authority_sha256": sha256_file(AUTHORITY),
            "network_scope": "exact 55 authority keys; TWSE selected ticker-month close-only",
            "readiness": readiness,
            "files": checksums.to_dict("records"),
            "future_data_violation_count": 0,
            **FLAGS,
        },
    )


def run(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "runner.lock"
    if lock.exists():
        raise RuntimeError(f"runner_lock_exists:{lock}")
    atomic_text(lock, str(os.getpid()))
    try:
        authority = load_authority(args.authority)
        listing = load_6669_listing_evidence(LISTING_MASTER)
        local_rows = load_local_00631l(LOCAL_00631L, authority)
        locally_ready = {(row["ticker"], row["date"]) for row in local_rows}
        routes = build_routes(authority, locally_ready, listing["listing_date"])
        atomic_json(
            output / "authority_guard.json",
            {
                "authority_path": str(args.authority),
                "authority_sha256": sha256_file(args.authority),
                "requested_exact_keys": len(authority),
                "ticker_counts": authority.groupby("ticker").size().to_dict(),
                "local_exact_reused_rows": len(local_rows),
                "official_prelisting_no_trade_rows": int(
                    ((authority["ticker"].eq("6669")) & (authority["date"] < listing["listing_date"])).sum()
                ),
                "network_authorized_ticker_month_routes": len(routes),
                "non_close_family_download_rows": 0,
                "future_data_violation_count": 0,
            },
        )
        route_results = []
        for index, (ticker, month) in enumerate(routes, 1):
            path = checkpoint_path(output, ticker, month)
            if path.exists():
                prior = read_checkpoint(path)
                if prior.get("status") == "accepted":
                    route_results.append(prior)
                    continue
            atomic_text(
                output / "current_step.txt",
                f"status=running_close_only_routes\ncompleted_routes={index - 1}\ntotal_routes={len(routes)}\n",
            )
            item = request_month(ticker, month)
            write_checkpoint(path, item)
            route_results.append(item)
            atomic_json(
                output / "progress.json",
                {
                    "task": TASK,
                    "status": "running",
                    "completed_routes": index,
                    "total_routes": len(routes),
                    "accepted_routes": sum(result.get("status") == "accepted" for result in route_results),
                    "blocked_routes": sum(result.get("status") != "accepted" for result in route_results),
                    "updated_at": now(),
                    "future_data_violation_count": 0,
                },
            )
        readiness = finalize(output, authority, local_rows, listing, route_results)
        atomic_json(
            output / "progress.json",
            {**readiness, "status": "complete", "current_step": "completed_for_core_absorption", "updated_at": now()},
        )
        atomic_text(
            output / "current_step.txt",
            "status=complete\nresume_step=none\nnext_owner=Core_Data_absorption_and_one_rechain\n",
        )
        rebuild_manifest(output, readiness)
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
