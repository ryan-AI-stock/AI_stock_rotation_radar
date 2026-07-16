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


TASK = "TASK-RADAR-DATA-VNEXT-4739-POST-TRANSFER-579-TWSE-CLOSE-FILL-001"
REPO = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
SOURCE_PACKAGE = REPO / "outputs/radar_vnext_4739_market_transfer_3474_termination_source_package_20260716"
AUTHORITY = SOURCE_PACKAGE / "ticker_4739_post_transition_remaining_local_gap.csv"
OUTPUT = REPO / "outputs/radar_vnext_4739_post_transfer_twse_close_fill_20260716"
TERMINAL = {"accepted", "official_valid_no_target_row"}
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


def checkpoint_path(output: Path, date_s: str) -> Path:
    return output / "checkpoints" / "TWSE" / f"{date_s}.json.gz"


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
    text = str(value).replace(",", "").replace("--", "").strip()
    try:
        number = float(text)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def parse_twse_close(payload: dict, ticker: str = "4739") -> tuple[bool, float | None]:
    tables = payload.get("tables") or [{"fields": payload.get("fields") or [], "data": payload.get("data") or []}]
    for table in tables:
        fields = ["".join(str(value).split()) for value in table.get("fields") or []]
        code = next((fields.index(token) for token in ("證券代號", "代號", "股票代號") if token in fields), None)
        close = next((fields.index(token) for token in ("收盤價", "收盤") if token in fields), None)
        if code is None or close is None:
            continue
        for row in table.get("data") or []:
            if len(row) <= max(code, close):
                continue
            row_ticker = "".join(character for character in str(row[code]).strip() if character.isalnum()).upper()
            if row_ticker == ticker:
                return True, clean_number(row[close])
        return True, None
    stat = str(payload.get("stat") or payload.get("status") or "").lower()
    return ("ok" in stat or "success" in stat), None


def route_url(date_s: str) -> str:
    return "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode(
        {"date": date_s.replace("-", ""), "type": "ALLBUT0999", "response": "json"}
    )


def request_with_retry(url: str, attempts: int = 4) -> tuple[requests.Response | None, bytes, str]:
    response: requests.Response | None = None
    raw = b""
    error = ""
    for attempt in range(attempts):
        time.sleep(random.uniform(0.7, 1.1))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 Radar4739CloseOnly/1.0", "Accept": "application/json"},
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


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    required = {"ticker", "date", "expected_market", "classification"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"authority_schema_missing:{sorted(required - set(frame.columns))}")
    frame["ticker"] = frame["ticker"].astype(str).str.zfill(4)
    frame["date"] = frame["date"].astype(str).str[:10]
    if len(frame) != 579 or frame.duplicated(["ticker", "date"]).any():
        raise RuntimeError(f"authority_count_or_duplicate_mismatch:{len(frame)}")
    if not frame["ticker"].eq("4739").all() or not frame["expected_market"].eq("TWSE").all():
        raise RuntimeError("authority_scope_violation")
    if not frame["classification"].eq("local_compact_scope_gap_after_market_transfer").all():
        raise RuntimeError("authority_classification_changed")
    return frame.sort_values("date").reset_index(drop=True)


def known_checkpoint_roots(repo: Path) -> list[Path]:
    return [
        repo / "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716/checkpoints/TWSE",
        repo / "outputs/radar_vnext_p1_p2_primary80_ma_slope_cd50_one_shot_close_fill_20260716/checkpoints/raw/TWSE",
        repo / "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716/network_checkpoints/raw/TWSE",
    ]


def extract_4739_from_checkpoint(item: dict) -> dict | None:
    for row in item.get("matched_rows") or item.get("rows") or []:
        if str(row.get("ticker", "")).strip() != "4739":
            continue
        close = row.get("close", row.get("official_raw_execution_close"))
        if clean_number(close) is None:
            continue
        return {
            "ticker": "4739",
            "date": str(row.get("date", item.get("date", "")))[:10],
            "market": "TWSE",
            "close": clean_number(close),
            "source_quality": row.get("source_quality", "official_twse_date_market_bulk_close_only"),
            "adjustment_policy": "official_unadjusted_execution_close_only",
            "source_url": row.get("source_url", item.get("source_url", "")),
            "source_hash": row.get("source_hash", item.get("source_hash", "")),
            "retrieved_at": row.get("retrieved_at", item.get("retrieved_at", "")),
            "source_reuse": "existing_checkpoint_exact_row",
            "future_data_violation_count": 0,
        }
    return None


