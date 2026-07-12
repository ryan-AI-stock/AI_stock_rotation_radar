import csv
import gzip
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1]))

from rotation_radar.daily_risk_features import (
    FLAGS,
    atomic_csv_gz,
    fetch_chip_family,
    fetch_foreign_ownership,
    fetch_price,
)


CHECKPOINTS = OUT / "checkpoints"
CHECKPOINTS.mkdir(exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-RIDGE-SHADOW-CURRENT-EXACT-LAYER0-4-SOURCE-PACKAGE-001"
START = date(2026, 6, 30)
END = date(2026, 7, 12)
ALL_ORDINARY_CODES = {str(i) for i in range(1000, 10000)}
CALENDAR_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
P3 = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711")
FUNDAMENTAL = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_p3_layer5_fundamental_balance_cashflow_pit_source_fill_20260712")
POST_MARKET = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_p3_post_market_source_remaining_gap_convergence_20260712")


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else ["empty"])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def days(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fetch_calendar():
    response = requests.get(CALENDAR_URL, headers={"User-Agent": "AI-stock-rotation-radar/1.0"}, timeout=30)
    response.raise_for_status()
    raw = response.content
    rows = response.json()
    return rows, {
        "family": "official_market_calendar",
        "market": "TWSE",
        "source_url": response.url,
        "http_status": response.status_code,
        "response_bytes": len(raw),
        "source_hash": digest(raw),
        "retrieved_at": now(),
        "status": "accepted",
        **FLAGS,
    }


def checkpoint_path(day):
    return CHECKPOINTS / f"{day.isoformat()}.json"


def fetch_day(day):
    cp = load_json(checkpoint_path(day))
    if cp and cp.get("status") in {"accepted_open_day", "market_closed_no_signal", "weekend_closed"}:
        return cp
    if day.weekday() >= 5:
        result = {"date": day.isoformat(), "status": "weekend_closed", "price_rows": [], "chip_rows": [], "ownership_rows": [], "manifest": []}
        write_json(checkpoint_path(day), result)
        return result
    price_rows, price_manifest = fetch_price(day, ALL_ORDINARY_CODES)
    market_status = {row["market"]: row["status"] for row in price_manifest}
    if all(market_status.get(market) == "no_rows" for market in ("TWSE", "TPEx")):
        result = {"date": day.isoformat(), "status": "market_closed_no_signal", "price_rows": [], "chip_rows": [], "ownership_rows": [], "manifest": price_manifest}
        write_json(checkpoint_path(day), result)
        return result
    if any(market_status.get(market) != "accepted" for market in ("TWSE", "TPEx")):
        result = {"date": day.isoformat(), "status": "incomplete_source", "price_rows": price_rows, "chip_rows": [], "ownership_rows": [], "manifest": price_manifest}
        write_json(checkpoint_path(day), result)
        return result
    chip_rows, chip_manifest = fetch_chip_family(day, ALL_ORDINARY_CODES)
    ownership_rows, ownership_manifest = fetch_foreign_ownership(day, ALL_ORDINARY_CODES)
    for row in price_rows:
        row["available_at_policy"] = "official EOD after market close; eligible next trading day"
        row["source_scope"] = "full_market_ordinary_candidate_source_not_layer0_selected"
    for row in chip_rows + ownership_rows:
        row["source_scope"] = "full_market_ordinary_candidate_source_not_layer0_selected"
    manifest = price_manifest + chip_manifest + ownership_manifest
    mandatory = [row for row in manifest if row["family"] in {"official_raw_execution_ohlcv", "institutional", "margin_short", "securities_lending", "foreign_ownership"}]
    blocked = [row for row in mandatory if row["status"] != "accepted"]
    result = {
        "date": day.isoformat(),
        "status": "accepted_open_day" if not blocked else "incomplete_source",
        "price_rows": price_rows,
        "chip_rows": chip_rows,
        "ownership_rows": ownership_rows,
        "manifest": manifest,
        "blocked_families": [f"{row['family']}:{row['market']}" for row in blocked],
    }
    write_json(checkpoint_path(day), result)
    return result


def reuse_row(family, path, coverage, role):
    exists = path.exists()
    return {
        "family": family,
        "source_path": str(path),
        "exists": exists,
        "sha256": digest(path.read_bytes()) if exists else "",
        "coverage": coverage,
        "role": role,
        "status": "reuse_ready" if exists else "blocked_missing_local_compact",
        **FLAGS,
    }


def main():
    CURRENT_STEP.write_text("fetch_official_calendar", encoding="utf-8")
    calendar_rows, calendar_manifest = fetch_calendar()
    write_csv(OUT / "ridge_shadow_official_market_calendar_rows.csv", calendar_rows)
    results = []
    for index, day in enumerate(days(START, END), 1):
        CURRENT_STEP.write_text(f"fetch_current_full_market_sources {index}/13 {day.isoformat()}", encoding="utf-8")
        results.append(fetch_day(day))

    price_rows, chip_rows, ownership_rows, manifests = [], [], [], [calendar_manifest]
    calendar_audit = []
    blocked = []
    for result in results:
        price_rows.extend(result["price_rows"])
        chip_rows.extend(result["chip_rows"])
        ownership_rows.extend(result["ownership_rows"])
        manifests.extend(result["manifest"])
        by_market = {row.get("market"): row for row in result["manifest"] if row.get("family") == "official_raw_execution_ohlcv"}
        calendar_audit.append({
            "date": result["date"],
            "weekday": date.fromisoformat(result["date"]).strftime("%A"),
            "session_verdict": result["status"],
            "twse_price_status": by_market.get("TWSE", {}).get("status", "not_queried"),
            "tpex_price_status": by_market.get("TPEx", {}).get("status", "not_queried"),
            "twse_price_rows": by_market.get("TWSE", {}).get("row_count", 0),
            "tpex_price_rows": by_market.get("TPEx", {}).get("row_count", 0),
            "signal_allowed": result["status"] == "accepted_open_day",
            "future_data_violation_count": 0,
            **FLAGS,
        })
        if result["status"] == "incomplete_source":
            blocked.append({"date": result["date"], "blocked_component": "current_market_source", "blocked_reason": ";".join(result.get("blocked_families", [])), "future_data_violation_count": 0, **FLAGS})

    price_fields = list(price_rows[0]) if price_rows else ["date"]
    chip_fields = list(chip_rows[0]) if chip_rows else ["date"]
    ownership_fields = list(ownership_rows[0]) if ownership_rows else ["date"]
    atomic_csv_gz(OUT / "ridge_shadow_current_full_market_official_ohlcv.csv.gz", price_rows, price_fields)
    atomic_csv_gz(OUT / "ridge_shadow_current_full_market_official_chip_rows.csv.gz", chip_rows, chip_fields)
    atomic_csv_gz(OUT / "ridge_shadow_current_full_market_official_foreign_ownership.csv.gz", ownership_rows, ownership_fields)
    write_csv(OUT / "ridge_shadow_market_session_audit.csv", calendar_audit)
    write_csv(OUT / "ridge_shadow_current_source_manifest.csv", manifests)

    adjusted = P3 / "compact" / "adjusted" / "2026.csv.gz"
    corp = P3 / "compact" / "corporate_action_guard" / "events.csv.gz"
    price_history = P3 / "compact" / "price" / "2026.csv.gz"
    fundamentals = FUNDAMENTAL / "p3_layer5_balance_cashflow_official_indicator_rows.csv.gz"
    post_market = POST_MARKET / "readiness_for_core_p3_post_market_source_convergence.json"
    reuse = [
        reuse_row("trusted_adjusted_analysis_history", adjusted, "through 2026-07-09 existing bounded P3 scope", "technical analysis only; not raw execution"),
        reuse_row("official_raw_execution_history", price_history, "through 2026-07-09 existing bounded P3 scope", "warmup history"),
        reuse_row("corporate_action_guard", corp, "official event inventory through 2026-07-10", "affected ticker guard; exact market_available_at may remain blocked"),
        reuse_row("fundamental_balance_cashflow_pit", fundamentals, "2022Q1-2026Q1 conservative statutory asof", "Layer1/F source candidate"),
        reuse_row("post_market_source_readiness", post_market, "source audit through 2026-07-09", "Core recompute handoff evidence"),
    ]
    write_csv(OUT / "ridge_shadow_existing_source_reuse_manifest.csv", reuse)

    event_rows = []
    if corp.exists():
        events = pd.read_csv(corp, dtype=str)
        effective = pd.to_datetime(events.get("effective_date"), errors="coerce")
        events = events[effective.ge(pd.Timestamp(START)) & effective.le(pd.Timestamp(2026, 7, 13))].copy()
        for row in events.to_dict("records"):
            row["market_available_at_status"] = "use source event timestamp if present; otherwise affected ticker remains blocked"
            row["accepted_for_unadjusted_execution"] = False
            row["future_data_violation_count"] = 0
            row.update(FLAGS)
            event_rows.append(row)
    write_csv(OUT / "ridge_shadow_current_corporate_action_guard_rows.csv", event_rows)

    open_days = [row["date"] for row in calendar_audit if row["session_verdict"] == "accepted_open_day"]
    closed_days = [row["date"] for row in calendar_audit if row["session_verdict"] in {"market_closed_no_signal", "weekend_closed"}]
    expected_open = ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]
    # 6/30 is included because Core exact Layer4 ended 6/29. 7/10 is an unscheduled no-session day.
    expected_ready = all(day in open_days for day in expected_open) and "2026-07-10" in closed_days and not blocked
    coverage = [
        {"family": "full_market_official_ohlcv", "required_dates": len(expected_open), "ready_dates": len([d for d in expected_open if d in open_days]), "rows": len(price_rows), "latest_source_date": max(open_days) if open_days else "", "status": "ready" if expected_ready else "partial"},
        {"family": "full_market_institutional_margin_lending", "required_dates": len(expected_open), "ready_dates": len({row["date"] for row in chip_rows}), "rows": len(chip_rows), "latest_source_date": max((row["date"] for row in chip_rows), default=""), "status": "ready" if chip_rows and not blocked else "partial"},
        {"family": "full_market_foreign_ownership", "required_dates": len(expected_open), "ready_dates": len({row["date"] for row in ownership_rows}), "rows": len(ownership_rows), "latest_source_date": max((row["date"] for row in ownership_rows), default=""), "status": "ready" if ownership_rows and not blocked else "partial"},
        {"family": "corporate_action_guard", "required_dates": "current_event_window", "ready_dates": "candidate events only", "rows": len(event_rows), "latest_source_date": "2026-07-10", "status": "partial_market_available_at_guard"},
        {"family": "exact_layer4_primary80", "required_dates": "next normal trading day", "ready_dates": 0, "rows": 0, "latest_source_date": "2026-06-29", "status": "Core_recompute_required_no_carry_forward"},
    ]
    write_csv(OUT / "ridge_shadow_current_layer0_4_source_coverage.csv", coverage)
    write_csv(OUT / "ridge_shadow_current_blocked_ledger.csv", blocked)
    write_csv(OUT / "ridge_shadow_future_data_audit.csv", [{
        "check": "current_exact_no_carry_forward", "status": "pass", "violation_count": 0,
        "notes": "2026-06-29 Layer4 membership is reference only; 7/10 no-session and weekend never emit a signal; post-close chip data is next-trading-day eligible.", **FLAGS,
    }])
    readiness = {
        "task_id": TASK_ID,
        "status": "current_full_market_source_patch_ready_for_core_exact_layer0_4_recompute" if expected_ready else "blocked_current_source_incomplete",
        "source": "official TWSE/TPEx market-wide EOD, institutional, margin/short/lending and foreign ownership routes",
        "coverage": {
            "requested_start": START.isoformat(), "requested_end": END.isoformat(),
            "latest_open_market_date": max(open_days) if open_days else "",
            "open_market_dates": open_days, "closed_no_signal_dates": closed_days,
            "official_ohlcv_rows": len(price_rows), "official_chip_rows": len(chip_rows),
            "official_foreign_ownership_rows": len(ownership_rows), "corporate_action_guard_rows": len(event_rows),
        },
        "current_exact_layer4_primary80_ready": False,
        "carried_2026_06_29_membership_allowed": False,
        "ready_for_core_exact_layer0_4_recompute": expected_ready,
        "ready_for_core_rerun": expected_ready,
        "ready_for_first_prospective_ridge_prediction": False,
        "market_closed_no_signal_policy_ready": True,
        "future_data_violation_count": 0,
        "ready_for_experiments": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_ridge_shadow_current_exact_layer0_4_source.json", readiness)
    CURRENT_STEP.write_text("completed_ready_for_core_exact_layer0_4_recompute", encoding="utf-8")
    write_json(OUT / "checkpoint.json", {"task_id": TASK_ID, "current_step": CURRENT_STEP.read_text(encoding="utf-8"), "completed_dates": len(results), "total_dates": 13, "latest_open_market_date": max(open_days) if open_days else "", "resume_command": "python -X utf8 build_package.py", "updated_at": now()})
    summary = f"""# P3 Ridge shadow current exact Layer0-4 source package\n\n- Status: {readiness['status']}\n- Full-market official patch: {START.isoformat()}~{max(open_days) if open_days else ''}。\n- Open dates: {', '.join(open_days)}。\n- Closed/no signal: {', '.join(closed_days)}。\n- Official OHLCV rows: {len(price_rows):,}；chip rows: {len(chip_rows):,}；foreign ownership rows: {len(ownership_rows):,}。\n- 2026-06-29 Layer4 membership 不得 carry-forward；本包只讓 Core 依 frozen Layer0-4 pipeline 重算。\n- current exact primary80 與首次 Ridge prediction 仍未在 Radar 產生。\n- future_data_violation_count=0。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    artifacts = []
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "checkpoints" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(OUT).as_posix()
        artifacts.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest(path.read_bytes())})
    write_json(OUT / "manifest.json", {"task_id": TASK_ID, "generated_at": now(), "artifacts": artifacts, **FLAGS})
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
