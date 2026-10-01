from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

from rotation_radar.schedule_gate import TAIPEI_TZ, fetch_twse_calendar, is_trading_day


def decide(*, now: datetime, profile: str, rules_path: str | Path,
           open_dates: set[date], closed_dates: set[date]) -> tuple[bool, date | None, str]:
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))["profiles"][profile]
    hour, minute = map(int, rules.get("run_after", "15:00").split(":"))
    cutoff = time(hour, minute)
    candidates = []
    for offset in range(0, 15):
        candidate = now.date() - timedelta(days=offset)
        if offset == 0 and now.time() < cutoff:
            continue
        if is_trading_day(candidate, open_dates, closed_dates):
            candidates.append(candidate)
    if not candidates:
        return False, None, "no_completed_trading_date"
    target = max(candidates)
    if profile == "daily":
        return True, target, "latest_completed_trading_date"
    if profile != "weekly":
        raise ValueError(f"unsupported R1 profile: {profile}")
    week_end = target + timedelta(days=6 - target.weekday())
    later_open = any(is_trading_day(target + timedelta(days=step), open_dates, closed_dates)
                     for step in range(1, (week_end - target).days + 1))
    if later_open:
        return False, None, "not_last_trading_day_of_week"
    return True, target, "last_trading_day_of_week"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("daily", "weekly"), required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--now")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now).astimezone(TAIPEI_TZ) if args.now else datetime.now(TAIPEI_TZ)
    open_dates, closed_dates = fetch_twse_calendar()
    if closed_dates is None:
        result = (False, None, "calendar_unavailable")
    else:
        result = decide(now=now, profile=args.profile, rules_path=args.rules,
                        open_dates=open_dates, closed_dates=closed_dates)
    should_run, target, reason = result
    output = {"should_run": str(should_run).lower(), "target_date": target.isoformat() if target else "",
              "target_key": target.strftime("%Y%m%d") if target else "", "reason": reason}
    print(json.dumps(output))
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            for key, value in output.items():
                handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
