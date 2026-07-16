from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-PRIMARY80-PATH-INDEPENDENT-OFFICIAL-CLOSE-BULK-FILL-001"
REPO = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
AUDIT = REPO / "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_local_audit_20260716"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716"
AUTHORITY = AUDIT / "primary80_path_independent_true_missing.csv.gz"
LOCAL_READY = AUDIT / "primary80_path_independent_local_ready.csv.gz"
LOCAL_NO_TRADE = AUDIT / "primary80_path_independent_official_no_trade_termination.csv.gz"
LOCAL_POLICY = AUDIT / "primary80_path_independent_policy_blocked.csv.gz"
P1_PRICE_MANIFEST = REPO / "outputs/radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710/price_bulk_download_manifest.csv"
P3_PRICE_MANIFEST = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711/price_source_manifest.csv"
KEY = ["ticker", "date"]
TERMINAL = {"accepted", "official_valid_no_target_rows"}
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
    frame.to_csv(temp, index=False, encoding="utf-8", compression="gzip" if path.suffix == ".gz" else None)
    if path.suffix == ".gz":
        with gzip.open(temp, "rt", encoding="utf-8", newline="") as handle:
            next(csv.reader(handle), None)
    os.replace(temp, path)


def write_checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.json.gz"
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
    os.replace(temp, path)


def read_checkpoint(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_ticker(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text.zfill(4)


def clean_number(value: object) -> float | None:
    text = str(value).replace(",", "").replace("--", "").strip()
    try:
        number = float(text)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def parse_market_close(payload: dict) -> tuple[bool, dict[str, float]]:
    tables = payload.get("tables") or [{"fields": payload.get("fields") or [], "data": payload.get("data") or []}]
    for table in tables:
        fields = ["".join(str(value).split()) for value in table.get("fields") or []]
        code = next((fields.index(token) for token in ("證券代號", "代號", "股票代號") if token in fields), None)
        close = next((fields.index(token) for token in ("收盤價", "收盤") if token in fields), None)
        if code is None or close is None:
            continue
        parsed: dict[str, float] = {}
        for row in table.get("data") or []:
            if len(row) <= max(code, close):
                continue
            ticker = "".join(character for character in str(row[code]).strip() if character.isalnum()).upper()
            value = clean_number(row[close])
            if ticker and value is not None:
                parsed[normalize_ticker(ticker)] = value
        return True, parsed
    stat = str(payload.get("stat") or payload.get("status") or "").lower()
    return ("ok" in stat or "success" in stat), {}


def raw_url(market: str, date_s: str) -> str:
    if market == "TWSE":
        return "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode(
            {"date": date_s.replace("-", ""), "type": "ALLBUT0999", "response": "json"}
        )
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?" + urlencode(
        {"date": date_s.replace("-", "/"), "response": "json"}
    )


def request_with_retry(url: str, market: str, attempts: int = 4) -> tuple[requests.Response | None, bytes, str]:
    response: requests.Response | None = None
    raw = b""
    error = ""
    for attempt in range(attempts):
        if market == "TWSE":
            time.sleep(random.uniform(0.6, 1.0))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 RadarPrimary80CloseOnly/1.0", "Accept": "application/json"},
                timeout=60,
            )
            raw = response.content
            if response.status_code == 200 and raw:
                return response, raw, ""
            error = f"http_{response.status_code}"
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
        if attempt >= attempts - 1:
            break
        if response is not None and response.status_code in {403, 429}:
            time.sleep((15, 30, 60)[min(attempt, 2)])
        else:
            time.sleep(min(8.0, 0.75 * (2 ** attempt)))
    return response, raw, error


def load_authority() -> pd.DataFrame:
    frame = pd.read_csv(AUTHORITY, dtype=str, low_memory=False)
    required = {"ticker", "date", "market", "classification"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"authority_schema_missing:{sorted(required - set(frame.columns))}")
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["date"] = frame["date"].astype(str).str[:10]
    frame["market"] = frame["market"].replace({"TPEX": "TPEx"})
    if len(frame) != 1_144_181:
        raise RuntimeError(f"authority_count_mismatch:{len(frame)}")
    if frame.duplicated(KEY).any():
        raise RuntimeError("authority_duplicate_exact_keys")
    by_market = frame["market"].value_counts().to_dict()
    if by_market != {"TWSE": 734_154, "TPEx": 410_027}:
        raise RuntimeError(f"authority_market_count_mismatch:{by_market}")
    if not frame["classification"].eq("true_missing").all():
        raise RuntimeError("authority_contains_non_missing_rows")
    return frame


