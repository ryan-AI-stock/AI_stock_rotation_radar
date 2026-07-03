import csv
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parent
runner_path = OUT / "run_tpex_market_cap_full_sweep.py"
spec = importlib.util.spec_from_file_location("tpex_runner", runner_path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def append_csv(path: Path, fieldnames, rows):
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def completed_dates():
    path = OUT / "tpex_market_cap_completed.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["date"] for row in csv.DictReader(f) if row.get("status") == "completed"}


def main():
    done = completed_dates()
    for raw in sorted((OUT / "raw_sources").glob("retry_tpex_dailyQuotes_*.json")):
        trade_date = raw.stem.replace("retry_tpex_dailyQuotes_", "")
        if trade_date in done:
            continue
        payload = json.loads(raw.read_text(encoding="utf-8-sig"))
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={trade_date.replace('-', '/')}&response=json"
        rows = runner.parse_rows(payload, trade_date, url, raw)
        if rows:
            shard = OUT / "tpex_full_sweep_shards" / f"accepted_tpex_market_cap_rows_{trade_date[:7]}.csv"
            append_csv(shard, runner.FIELDS, rows)
        append_csv(
            OUT / "tpex_market_cap_completed.csv",
            ["date", "completed_at", "status", "http_code", "content_type", "row_count", "url"],
            [{
                "date": trade_date,
                "completed_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "status": "completed",
                "http_code": 200,
                "content_type": "application/json; manual_retry_probe",
                "row_count": len(rows),
                "url": url,
            }],
        )


if __name__ == "__main__":
    main()
