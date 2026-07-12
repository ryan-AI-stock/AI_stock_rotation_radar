from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
P1 = ROOT / "outputs/radar_vnext_p1_full_lifecycle_minimum_data_acquisition_20260710"
OUT = ROOT / "outputs/radar_vnext_p1_free_historical_source_reopen_audit_20260712"
START, END = "2015-01-02", "2022-12-29"
FIELDS = [
    "date", "ticker", "name", "market", "foreign_net", "trust_net", "dealer_net",
    "institutional_total_net", "source_quality", "available_at_policy", "source_url",
    "source_hash", "retrieval_time_utc",
]
LOCAL = threading.local()
LOCK = threading.Lock()
LAST_REQUEST = 0.0


def now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def integer(value) -> str:
    text = str(value or "").replace(",", "").strip()
    return str(int(float(text))) if text not in {"", "--", "-"} else ""


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def atomic_gzip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f"{path.name}.{os.getpid()}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        with gzip.open(temp, "wt", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        with gzip.open(temp, "rt", encoding="utf-8-sig", newline="") as stream:
            if sum(1 for _ in csv.DictReader(stream)) != len(rows):
                raise RuntimeError("gzip verification failed")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def trading_dates() -> list[str]:
    dates = set()
    for path in sorted((P1 / "compact/official_raw_execution_ohlcv/TPEx").glob("20*.csv.gz")):
        if not (2015 <= int(path.stem.split(".")[0]) <= 2022):
            continue
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
            dates.update(row["date"] for row in csv.DictReader(stream) if START <= row["date"] <= END)
    return sorted(dates)


def session() -> requests.Session:
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update({"User-Agent": "Mozilla/5.0 RadarP1TPExHistory/1.0"})
    return LOCAL.session


def fetch(date: str) -> dict:
    global LAST_REQUEST
    checkpoint = OUT / "checkpoints/tpex_institutional" / f"{date}.csv.gz"
    meta_path = OUT / "checkpoints/tpex_institutional" / f"{date}.json"
    if checkpoint.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("status") == "accepted":
            return meta
    url = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
    params = {"date": date.replace("-", "/"), "type": "Daily", "sect": "EW", "response": "json"}
    raw, status, error = b"", 0, ""
    for attempt, delay in enumerate((0, 2, 5, 12), 1):
        if delay:
            time.sleep(delay)
        try:
            with LOCK:
                wait = 0.3 - (time.monotonic() - LAST_REQUEST)
                if wait > 0:
                    time.sleep(wait)
                LAST_REQUEST = time.monotonic()
            response = session().get(url, params=params, timeout=45)
            raw, status = response.content, response.status_code
            response.raise_for_status()
            obj = response.json()
            tables = [table for table in obj.get("tables", []) if table.get("data")]
            table = max(tables, key=lambda value: len(value.get("data") or []))
            output = []
            digest = hashlib.sha256(raw).hexdigest()
            retrieved = now()
            for row in table["data"]:
                if len(row) >= 24:
                    foreign, trust, dealer, total = row[10], row[13], row[22], row[23]
                elif len(row) >= 16:
                    foreign, trust, dealer, total = row[4], row[7], row[8], row[15]
                else:
                    continue
                output.append({
                    "date": date, "ticker": str(row[0]).strip(), "name": str(row[1]).strip(),
                    "market": "TPEx", "foreign_net": integer(foreign), "trust_net": integer(trust),
                    "dealer_net": integer(dealer), "institutional_total_net": integer(total),
                    "source_quality": "official_tpex_daily_institutional_full_market",
                    "available_at_policy": "official post-close release; eligible next trading day only",
                    "source_url": response.url, "source_hash": digest, "retrieval_time_utc": retrieved,
                })
            if not output:
                raise ValueError("official_response_no_detail_rows")
            atomic_gzip(checkpoint, output)
            meta = {"date": date, "status": "accepted", "rows": len(output), "http_status": status,
                    "response_bytes": len(raw), "source_url": response.url, "source_hash": digest,
                    "retrieval_time_utc": retrieved, "error": ""}
            atomic_json(meta_path, meta)
            return meta
        except Exception as exc:
            error = f"attempt_{attempt}_{type(exc).__name__}:{exc}"
    meta = {"date": date, "status": "failed", "rows": 0, "http_status": status,
            "response_bytes": len(raw), "source_url": url, "source_hash": hashlib.sha256(raw).hexdigest() if raw else "",
            "retrieval_time_utc": now(), "error": error}
    atomic_json(meta_path, meta)
    return meta


def run(workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dates = trading_dates()
    accepted = []
    pending = []
    for date in dates:
        meta_path = OUT / "checkpoints/tpex_institutional" / f"{date}.json"
        if meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8")).get("status") == "accepted":
            accepted.append(date)
        else:
            pending.append(date)
    completed = len(accepted)
    atomic_json(OUT / "tpex_institutional_progress.json", {"status": "running", "completed": completed, "total": len(dates), "updated_at": now()})
    (OUT / "current_step.txt").write_text("tpex_institutional_full_p1_running\n", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch, date): date for date in pending}
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 20 == 0 or completed == len(dates):
                atomic_json(OUT / "tpex_institutional_progress.json", {"status": "running", "completed": completed, "total": len(dates), "last_date": futures[future], "updated_at": now()})
    manifest = []
    for date in dates:
        manifest.append(json.loads((OUT / "checkpoints/tpex_institutional" / f"{date}.json").read_text(encoding="utf-8")))
    write_csv(OUT / "tpex_institutional_source_manifest.csv", manifest)
    all_rows = []
    for year in range(2015, 2023):
        rows = []
        for date in dates:
            if date.startswith(str(year)):
                path = OUT / "checkpoints/tpex_institutional" / f"{date}.csv.gz"
                if path.exists():
                    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
                        rows.extend(csv.DictReader(stream))
        rows = sorted({(row["date"], row["ticker"]): row for row in rows}.values(), key=lambda row: (row["date"], row["ticker"]))
        if rows:
            atomic_gzip(OUT / "compact/tpex_institutional" / f"{year}.csv.gz", rows)
            all_rows.extend(rows)
    failures = [row for row in manifest if row["status"] != "accepted"]
    write_csv(OUT / "tpex_institutional_blocked_ledger.csv", failures, list(manifest[0]))
    hashes = []
    for path in sorted((OUT / "compact/tpex_institutional").glob("*.csv.gz")):
        hashes.append({"path": str(path.relative_to(OUT)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_csv(OUT / "tpex_institutional_checksum_manifest.csv", hashes)
    atomic_json(OUT / "tpex_institutional_progress.json", {"status": "completed", "completed": len(dates), "total": len(dates), "accepted": len(dates)-len(failures), "failed": len(failures), "rows": len(all_rows), "updated_at": now()})
    (OUT / "current_step.txt").write_text("tpex_institutional_complete_audit_finalize_pending\n", encoding="utf-8")
    print(json.dumps({"dates": len(dates), "accepted": len(dates)-len(failures), "failed": len(failures), "rows": len(all_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    run(args.workers)