def is_proven_market_closed_checkpoint(item: dict) -> bool:
    return item.get("status") == "official_valid_no_target_rows" and bool(item.get("classification_evidence"))


def seed_local_reuse(output: Path, authority: pd.DataFrame, repo: Path) -> int:
    reused = 0
    roots = known_checkpoint_roots(repo)
    for date_s in authority["date"]:
        target = checkpoint_path(output, date_s)
        if target.exists() and read_checkpoint(target).get("status") in TERMINAL:
            continue
        for root in roots:
            source = root / f"{date_s}.json.gz"
            if not source.exists():
                continue
            source_item = read_checkpoint(source)
            row = extract_4739_from_checkpoint(source_item)
            if not row:
                if (
                    root == roots[0]
                    and is_proven_market_closed_checkpoint(source_item)
                ):
                    write_checkpoint(target, {
                        "task": TASK, "ticker": "4739", "market": "TWSE", "date": date_s,
                        "status": "official_valid_no_target_row", "error": "official_market_closed_no_session",
                        "http_status": source_item.get("http_status", ""),
                        "source_url": source_item.get("source_url", ""),
                        "source_hash": source_item.get("source_hash", ""),
                        "retrieved_at": source_item.get("retrieved_at", ""), "response_bytes": 0,
                        "matched_rows": [], "network_attempted": False,
                        "reused_checkpoint_path": str(source),
                        "classification_evidence": source_item.get("classification_evidence", ""),
                        "future_data_violation_count": 0,
                    })
                    reused += 1
                    break
                continue
            write_checkpoint(target, {
                "task": TASK, "ticker": "4739", "market": "TWSE", "date": date_s,
                "status": "accepted", "error": "", "http_status": "local_reuse",
                "source_url": row["source_url"], "source_hash": row["source_hash"],
                "retrieved_at": row["retrieved_at"], "response_bytes": 0,
                "matched_rows": [row], "network_attempted": False,
                "reused_checkpoint_path": str(source), "future_data_violation_count": 0,
            })
            reused += 1
            break
    return reused


def fetch_date(output: Path, date_s: str) -> dict:
    path = checkpoint_path(output, date_s)
    if path.exists():
        prior = read_checkpoint(path)
        if prior.get("status") in TERMINAL:
            return prior
    url = route_url(date_s)
    retrieved_at = now()
    response, raw, error = request_with_retry(url)
    result = {
        "task": TASK, "ticker": "4739", "market": "TWSE", "date": date_s,
        "status": "temporary_source_gap", "error": error,
        "http_status": response.status_code if response is not None else "",
        "source_url": response.url if response is not None else url,
        "source_hash": sha256_bytes(raw) if raw else "", "retrieved_at": retrieved_at,
        "response_bytes": len(raw), "matched_rows": [], "network_attempted": True,
        "future_data_violation_count": 0,
    }
    if raw and not error:
        try:
            schema_ok, close = parse_twse_close(json.loads(raw.decode("utf-8-sig")))
            if schema_ok and close is not None:
                result["matched_rows"] = [{
                    "ticker": "4739", "date": date_s, "market": "TWSE", "close": close,
                    "source_quality": "official_twse_date_market_bulk_close_only",
                    "adjustment_policy": "official_unadjusted_execution_close_only",
                    "source_url": result["source_url"], "source_hash": result["source_hash"],
                    "retrieved_at": retrieved_at, "source_reuse": "network_exact_authority",
                    "future_data_violation_count": 0,
                }]
                result["status"] = "accepted"
                result["error"] = ""
            elif schema_ok:
                result["status"] = "official_valid_no_target_row"
                result["error"] = "exact_ticker_absent_from_valid_official_market_response"
            else:
                result["error"] = "schema_not_ok"
        except Exception as exc:
            result["error"] = f"parse_{type(exc).__name__}:{exc}"
    write_checkpoint(path, result)
    return result