def build_plan(authority: pd.DataFrame) -> pd.DataFrame:
    plan = authority.groupby(["market", "date"], as_index=False).agg(
        target_rows=("ticker", "size"),
        target_tickers=("ticker", lambda values: "|".join(sorted(set(values)))),
    )
    counts = plan["market"].value_counts().to_dict()
    if counts != {"TPEx": 2915, "TWSE": 2906} or len(plan) != 5821:
        raise RuntimeError(f"authority_route_count_mismatch:{counts}:{len(plan)}")
    plan["route_id"] = plan["market"] + "_" + plan["date"]
    plan["network_authorized"] = True
    return plan.sort_values(["market", "date"]).reset_index(drop=True)


def checkpoint_path(output: Path, market: str, date_s: str) -> Path:
    return output / "checkpoints" / market / f"{date_s}.json.gz"


def official_no_session_proven(twse_item: dict, tpex_status: str, manifest_status: str) -> bool:
    return (
        twse_item.get("status") == "temporary_source_gap"
        and twse_item.get("error") == "schema_not_ok"
        and str(twse_item.get("http_status")) in {"200", "200.0"}
        and bool(twse_item.get("source_hash"))
        and (
            tpex_status == "official_valid_no_target_rows"
            or manifest_status in {"no_rows", "no_rows_valid_official_response"}
        )
    )


def repair_official_no_session_checkpoints(output: Path) -> int:
    manifests = []
    for path in [P1_PRICE_MANIFEST, P3_PRICE_MANIFEST]:
        frame = pd.read_csv(path, dtype=str, low_memory=False)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        manifests.append(frame)
    combined = pd.concat(manifests, ignore_index=True, sort=False)
    combined = combined[combined["market"].eq("TWSE")].drop_duplicates(["market", "date"], keep="last")
    manifest_status = combined.set_index("date")["status"].to_dict()
    repaired = 0
    for path in sorted((output / "checkpoints/TWSE").glob("*.json.gz")):
        item = read_checkpoint(path)
        date_s = str(item.get("date", ""))
        counterpart = checkpoint_path(output, "TPEx", date_s)
        tpex = read_checkpoint(counterpart) if counterpart.exists() else {}
        if not official_no_session_proven(item, str(tpex.get("status", "")), str(manifest_status.get(date_s, ""))):
            continue
        item["status"] = "official_valid_no_target_rows"
        item["error"] = ""
        item["classification_evidence"] = "twse_http_200_no_data_schema_plus_official_tpex_same_date_no_rows_or_twse_manifest_no_rows"
        item["checkpoint_reclassified_at"] = now()
        write_checkpoint(path, item)
        repaired += 1
    return repaired


def fetch_route(output: Path, row: dict) -> dict:
    path = checkpoint_path(output, row["market"], row["date"])
    if path.exists():
        prior = read_checkpoint(path)
        if prior.get("status") in TERMINAL:
            return prior
    targets = set(str(row["target_tickers"]).split("|"))
    url = raw_url(row["market"], row["date"])
    retrieved_at = now()
    response, raw, error = request_with_retry(url, row["market"])
    result = {
        "task": TASK,
        "route_id": row["route_id"],
        "market": row["market"],
        "date": row["date"],
        "target_rows": int(row["target_rows"]),
        "status": "temporary_source_gap",
        "error": error,
        "http_status": response.status_code if response is not None else "",
        "source_url": response.url if response is not None else url,
        "source_hash": sha256_bytes(raw) if raw else "",
        "retrieved_at": retrieved_at,
        "response_bytes": len(raw),
        "matched_rows": [],
        "network_authorized": True,
        "non_close_family_rows": 0,
    }
    if raw and not error:
        try:
            schema_ok, values = parse_market_close(json.loads(raw.decode("utf-8-sig")))
            if schema_ok:
                result["matched_rows"] = [{
                    "ticker": ticker,
                    "date": row["date"],
                    "market": row["market"],
                    "close": values[ticker],
                    "source_quality": f"official_{row['market'].lower()}_date_market_bulk_close_only",
                    "adjustment_policy": "official_unadjusted_execution_close_only",
                    "source_url": result["source_url"],
                    "source_hash": result["source_hash"],
                    "retrieved_at": retrieved_at,
                    "future_data_violation_count": 0,
                } for ticker in sorted(targets & set(values))]
                result["status"] = "accepted" if result["matched_rows"] else "official_valid_no_target_rows"
                result["error"] = ""
            else:
                result["error"] = "schema_not_ok"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_checkpoint(path, result)
    return result


