import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib import request


OUT = Path(__file__).resolve().parent
SHARDS = OUT / "tpex_full_sweep_shards"
RAW = OUT / "tpex_full_sweep_raw"
SHARDS.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

FIELDS = [
    "ticker",
    "name",
    "date",
    "period",
    "market",
    "market_cap",
    "free_float_market_cap",
    "shares_outstanding",
    "capital_stock",
    "source_price_date",
    "close_price",
    "source_date",
    "available_date",
    "source_url",
    "source_route",
    "source_type",
    "formal_exact",
    "derivation",
    "raw_source_path",
]


def append_csv(path: Path, fieldnames, rows):
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def parse_number(value):
    value = str(value or "").strip().replace(",", "")
    if value in {"", "--", "---"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_json(url: str, raw_path: Path):
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        raw_path.write_bytes(body)
        return resp.status, resp.headers.get("Content-Type", ""), json.loads(body.decode("utf-8-sig", errors="ignore"))


def parse_rows(payload, trade_date: str, url: str, raw_path: Path):
    rows = []
    for table in payload.get("tables", []):
        fields = table.get("fields") or []
        if "代號" not in fields or "收盤" not in fields or "發行股數" not in fields:
            continue
        idx = {name: i for i, name in enumerate(fields)}
        for data in table.get("data", []):
            ticker = str(data[idx["代號"]]).strip() if len(data) > idx["代號"] else ""
            if not re.fullmatch(r"\d{4}", ticker):
                continue
            close = parse_number(data[idx["收盤"]])
            shares = parse_number(data[idx["發行股數"]])
            if close is None or shares is None:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": str(data[idx["名稱"]]).strip() if "名稱" in idx and len(data) > idx["名稱"] else "",
                    "date": trade_date,
                    "period": trade_date,
                    "market": "TPEx",
                    "market_cap": f"{close * shares:.0f}",
                    "free_float_market_cap": "",
                    "shares_outstanding": f"{shares:.0f}",
                    "capital_stock": "",
                    "source_price_date": trade_date,
                    "close_price": f"{close:.4f}",
                    "source_date": trade_date,
                    "available_date": trade_date,
                    "source_url": url,
                    "source_route": "tpex_dailyQuotes/close_and_issued_shares",
                    "source_type": "shares_derived_official_daily_candidate",
                    "formal_exact": "false",
                    "derivation": "official same-day close * official same-day issued shares",
                    "raw_source_path": str(raw_path.relative_to(OUT)),
                }
            )
    return rows


def completed_dates():
    path = OUT / "tpex_market_cap_completed.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["date"] for row in csv.DictReader(f) if row.get("status") == "completed"}


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur
        cur += timedelta(days=1)


def main():
    start = date(2015, 1, 1)
    end = date.today()
    done = completed_dates()
    for d in daterange(start, end):
        ymd = d.isoformat()
        if ymd in done:
            continue
        raw_path = RAW / f"tpex_dailyQuotes_{ymd}.json"
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={ymd.replace('-', '/')}&response=json"
        try:
            status, ctype, payload = fetch_json(url, raw_path)
            rows = parse_rows(payload, ymd, url, raw_path)
            if rows:
                shard = SHARDS / f"accepted_tpex_market_cap_rows_{ymd[:7]}.csv"
                append_csv(shard, FIELDS, rows)
            append_csv(
                OUT / "tpex_market_cap_completed.csv",
                ["date", "completed_at", "status", "http_code", "content_type", "row_count", "url"],
                [{"date": ymd, "completed_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "completed", "http_code": status, "content_type": ctype, "row_count": len(rows), "url": url}],
            )
            time.sleep(0.25)
        except Exception as exc:
            append_csv(
                OUT / "tpex_market_cap_failed.csv",
                ["date", "failed_at", "status", "error", "url"],
                [{"date": ymd, "failed_at": datetime.now(timezone.utc).astimezone().isoformat(), "status": "failed", "error": repr(exc), "url": url}],
            )
            time.sleep(1.0)


if __name__ == "__main__":
    sys.exit(main())
