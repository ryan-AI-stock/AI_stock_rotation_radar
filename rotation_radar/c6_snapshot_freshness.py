"""Reject silent re-publication of an old C6 snapshot on scheduled runs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")


def expected_latest_weekday(now: datetime) -> str:
    local = now.astimezone(TAIPEI)
    day = local.date()
    if local.hour < 16:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def validate_payload_freshness(payload: dict, now: datetime) -> None:
    actual = str(payload.get("ranking_snapshot_as_of") or payload.get("snapshot_as_of") or "")[:10]
    expected = expected_latest_weekday(now)
    if actual < expected:
        raise RuntimeError(
            f"C6 snapshot is stale: latest ranking date is {actual or 'missing'}, expected at least {expected}. "
            "The workflow must materialize the daily C6 ranking before publishing."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    validate_payload_freshness(payload, datetime.now(tz=TAIPEI))


if __name__ == "__main__":
    main()
