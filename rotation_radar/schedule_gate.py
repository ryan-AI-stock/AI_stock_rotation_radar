from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
TWSE_HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"


@dataclass(frozen=True)
class ScheduleGateDecision:
    should_run: bool
    target_date: date | None
    reason: str

    @property
    def target_key(self) -> str:
        return self.target_date.strftime("%Y%m%d") if self.target_date else ""

    @property
    def target_date_text(self) -> str:
        return self.target_date.isoformat() if self.target_date else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Determine the Taiwan trading date whose report still needs publishing.")
    parser.add_argument("--now", help="Optional Asia/Taipei timestamp for validation, e.g. 2026-06-04T15:00:00.")
    args = parser.parse_args()

    now = _parse_now(args.now)
    open_dates, closed_dates = fetch_twse_calendar()
    decision = evaluate_schedule_gate(now, open_dates, closed_dates)
    outputs = {
        "should_run": str(decision.should_run).lower(),
        "target_date": decision.target_date_text,
        "target_key": decision.target_key,
        "reason": decision.reason,
    }
    if decision.should_run:
        print(f"Target Taiwan trading date: {outputs['target_date']}")
    else:
        print(f"Schedule gate skipped: {decision.reason}")
    _write_github_outputs(outputs)


def fetch_twse_calendar() -> tuple[set[date], set[date] | None]:
    request = Request(TWSE_HOLIDAY_URL, headers={"User-Agent": "AI-stock-rotation-radar/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (json.JSONDecodeError, OSError, URLError) as exc:
        print(f"Warning: failed to load TWSE holiday schedule; skipping scheduled report: {exc}")
        return set(), None

    open_dates: set[date] = set()
    closed_dates: set[date] = set()
    for row in payload:
        trade_date = _parse_roc_date(str(row.get("Date", "")))
        if not trade_date:
            continue
        name = str(row.get("Name", ""))
        if "開始交易" in name or "最後交易" in name:
            open_dates.add(trade_date)
        else:
            closed_dates.add(trade_date)
    if not closed_dates:
        print("Warning: TWSE holiday schedule returned no closed dates; skipping scheduled report.")
        return set(), None
    return open_dates, closed_dates


def evaluate_schedule_gate(
    now: datetime,
    open_dates: set[date],
    closed_dates: set[date] | None,
) -> ScheduleGateDecision:
    if closed_dates is None:
        return ScheduleGateDecision(False, None, "calendar_unavailable")
    target = _latest_open_report_date(now, open_dates, closed_dates)
    if target is None:
        reason = "before_15_taipei" if now.hour < 15 else "not_trading_day"
        return ScheduleGateDecision(False, None, reason)
    if target == now.date():
        return ScheduleGateDecision(True, target, "trading_day_after_15_taipei")
    return ScheduleGateDecision(True, target, "retry_previous_trading_day_until_published")


def is_trading_day(value: date, open_dates: set[date], closed_dates: set[date]) -> bool:
    if value in open_dates:
        return True
    return value.weekday() < 5 and value not in closed_dates


def _latest_open_report_date(now: datetime, open_dates: set[date], closed_dates: set[date]) -> date | None:
    current = now.date()
    if now.hour >= 15 and is_trading_day(current, open_dates, closed_dates):
        return current
    for offset in range(1, 15):
        candidate = current - timedelta(days=offset)
        if is_trading_day(candidate, open_dates, closed_dates):
            return candidate
    return None


def _parse_now(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(TAIPEI_TZ)
    parsed = datetime.fromisoformat(raw)
    return parsed.replace(tzinfo=TAIPEI_TZ) if parsed.tzinfo is None else parsed.astimezone(TAIPEI_TZ)


def _parse_roc_date(raw: str) -> date | None:
    if len(raw) != 7 or not raw.isdigit():
        return None
    return date(int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7]))


def _write_github_outputs(outputs: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