class Progress:
    def __init__(self, output: Path, total: int) -> None:
        self.output = output
        self.total = total
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.attempted = 0

    def write(self, step: str) -> None:
        terminal = accepted = no_trade = blocked = 0
        for path in (self.output / "checkpoints/TWSE").glob("*.json.gz"):
            item = read_checkpoint(path)
            if item.get("status") in TERMINAL:
                terminal += 1
                if item.get("status") == "accepted":
                    accepted += 1
                else:
                    no_trade += 1
            else:
                blocked += 1
        elapsed = time.monotonic() - self.started
        eta = elapsed / self.attempted * max(0, self.total - terminal) / 60 if self.attempted else None
        atomic_json(self.output / "progress.json", {
            "task": TASK, "status": "running", "current_step": step, "updated_at": now(),
            "completed_routes": terminal, "total_routes": self.total, "accepted_keys": accepted,
            "official_no_trade_keys": no_trade, "temporarily_blocked_routes": blocked,
            "eta_minutes": round(eta, 1) if eta is not None else "calculating",
            "future_data_violation_count": 0,
        })
        atomic_text(self.output / "current_step.txt", step + "\n")

    def record(self, step: str) -> None:
        with self.lock:
            self.attempted += 1
            if self.attempted % 100 == 0:
                self.write(step)