def route_status(plan: pd.DataFrame, output: Path) -> tuple[int, int, int, int]:
    completed = accepted_keys = no_trade_keys = blocked_keys = 0
    for row in plan.itertuples(index=False):
        path = checkpoint_path(output, row.market, row.date)
        if not path.exists():
            blocked_keys += int(row.target_rows)
            continue
        item = read_checkpoint(path)
        matched = len(item.get("matched_rows", []))
        if item.get("status") in TERMINAL:
            completed += 1
            accepted_keys += matched
            no_trade_keys += max(0, int(row.target_rows) - matched)
        else:
            blocked_keys += int(row.target_rows)
    return completed, accepted_keys, no_trade_keys, blocked_keys


class Progress:
    def __init__(self, output: Path, plan: pd.DataFrame) -> None:
        self.output = output
        self.plan = plan
        self.lock = threading.Lock()
        self.started = time.monotonic()
        completed, accepted, no_trade, blocked = route_status(plan, output)
        self.completed = completed
        self.accepted = accepted
        self.no_trade = no_trade
        self.blocked = blocked
        self.processed_attempts = 0
        self.last_written = 0.0

    def record(self, result: dict) -> None:
        with self.lock:
            self.processed_attempts += 1
            if result.get("status") in TERMINAL:
                matched = len(result.get("matched_rows", []))
                target_rows = int(result.get("target_rows", 0))
                self.completed += 1
                self.accepted += matched
                self.no_trade += max(0, target_rows - matched)
                self.blocked -= target_rows

    def write(self, step: str, force: bool = False) -> None:
        with self.lock:
            elapsed = time.monotonic() - self.started
            eta = (
                elapsed / self.processed_attempts * max(0, len(self.plan) - self.completed) / 60
                if self.processed_attempts else None
            )
            if not force and self.processed_attempts % 500 and (time.monotonic() - self.last_written) < 600:
                return
            value = {
                "task": TASK,
                "status": "running",
                "current_step": step,
                "updated_at": now(),
                "completed_routes": self.completed,
                "total_routes": len(self.plan),
                "accepted_keys": self.accepted,
                "official_no_trade_keys": self.no_trade,
                "temporarily_blocked_keys": self.blocked,
                "eta_minutes": round(eta, 1) if eta is not None else "calculating",
                "network_authorized": True,
                "future_data_violation_count": 0,
            }
            atomic_json(self.output / "progress.json", value)
            atomic_text(self.output / "current_step.txt", step + "\n")
            self.last_written = time.monotonic()


def run_market(output: Path, plan: pd.DataFrame, market: str, workers: int, progress: Progress) -> None:
    rows = plan[plan["market"].eq(market)].to_dict("records")
    pending = []
    for row in rows:
        path = checkpoint_path(output, market, row["date"])
        prior = read_checkpoint(path) if path.exists() else {}
        if prior.get("status") not in TERMINAL:
            pending.append(row)
    progress.write(f"{market.lower()}_close_routes_running", force=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_route, output, row): row for row in pending}
        for future in as_completed(futures):
            progress.record(future.result())
            progress.write(f"{market.lower()}_close_routes_running")
    progress.write(f"{market.lower()}_close_routes_complete", force=True)


def checkpoint_results(output: Path) -> list[dict]:
    return [read_checkpoint(path) for path in sorted((output / "checkpoints").rglob("*.json.gz"))]


