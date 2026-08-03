from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen


TWSE_URL = "https://www.twse.com.tw/announcement/punish"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/bulletin/disposal"
LOOKBACK_DAYS = 120


class DispositionSourceNotReady(RuntimeError):
    pass


def _roc_date(value: str) -> date:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    if len(parts) != 3:
        raise ValueError(f"Unsupported ROC date: {value!r}")
    return date(parts[0] + 1911, parts[1], parts[2])


def _period(value: str) -> tuple[date, date]:
    values = re.findall(r"\d{2,3}/\d{1,2}/\d{1,2}", value)
    if len(values) != 2:
        raise ValueError(f"Unsupported disposition period: {value!r}")
    return _roc_date(values[0]), _roc_date(values[1])


def normalize_twse(payload: dict) -> list[dict]:
    rows = []
    for item in payload.get("data", []):
        start, end = _period(str(item[6]))
        rows.append(
            {
                "market": "TWSE",
                "announce_date": _roc_date(str(item[1])),
                "ticker": str(item[2]).strip(),
                "name": str(item[3]).strip(),
                "start_date": start,
                "end_date": end,
                "detail": str(item[8]).strip(),
                "source_url": TWSE_URL,
            }
        )
    return rows


def normalize_tpex(payload: dict) -> list[dict]:
    tables = payload.get("tables", [])
    rows = []
    for item in tables[0].get("data", []) if tables else []:
        start, end = _period(str(item[5]))
        rows.append(
            {
                "market": "TPEX",
                "announce_date": _roc_date(str(item[1])),
                "ticker": str(item[2]).strip(),
                "name": re.sub(r"\(.*$", "", str(item[3])).strip(),
                "start_date": start,
                "end_date": end,
                "detail": str(item[7]).strip(),
                "source_url": TPEX_URL,
            }
        )
    return rows


def evaluate_disposition_gate(
    events: list[dict],
    *,
    ticker: str,
    signal_date: date,
    execution_date: date,
    as_of_date: date,
) -> dict:
    ticker = str(ticker).zfill(4)
    matches = [
        event
        for event in events
        if str(event["ticker"]).zfill(4) == ticker
        and event["announce_date"] <= as_of_date
        and (
            event["start_date"] <= signal_date <= event["end_date"]
            or event["start_date"] <= execution_date <= event["end_date"]
        )
    ]
    if not matches:
        return {
            "blocked": False,
            "status": "executable",
            "message": "未查得訊號日或預定執行日處於官方處置期間。",
            "events": [],
        }
    matches.sort(key=lambda event: (event["start_date"], event["end_date"]))
    return {
        "blocked": True,
        "status": "blocked_by_disposition",
        "message": "Top1處於官方處置期間：當日空手，不遞補Top2或Top3。",
        "events": [
            {
                **event,
                "announce_date": event["announce_date"].isoformat(),
                "start_date": event["start_date"].isoformat(),
                "end_date": event["end_date"].isoformat(),
            }
            for event in matches
        ],
    }


def _fetch_json(url: str, data: dict[str, str] | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    request = Request(
        url,
        data=body,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def load_disposition_gate(
    *,
    ticker: str,
    signal_date: date,
    execution_date: date,
    source_cache: Path,
    offline: bool,
) -> dict:
    cache_dir = source_cache / "disposition"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{signal_date:%Y%m%d}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    elif offline:
        raise DispositionSourceNotReady(
            f"Disposition source cache missing: {cache_path.name}"
        )
    else:
        start = signal_date - timedelta(days=LOOKBACK_DAYS)
        try:
            twse = _fetch_json(
                TWSE_URL
                + "?"
                + urllib.parse.urlencode(
                    {
                        "response": "json",
                        "startDate": start.strftime("%Y%m%d"),
                        "endDate": signal_date.strftime("%Y%m%d"),
                        "selectType": "all",
                        "sortKind": "STKNO",
                    }
                )
            )
            tpex = _fetch_json(
                TPEX_URL,
                {
                    "startDate": start.strftime("%Y/%m/%d"),
                    "endDate": signal_date.strftime("%Y/%m/%d"),
                    "type": "all",
                    "reason": "-1",
                    "measure": "-1",
                    "order": "code",
                    "response": "json",
                },
            )
        except Exception as exc:
            raise DispositionSourceNotReady(
                "Official disposition source is unavailable"
            ) from exc
        payload = {"twse": twse, "tpex": tpex}
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    events = normalize_twse(payload["twse"]) + normalize_tpex(payload["tpex"])
    return evaluate_disposition_gate(
        events,
        ticker=ticker,
        signal_date=signal_date,
        execution_date=execution_date,
        as_of_date=signal_date,
    )
