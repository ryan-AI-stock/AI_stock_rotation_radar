"""Resumable official daily market source acquisition for V4-D challengers."""

from __future__ import annotations

import hashlib
import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/formal_sources/v4d_theme_institutional_20150518_20260722"
RAW = OUT / "raw"
DEFAULT_START = date(2015, 5, 18)
DEFAULT_END = date(2026, 7, 22)


def routes(day: date) -> dict[str, str]:
    ymd = day.strftime("%Y%m%d")
    slash = day.strftime("%Y/%m/%d")
    return {
        "twse_turnover": "https://www.twse.com.tw/exchangeReport/MI_INDEX?" + urlencode({"date": ymd, "type": "ALLBUT0999", "response": "json"}),
        "tpex_turnover": "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?" + urlencode({"date": slash, "response": "json"}),
        "twse_institutional": "https://www.twse.com.tw/fund/T86?" + urlencode({"date": ymd, "selectType": "ALLBUT0999", "response": "json"}),
        "tpex_institutional": "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?" + urlencode({"date": slash, "type": "Daily", "cate": "EW", "response": "json"}),
    }


def fetch(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/1.0", "Accept": "application/json,*/*"})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    assert last_error is not None
    raise last_error


def valid_json(raw: bytes) -> bool:
    try:
        return isinstance(json.loads(raw.decode("utf-8-sig")), dict)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False


def save_progress(completed: int, total: int, current: str, errors: int, start: date, end: date, worker: str) -> None:
    payload = {
        "phase": "official_daily_source_acquisition",
        "requested_coverage": [start.isoformat(), end.isoformat()],
        "completed_route_count": completed,
        "total_route_count": total,
        "current_route": current,
        "error_count": errors,
        "resume_command": "python -X utf8 scripts/run_v4d_theme_institutional_official_daily_acquisition.py",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / f"progress_{worker}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=DEFAULT_START.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END.isoformat())
    parser.add_argument("--worker", default="all")
    args = parser.parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    RAW.mkdir(parents=True, exist_ok=True)
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    all_routes = [(day, family, url) for day in days for family, url in routes(day).items()]
    errors = 0
    completed = 0
    for day, family, url in all_routes:
        target = RAW / family / f"{day:%Y%m%d}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 20:
            completed += 1
            continue
        current = f"{family}:{day.isoformat()}"
        try:
            raw = fetch(url)
            if not valid_json(raw):
                raise ValueError("response_not_json_object")
            target.write_bytes(raw)
            meta = {"url": url, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            target.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            completed += 1
        except Exception as exc:  # checkpoint and continue; parser will classify later
            errors += 1
            error_path = target.with_suffix(".error.json")
            error_path.write_text(json.dumps({"url": url, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), encoding="utf-8")
        if (completed + errors) % 10 == 0:
            save_progress(completed, len(all_routes), current, errors, start, end, args.worker)
            print(f"{completed}/{len(all_routes)} errors={errors} current={current}", flush=True)
        time.sleep(0.15)
    save_progress(completed, len(all_routes), "download_complete", errors, start, end, args.worker)


if __name__ == "__main__":
    main()