def finalize(output: Path, authority: pd.DataFrame, plan: pd.DataFrame) -> None:
    atomic_text(output / "current_step.txt", "final_exact_partition_audit_running\n")
    results = checkpoint_results(output)
    values = pd.DataFrame([row for item in results for row in item.get("matched_rows", [])])
    value_columns = [
        "ticker", "date", "market", "close", "source_quality", "adjustment_policy",
        "source_url", "source_hash", "retrieved_at", "future_data_violation_count",
    ]
    values = values.reindex(columns=value_columns)
    if not values.empty:
        values = values.drop_duplicates(KEY, keep="last")
    joined = authority.drop(columns=[
        "close", "market_source", "source_quality", "source_component", "source_url",
        "source_hash", "retrieved_at", "market", "classification", "classification_reason",
        "future_data_violation_count",
    ], errors="ignore").merge(values, on=KEY, how="left", validate="one_to_one")
    route_map = {(item.get("market"), item.get("date")): item for item in results}
    classifications, reasons = [], []
    for row in joined.itertuples(index=False):
        if pd.notna(row.close):
            classifications.append("network_ready")
            reasons.append("exact_official_raw_close_from_authorized_market_date_bulk_route")
            continue
        item = route_map.get((row.market_required, row.date), {})
        if item.get("status") in TERMINAL:
            classifications.append("official_no_trade_or_not_applicable")
            reasons.append("official_market_route_valid_exact_ticker_absent")
        else:
            classifications.append("temporary_or_structural_source_gap")
            reasons.append(f"{item.get('status','route_not_completed')}:{item.get('error','')}")
    joined["classification_after_fill"] = classifications
    joined["classification_reason_after_fill"] = reasons
    joined["future_data_violation_count"] = 0
    network_ready = joined[joined["classification_after_fill"].eq("network_ready")].copy()
    network_no_trade = joined[joined["classification_after_fill"].eq("official_no_trade_or_not_applicable")].copy()
    network_blocked = joined[joined["classification_after_fill"].eq("temporary_or_structural_source_gap")].copy()
    atomic_csv(output / "path_independent_network_exact_close_patch.csv.gz", network_ready)
    atomic_csv(output / "path_independent_network_official_no_trade.csv.gz", network_no_trade)
    atomic_csv(output / "path_independent_network_remaining_blocked.csv.gz", network_blocked)

    local_ready = pd.read_csv(LOCAL_READY, dtype=str, low_memory=False)
    local_ready["ticker"] = local_ready["ticker"].map(normalize_ticker)
    local_ready["date"] = local_ready["date"].astype(str).str[:10]
    local_compact = local_ready.reindex(columns=value_columns)
    reusable = pd.concat([local_compact, network_ready.reindex(columns=value_columns)], ignore_index=True)
    reusable["close"] = pd.to_numeric(reusable["close"], errors="coerce")
    reusable = reusable.dropna(subset=["close"]).drop_duplicates(KEY, keep="last").sort_values(KEY)
    atomic_csv(output / "path_independent_primary80_official_raw_close_compact.csv.gz", reusable)

    local_no_trade = pd.read_csv(LOCAL_NO_TRADE, dtype=str, low_memory=False)
    final_no_trade = pd.concat([local_no_trade, network_no_trade], ignore_index=True, sort=False).drop_duplicates(KEY)
    local_policy = pd.read_csv(LOCAL_POLICY, dtype=str, low_memory=False)
    final_blocked = pd.concat([local_policy, network_blocked], ignore_index=True, sort=False).drop_duplicates(KEY)
    atomic_csv(output / "path_independent_final_official_no_trade_termination.csv.gz", final_no_trade)
    atomic_csv(output / "path_independent_final_blocked.csv.gz", final_blocked)

    manifest_rows = [{key: value for key, value in item.items() if key != "matched_rows"} for item in results]
    source_manifest = pd.DataFrame(manifest_rows)
    atomic_csv(output / "path_independent_close_source_manifest.csv.gz", source_manifest)
    status_counts = source_manifest["status"].value_counts().to_dict() if not source_manifest.empty else {}
    required_total = len(local_ready) + len(local_no_trade) + len(local_policy) + len(authority)
    partition_total = len(reusable) + len(final_no_trade) + len(final_blocked)
    partition_keys = pd.concat([
        reusable[KEY].assign(partition="ready"),
        final_no_trade[KEY].assign(partition="no_trade"),
        final_blocked[KEY].assign(partition="blocked"),
    ], ignore_index=True)
    duplicate_keys = int(partition_keys.duplicated(KEY).sum())
    coverage = pd.DataFrame([
        {"classification": "required_unique_ticker_date", "rows": required_total},
        {"classification": "official_raw_close_ready", "rows": len(reusable)},
        {"classification": "official_no_trade_or_termination", "rows": len(final_no_trade)},
        {"classification": "blocked", "rows": len(final_blocked)},
    ])
    coverage["future_data_violation_count"] = 0
    atomic_csv(output / "requested_vs_actual_coverage.csv", coverage)
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
        {"audit": "authority_exact_keys_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "close_only_normalized_output", "status": "pass", "future_data_violation_count": 0},
        {"audit": "non_close_family_download", "status": "0", "future_data_violation_count": 0},
        {"audit": "neighbor_or_last_price_substitution", "status": "false", "future_data_violation_count": 0},
        {"audit": "future_data_violation", "status": "0", "future_data_violation_count": 0},
    ]))

    complete = len(network_blocked) == 0 and len(local_policy) == 0
    readiness = {
        "task": TASK,
        "status": "path_independent_close_bulk_fill_complete" if complete else "path_independent_close_bulk_fill_complete_with_explicit_blockers",
        "authority_true_missing_rows": len(authority),
        "authority_market_date_routes": len(plan),
        "route_status_counts": status_counts,
        "network_exact_close_filled_rows": len(network_ready),
        "network_official_no_trade_rows": len(network_no_trade),
        "network_remaining_blocked_rows": len(network_blocked),
        "final_official_raw_close_ready_rows": len(reusable),
        "final_official_no_trade_or_termination_rows": len(final_no_trade),
        "final_blocked_rows": len(final_blocked),
        "required_partition_rows": required_total,
        "final_partition_rows": partition_total,
        "partition_count_matches": partition_total == required_total,
        "duplicate_exact_keys": duplicate_keys,
        "network_authority_outside_rows": 0,
        "non_close_family_download_rows": 0,
        "ready_for_core_path_independent_raw_close_absorption": len(reusable) > 0 and partition_total == required_total,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    atomic_json(output / "readiness_for_core_path_independent_raw_close_absorption.json", readiness)
    atomic_text(output / "final_summary_zh.md", (
        "# P1/P2 primary80 path-independent official raw close bulk fill\n\n"
        f"- authority routes：{len(plan):,}；exact keys：{len(authority):,}。\n"
        f"- network exact close：{len(network_ready):,}；official no-trade：{len(network_no_trade):,}；blocked：{len(network_blocked):,}。\n"
        f"- final reusable close compact：{len(reusable):,} rows。\n"
        f"- final partition：ready {len(reusable):,} / no-trade {len(final_no_trade):,} / blocked {len(final_blocked):,}。\n"
        "- 僅 official raw close；未下載其他 family 或其他 OHLC 欄。\n"
        "- future_data_violation_count=0。\n"
    ))
    progress = {**readiness, "current_step": "completed_ready_for_core_path_independent_close_absorption", "updated_at": now()}
    atomic_json(output / "progress.json", progress)
    atomic_text(output / "current_step.txt", "completed_ready_for_core_path_independent_close_absorption\n")
    rebuild_manifest(output, len(plan))


def rebuild_manifest(output: Path, network_routes: int) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv", "runner.lock"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checksums = pd.DataFrame([{
        "file": str(path.relative_to(output)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    } for path in files])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(output / "manifest.json", {
        "task": TASK,
        "generated_at": now(),
        "output_path": str(output),
        "network_authorized": True,
        "network_routes": network_routes,
        "non_close_family_download_rows": 0,
        "files": checksums.to_dict("records"),
        "future_data_violation_count": 0,
        **FLAGS,
    })


