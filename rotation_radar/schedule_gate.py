from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
TWSE_HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
TWSE_NEWS_URL = "https://www.twse.com.tw/rwd/zh/news/newsList?response=json"


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


@dataclass(frozen=True)
class ScheduleGateRules:
    run_after: time = time(15, 0)
    retry_until_success: bool = False
    emergency_confirm_after: time = time(18, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Determine the Taiwan trading date whose report still needs publishing.")
    parser.add_argument("--now", help="Optional Asia/Taipei timestamp for validation, e.g. 2026-06-04T15:00:00.")
    parser.add_argument("--run-after", help="Explicit task-specific cutoff; shared PDF schedule is unchanged.")
    parser.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Optional AI_stock_schedule_rules schedule_rules.json path. Defaults to SCHEDULE_RULES_PATH.",
    )
    parser.add_argument(
        "--recover-delayed-schedule",
        action="store_true",
        help="Before the daily cutoff, publish the latest prior trading day. Use only for delayed scheduled jobs.",
    )
    args = parser.parse_args()

    now = _parse_now(args.now)
    rules = load_schedule_rules(args.rules)
    if args.run_after:
        rules = ScheduleGateRules(
            run_after=_parse_hhmm(args.run_after),
            retry_until_success=rules.retry_until_success,
            emergency_confirm_after=rules.emergency_confirm_after,
        )
    if args.recover_delayed_schedule and now.time() < rules.run_after:
        rules = ScheduleGateRules(
            run_after=rules.run_after,
            retry_until_success=True,
            emergency_confirm_after=rules.emergency_confirm_after,
        )
    open_dates, closed_dates = fetch_twse_calendar()
    session_reason = ""
    if closed_dates is not None:
        closed_dates, session_reason = resolve_recent_market_calendar(now, open_dates, closed_dates, rules)
    if session_reason in {"official_session_data_pending", "official_data_delayed"}:
        decision = ScheduleGateDecision(False, None, session_reason)
    else:
        decision = evaluate_schedule_gate(now, open_dates, closed_dates, rules=rules)
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


def load_schedule_rules(path: Path | None = None) -> ScheduleGateRules:
    raw_path = path or _schedule_rules_path_from_env()
    if raw_path is None:
        return ScheduleGateRules()
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        daily = payload["profiles"]["daily"]
        run_after = _parse_hhmm(str(daily.get("run_after", "15:00")))
        retry_until_success = bool(daily.get("retry_until_success", False))
        emergency_confirm_after = _parse_hhmm(str(daily.get("emergency_confirm_after", "18:00")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"Warning: failed to load shared schedule rules from {raw_path}; using defaults: {exc}")
        return ScheduleGateRules()
    print(f"Loaded shared daily schedule rules from {raw_path}")
    return ScheduleGateRules(
        run_after=run_after,
        retry_until_success=retry_until_success,
        emergency_confirm_after=emergency_confirm_after,
    )


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


def fetch_official_market_session_state(trade_date: date) -> str:
    """Return open/closed/unknown using both official after-trading APIs."""
    ymd = trade_date.strftime("%Y%m%d")
    slash_date = trade_date.strftime("%Y/%m/%d")
    urls = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={ymd}&type=ALLBUT0999&response=json",
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
        f"?date={slash_date}&type=EW&response=json",
    )
    row_counts = []
    try:
        for url in urls:
            request = Request(url, headers={"User-Agent": "AI-stock-rotation-radar/1.0"})
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            row_counts.append(sum(len(table.get("data") or []) for table in payload.get("tables") or []))
    except (json.JSONDecodeError, OSError, TypeError, URLError):
        return "unknown"
    if any(count > 0 for count in row_counts):
        return "open"
    return "closed" if len(row_counts) == 2 else "unknown"


