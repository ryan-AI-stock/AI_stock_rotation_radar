from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import build_full_sweep_package as sweep


def latest_attempts():
    best = {}
    rank = {"ok": 3, "empty": 2, "blocked_current_only": 2, "failed": 1}
    for row in sweep.read_csv(sweep.BASE / "source_request_attempts.csv"):
        attempt_id = row.get("attempt_id", "")
        if not attempt_id:
            continue
        prev = best.get(attempt_id)
        if prev is None or rank.get(row.get("status", ""), 0) >= rank.get(prev.get("status", ""), 0):
            best[attempt_id] = row
    return best


def retry_one(row):
    target_date = row["target_date"]
    y, m, d = [int(x) for x in target_date.split("-")]
    dt = sweep.date(y, m, d)
    attempt_id = row["attempt_id"]
    params = {"date": sweep.iso_slash(dt), "response": "json"}
    try:
        http_code, content_type, obj, raw_len = sweep.post_json("afterTrading/chtm", params, timeout=30)
        source_date = sweep.roc_to_iso(obj.get("date", "")) or dt.isoformat()
        rows = []
        for raw in sweep.table_data(obj):
            parsed = sweep.normalize_status(raw, attempt_id, source_date)
            if parsed:
                rows.append(parsed)
        status = "ok" if rows else "empty"
        attempt = sweep.attempt_row(
            attempt_id=attempt_id,
            route_family="status_snapshot",
            action="afterTrading/chtm",
            params=params,
            target_date=dt.isoformat(),
            target_year=str(dt.year),
            status=status,
            http_code=http_code,
            content_type=content_type,
            stat=obj.get("stat", ""),
            source_date=source_date,
            row_count=sweep.table_rows(obj),
            accepted_rows=len(rows),
        )
        return dt, rows, attempt
    except Exception as exc:
        return dt, [], sweep.attempt_row(
            attempt_id=attempt_id,
            route_family="status_snapshot",
            action="afterTrading/chtm",
            params=params,
            target_date=dt.isoformat(),
            target_year=str(dt.year),
            status="failed",
            error=repr(exc),
        )


def main():
    latest = latest_attempts()
    failed = [row for row in latest.values() if row.get("route_family") == "status_snapshot" and row.get("status") == "failed"]
    (sweep.BASE / "current_step.txt").write_text(f"retrying failed status attempts: {len(failed)}", encoding="utf-8")
    existing_by_year = defaultdict(list)
    for row in sweep.load_status_rows():
        if row.get("status_date", "")[:4].isdigit():
            existing_by_year[int(row["status_date"][:4])].append(row)
    attempt_rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(retry_one, row) for row in failed]
        for idx, fut in enumerate(as_completed(futures), start=1):
            dt, rows, attempt = fut.result()
            existing_by_year[dt.year].extend(rows)
            attempt_rows.append(attempt)
            if idx % 50 == 0:
                (sweep.BASE / "current_step.txt").write_text(f"retrying failed status attempts: {idx}/{len(failed)}", encoding="utf-8")
    attempt_rows.sort(key=lambda r: r["target_date"])
    sweep.append_csv(sweep.BASE / "source_request_attempts.csv", attempt_rows, sweep.ATTEMPT_FIELDS)
    sweep.write_status_shards(existing_by_year)
    readiness = sweep.finalize_package()
    run_log = sweep.read_csv(sweep.BASE / "run_log.csv")
    run_log.append(
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "message": f"Retried {len(failed)} failed status attempts; readiness status {readiness['status']}",
        }
    )
    sweep.write_csv(sweep.BASE / "run_log.csv", run_log, ["timestamp_utc", "level", "message"])
    print(sweep.json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