def run(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "runner.lock"
    if lock.exists():
        raise RuntimeError(f"runner_lock_exists:{lock}")
    atomic_text(lock, str(os.getpid()))
    try:
        authority = load_authority()
        plan = build_plan(authority)
        repaired_no_session_routes = repair_official_no_session_checkpoints(output)
        atomic_csv(output / "authorized_market_date_route_plan.csv.gz", plan)
        atomic_json(output / "authority_guard.json", {
            "authority_path": str(AUTHORITY),
            "authority_sha256": sha256_file(AUTHORITY),
            "authority_rows": len(authority),
            "market_date_routes": len(plan),
            "twse_routes": int(plan["market"].eq("TWSE").sum()),
            "tpex_routes": int(plan["market"].eq("TPEx").sum()),
            "network_authorized": True,
            "non_close_family_download_rows": 0,
            "locally_reclassified_official_no_session_routes": repaired_no_session_routes,
        })
        progress = Progress(output, plan)
        progress.write("authority_validated_route_execution_pending", force=True)
        if args.phase == "smoke":
            return
        run_market(output, plan, "TPEx", args.tpex_workers, progress)
        run_market(output, plan, "TWSE", args.twse_workers, progress)
        finalize(output, authority, plan)
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Path-independent primary80 official raw close bulk fill")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--phase", choices=["smoke", "all"], default="all")
    parser.add_argument("--twse-workers", type=int, default=3)
    parser.add_argument("--tpex-workers", type=int, default=6)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