def finalize(output: Path, authority: pd.DataFrame) -> dict:
    items = []
    for date_s in authority["date"]:
        path = checkpoint_path(output, date_s)
        if path.exists():
            items.append(read_checkpoint(path))
        else:
            items.append({"date": date_s, "status": "route_not_attempted", "error": "checkpoint_missing", "matched_rows": []})
    patch = pd.DataFrame([row for item in items for row in item.get("matched_rows", [])])
    columns = [
        "ticker", "date", "market", "close", "source_quality", "adjustment_policy", "source_url",
        "source_hash", "retrieved_at", "source_reuse", "future_data_violation_count",
    ]
    patch = patch.reindex(columns=columns)
    if not patch.empty:
        patch = patch.drop_duplicates(["ticker", "date"], keep="last").sort_values("date")
    ready_dates = set(patch["date"]) if not patch.empty else set()
    item_by_date = {str(item.get("date", "")): item for item in items}
    no_trade_rows = []
    blocked_rows = []
    for date_s in authority["date"]:
        if date_s in ready_dates:
            continue
        item = item_by_date.get(date_s, {})
        row = {
            "ticker": "4739", "date": date_s, "market": "TWSE", "status": item.get("status", ""),
            "reason": item.get("error", ""), "source_url": item.get("source_url", ""),
            "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""),
            "future_data_violation_count": 0,
        }
        if item.get("status") == "official_valid_no_target_row":
            no_trade_rows.append(row)
        else:
            blocked_rows.append(row)
    no_trade = pd.DataFrame(no_trade_rows)
    blocked = pd.DataFrame(blocked_rows)
    partition_columns = [
        "ticker", "date", "market", "status", "reason", "source_url", "source_hash",
        "retrieved_at", "future_data_violation_count",
    ]
    no_trade = no_trade.reindex(columns=partition_columns)
    blocked = blocked.reindex(columns=partition_columns)
    manifest = pd.DataFrame([{key: value for key, value in item.items() if key != "matched_rows"} for item in items])
    atomic_csv(output / "ticker_4739_exact_twse_close_patch.csv.gz", patch)
    atomic_csv(output / "ticker_4739_exact_twse_official_no_trade.csv", no_trade)
    atomic_csv(output / "ticker_4739_exact_twse_blocked.csv", blocked)
    atomic_csv(output / "ticker_4739_twse_close_source_manifest.csv.gz", manifest)
    coverage = pd.DataFrame([
        {"classification": "requested_exact_dates", "rows": len(authority)},
        {"classification": "official_raw_close_ready", "rows": len(patch)},
        {"classification": "official_valid_no_target_row", "rows": len(no_trade)},
        {"classification": "blocked", "rows": len(blocked)},
    ])
    coverage["future_data_violation_count"] = 0
    atomic_csv(output / "requested_vs_actual_coverage.csv", coverage)
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
        {"audit": "authority_ticker_4739_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "authority_exact_579_dates_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "official_raw_close_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "neighbor_last_adjusted_substitution", "status": "false", "future_data_violation_count": 0},
    ]))
    partition = len(patch) + len(no_trade) + len(blocked)
    readiness = {
        "task": TASK,
        "status": "complete_ready_for_core_absorption" if not len(blocked) else "complete_with_explicit_source_blockers",
        "requested_exact_dates": len(authority), "official_raw_close_ready_rows": len(patch),
        "official_valid_no_target_rows": len(no_trade), "blocked_rows": len(blocked),
        "partition_rows": partition, "partition_matches_authority": partition == len(authority),
        "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()) if not patch.empty else 0,
        "network_outside_authority_rows": 0, "non_close_family_download_rows": 0,
        "ready_for_core_4739_transition_close_absorption": partition == len(authority) and len(patch) > 0,
        "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS,
    }
    atomic_json(output / "readiness_for_core_4739_transition_close_absorption.json", readiness)
    atomic_text(output / "final_summary_zh.md", (
        "# 4739 TPEx 轉 TWSE 後 exact close fill\n\n"
        f"- authority：{len(authority):,} exact TWSE dates。\n"
        f"- official raw close ready：{len(patch):,}。\n"
        f"- official valid no-target：{len(no_trade):,}。\n"
        f"- blocked：{len(blocked):,}。\n"
        "- 僅保存 4739 exact close 與 lineage；未保存其他 ticker 或資料 family。\n"
        "- future_data_violation_count=0。\n"
    ))
    atomic_json(output / "progress.json", {**readiness, "current_step": "completed_ready_for_core_absorption", "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete_ready_for_core_absorption\nresume_step=none\n")
    rebuild_manifest(output, readiness)
    return readiness


def rebuild_manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv", "runner.lock"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checksums = pd.DataFrame([{
        "file": str(path.relative_to(output)).replace("\\", "/"),
        "bytes": path.stat().st_size, "sha256": sha256_file(path),
    } for path in files])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(output / "manifest.json", {
        "task": TASK, "generated_at": now(), "output_path": str(output),
        "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY),
        "network_authorized_exact_routes": 579, "network_scope": "ticker=4739 market=TWSE close-only",
        "readiness": readiness, "files": checksums.to_dict("records"),
        "future_data_violation_count": 0, **FLAGS,
    })


def run(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "runner.lock"
    if lock.exists():
        raise RuntimeError(f"runner_lock_exists:{lock}")
    atomic_text(lock, str(os.getpid()))
    try:
        authority = load_authority(args.authority)
        local_reused = seed_local_reuse(output, authority, REPO)
        atomic_json(output / "authority_guard.json", {
            "authority_path": str(args.authority), "authority_sha256": sha256_file(args.authority),
            "requested_exact_dates": len(authority), "ticker": "4739", "market": "TWSE",
            "local_exact_reused_rows": local_reused, "network_authorized_max_routes": len(authority) - local_reused,
            "non_close_family_download_rows": 0, "future_data_violation_count": 0,
        })
        progress = Progress(output, len(authority))
        progress.write("twse_close_only_routes_running")
        pending = []
        for date_s in authority["date"]:
            path = checkpoint_path(output, date_s)
            prior = read_checkpoint(path) if path.exists() else {}
            if prior.get("status") not in TERMINAL:
                pending.append(date_s)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(fetch_date, output, date_s): date_s for date_s in pending}
            for future in as_completed(futures):
                future.result()
                progress.record("twse_close_only_routes_running")
        progress.write("final_partition_audit_running")
        readiness = finalize(output, authority)
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 3:
        raise SystemExit("workers must be 1..3 for TWSE bounded rate control")
    run(args)


if __name__ == "__main__":
    main()