def fetch_official_emergency_closure(trade_date: date) -> bool | None:
    """Confirm an unscheduled closure from an exact-date TWSE news title."""
    request = Request(TWSE_NEWS_URL, headers={"User-Agent": "AI-stock-rotation-radar/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (json.JSONDecodeError, OSError, TypeError, URLError):
        return None
    roc_date = f"{trade_date.year - 1911}年{trade_date.month}月{trade_date.day}日"
    titles = [str(row[1]) for row in payload.get("data") or [] if len(row) > 1]
    return any(roc_date in title and "休市" in title for title in titles)


def add_recent_emergency_market_closure(
    now: datetime,
    open_dates: set[date],
    closed_dates: set[date],
    rules: ScheduleGateRules,
) -> set[date]:
    """Add an unscheduled closure only when both official markets confirm no session."""
    updated, _ = resolve_recent_market_calendar(now, open_dates, closed_dates, rules)
    return updated


def resolve_recent_market_calendar(
    now: datetime,
    open_dates: set[date],
    closed_dates: set[date],
    rules: ScheduleGateRules,
) -> tuple[set[date], str]:
    """Classify recent unscheduled closures without treating fresh data delay as closure.

    The holiday feed is not retroactively complete for every emergency closure.  A
    past weekday with no rows on either exchange can therefore be marked closed
    once a later official session is confirmed open.  The current candidate keeps
    the stricter notice/deadline behaviour so delayed same-day data is never
    silently converted into a holiday.
    """
    updated = set(closed_dates)
    candidate = now.date()
    if candidate.weekday() >= 5:
        candidate -= timedelta(days=candidate.weekday() - 4)
    elif now.time() < rules.run_after:
        candidate -= timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
    candidate_reason = "calendar_known"
    candidate_state = "known" if candidate in open_dates or candidate in updated else "unknown"
    if candidate_state == "unknown":
        closure_notice = fetch_official_emergency_closure(candidate)
        if closure_notice is True:
            updated.add(candidate)
            candidate_state = "closed"
            candidate_reason = "emergency_market_closed"
            print(f"Detected official TWSE emergency closure notice: {candidate.isoformat()}")
        else:
            candidate_state = fetch_official_market_session_state(candidate)
            if candidate_state == "open":
                candidate_reason = "official_session_open"
            elif candidate_state == "closed" and candidate == now.date() and now.time() < rules.emergency_confirm_after:
                candidate_reason = "official_session_data_pending"
            elif candidate_state == "closed":
                candidate_reason = "official_data_delayed"
            else:
                candidate_reason = "official_session_unknown"

    # Reconcile only a short recent window.  A later confirmed-open session is
    # required before zero-row historical data may be interpreted as a closure.
    states: dict[date, str] = {}
    if candidate_state == "open":
        states[candidate] = "open"
    start = candidate - timedelta(days=10)
    for offset in range((candidate - start).days + 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5 or day in open_dates or day in updated or day == candidate:
            continue
        states[day] = fetch_official_market_session_state(day)

    open_sessions = sorted(day for day, state in states.items() if state == "open")
    for day, state in sorted(states.items()):
        if state == "closed" and any(later > day for later in open_sessions):
            updated.add(day)
            print(
                "Detected historical emergency closure from bracketed official sessions: "
                f"{day.isoformat()}"
            )

    if candidate_reason == "official_session_data_pending":
        print(f"Official session data not ready yet: {candidate.isoformat()}")
    elif candidate_reason == "official_data_delayed" and candidate not in updated:
        print(f"Official session data remains absent without a closure notice: {candidate.isoformat()}")
    return updated, candidate_reason


def evaluate_schedule_gate(
    now: datetime,
    open_dates: set[date],
    closed_dates: set[date] | None,
    *,
    rules: ScheduleGateRules | None = None,
) -> ScheduleGateDecision:
    rules = rules or ScheduleGateRules()
    if closed_dates is None:
        return ScheduleGateDecision(False, None, "calendar_unavailable")
    target = _latest_open_report_date(now, open_dates, closed_dates, rules)
    if target is None:
        reason = "before_run_after_taipei" if now.time() < rules.run_after else "not_trading_day"
        return ScheduleGateDecision(False, None, reason)
    if target == now.date():
        return ScheduleGateDecision(True, target, "trading_day_after_run_after_taipei")
    return ScheduleGateDecision(True, target, "retry_previous_trading_day_until_published")


def is_trading_day(value: date, open_dates: set[date], closed_dates: set[date]) -> bool:
    if value in open_dates:
        return True
    return value.weekday() < 5 and value not in closed_dates


def _latest_open_report_date(
    now: datetime,
    open_dates: set[date],
    closed_dates: set[date],
    rules: ScheduleGateRules,
) -> date | None:
    current = now.date()
    if now.time() >= rules.run_after and is_trading_day(current, open_dates, closed_dates):
        return current
    if not rules.retry_until_success:
        return None
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


def _parse_hhmm(raw: str) -> time:
    hour, minute = raw.split(":", 1)
    return time(int(hour), int(minute))


def _schedule_rules_path_from_env() -> Path | None:
    raw_path = os.environ.get("SCHEDULE_RULES_PATH", "").strip()
    return Path(raw_path) if raw_path else None


def _write_github_outputs(outputs: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
