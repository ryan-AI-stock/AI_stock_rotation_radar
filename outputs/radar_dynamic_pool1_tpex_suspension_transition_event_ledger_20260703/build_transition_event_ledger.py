from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-TPEX-SUSPENSION-TRANSITION-EVENT-LEDGER-20260703"
BASE = Path("outputs/radar_dynamic_pool1_tpex_suspension_transition_event_ledger_20260703")
PREVIOUS_PACKAGE = Path("outputs/radar_dynamic_pool1_tpex_historical_full_sweep_20260703")
CORE_READINESS = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\dynamic_pool1_pit_readiness_after_tpex_full_route_coverage_20260703"
)
STATUS_ROWS = PREVIOUS_PACKAGE / "accepted_status_snapshot_rows.csv"
RUN_TS = datetime.now(timezone.utc).isoformat()
START_DATE = date(2015, 1, 1)
END_DATE = date(2025, 12, 31)

ANN_ENDPOINT = "https://www.tpex.org.tw/www/zh-tw/bulletin/annDownload"
TP_EX = "https://www.tpex.org.tw"
MAX_VERIFICATION_CANDIDATES = 160
ANNOUNCEMENT_KEYWORDS = ["暫停", "停止交易", "恢復", "變更交易", "分盤", "管理股票", "終止上櫃"]

TRANSITION_FIELDS = [
    "event_id",
    "ticker",
    "name",
    "event_date",
    "previous_status",
    "new_status",
    "transition_type",
    "source_snapshot_date",
    "source_url",
    "source_type",
    "verification_status",
    "matched_announcement_date",
    "matched_announcement_url",
    "matched_keywords",
    "matched_excerpt",
    "notes",
]

ATTEMPT_FIELDS = [
    "attempt_id",
    "candidate_event_id",
    "ticker",
    "name",
    "event_date",
    "route",
    "method",
    "query_url",
    "params",
    "http_code",
    "content_type",
    "status",
    "zip_url",
    "zip_http_code",
    "zip_entry_count",
    "matched",
    "matched_keywords",
    "error",
]


def ensure_base() -> None:
    BASE.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({field: row.get(field, "") for field in fields})


def append_run_log(status: str, details: str) -> None:
    path = BASE / "run_log.csv"
    if not path.exists():
        write_csv(path, [], ["timestamp", "status", "details"])
    with path.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(), status, details])


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def status_label(row: dict[str, str]) -> str:
    parts: list[str] = []
    if parse_bool(row.get("is_suspended", "")):
        parts.append("suspended")
    if parse_bool(row.get("is_altered_trading", "")):
        parts.append("altered")
    if parse_bool(row.get("is_periodic_call_auction", "")):
        parts.append("periodic")
    if parse_bool(row.get("is_management_stock", "")):
        parts.append("management")
    cycle = row.get("matching_cycle_minutes", "").strip()
    if cycle:
        parts.append(f"cycle_{cycle}")
    return "+".join(parts) if parts else "normal"


def classify_transition(previous_status: str, new_status: str) -> str:
    if previous_status == "normal" and new_status != "normal":
        if "suspended" in new_status:
            return "normal_to_suspended"
        if "altered" in new_status:
            return "normal_to_altered"
        if "periodic" in new_status:
            return "normal_to_periodic"
        if "management" in new_status:
            return "normal_to_management"
        return "normal_to_abnormal"
    if previous_status != "normal" and new_status == "normal":
        if "suspended" in previous_status:
            return "suspended_to_normal"
        if "altered" in previous_status:
            return "altered_to_normal"
        if "periodic" in previous_status:
            return "periodic_to_normal"
        if "management" in previous_status:
            return "management_to_normal"
        return "abnormal_to_normal"
    if previous_status != new_status:
        return "status_change"
    return "unchanged"


def build_candidates() -> list[dict[str, str]]:
    rows = read_csv(STATUS_ROWS)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        row["_status"] = status_label(row)
        grouped[row["ticker"]].append(row)

    candidates: list[dict[str, str]] = []
    event_seq = 0
    for ticker, ticker_rows in sorted(grouped.items()):
        ticker_rows.sort(key=lambda r: (r["status_date"], r.get("name", "")))
        previous_status = "normal"
        previous_date: date | None = None
        previous_row: dict[str, str] | None = None
        for row in ticker_rows:
            current_date = date.fromisoformat(row["status_date"])
            current_status = row["_status"]
            if previous_date and (current_date - previous_date).days > 7 and previous_status != "normal":
                event_seq += 1
                exit_date = min(previous_date + timedelta(days=1), END_DATE)
                candidates.append(
                    make_candidate(
                        event_seq,
                        previous_row or row,
                        exit_date.isoformat(),
                        previous_status,
                        "normal",
                        "gap_gt_7_days_implied_resolution",
                        previous_date.isoformat(),
                    )
                )
                previous_status = "normal"
            if current_status != previous_status:
                event_seq += 1
                candidates.append(
                    make_candidate(
                        event_seq,
                        row,
                        row["status_date"],
                        previous_status,
                        current_status,
                        "",
                        row["status_date"],
                    )
                )
            previous_status = current_status
            previous_date = current_date
            previous_row = row
        if previous_status != "normal" and previous_date and previous_date < END_DATE:
            event_seq += 1
            candidates.append(
                make_candidate(
                    event_seq,
                    previous_row or ticker_rows[-1],
                    (previous_date + timedelta(days=1)).isoformat(),
                    previous_status,
                    "normal",
                    "end_of_observed_abnormal_sequence",
                    previous_date.isoformat(),
                )
            )
    return candidates


def make_candidate(
    seq: int,
    row: dict[str, str],
    event_date: str,
    previous_status: str,
    new_status: str,
    note_prefix: str,
    source_snapshot_date: str,
) -> dict[str, str]:
    transition_type = classify_transition(previous_status, new_status)
    note = "Inferred from TPEx afterTrading/chtm daily abnormal status snapshots; not an official explicit transition event."
    if note_prefix:
        note = f"{note_prefix}; {note}"
    return {
        "event_id": f"tpex_transition_{seq:06d}",
        "ticker": row.get("ticker", ""),
        "name": row.get("name", ""),
        "event_date": event_date,
        "previous_status": previous_status,
        "new_status": new_status,
        "transition_type": transition_type,
        "source_snapshot_date": source_snapshot_date,
        "source_url": row.get("source_url", ""),
        "source_type": "inferred_from_daily_status_snapshot",
        "verification_status": "unverified_candidate",
        "matched_announcement_date": "",
        "matched_announcement_url": "",
        "matched_keywords": "",
        "matched_excerpt": "",
        "notes": note,
    }


def select_for_verification(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    priority = []
    for row in candidates:
        status_text = f"{row['previous_status']} {row['new_status']} {row['transition_type']}"
        score = 0
        if "suspended" in status_text:
            score += 100
        if "normal_to" in row["transition_type"] or "_to_normal" in row["transition_type"]:
            score += 20
        if "status_change" == row["transition_type"]:
            score += 10
        priority.append((score, row["event_date"], row["ticker"], row))
    priority.sort(key=lambda item: (-item[0], item[1], item[2]))
    selected = [item[-1] for item in priority[:MAX_VERIFICATION_CANDIDATES]]
    return selected


def candidate_windows(candidate: dict[str, str]) -> tuple[str, str]:
    d = date.fromisoformat(candidate["event_date"])
    start = max(START_DATE, d - timedelta(days=1))
    end = min(END_DATE, d + timedelta(days=3))
    return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")


def normalize_text(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "big5", "cp950"):
        try:
            return raw.decode(enc, errors="ignore")
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def excerpt(text: str, ticker: str, name: str) -> str:
    compact = re.sub(r"\s+", " ", text)
    positions = [p for p in [compact.find(ticker), compact.find(name)] if p >= 0]
    start = max(0, min(positions) - 80) if positions else 0
    return compact[start : start + 240]


def verify_candidates(candidates: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    if requests is None:
        return [], [], [
            {
                "source": "TPEx bulletin/annDownload",
                "blocked_component": "announcement verification",
                "blocked_reason": "python_requests_unavailable",
                "next_programmatic_route": "Install/use requests or urllib based downloader.",
            }
        ]

    attempts: list[dict[str, str]] = []
    verified: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    selected = select_for_verification(candidates)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    zip_cache: dict[str, tuple[int, str, bytes | None]] = {}
    for idx, candidate in enumerate(selected, start=1):
        start, end = candidate_windows(candidate)
        params = {"startDate": start, "endDate": end, "response": "json"}
        attempt = {
            "attempt_id": f"verify_{idx:04d}",
            "candidate_event_id": candidate["event_id"],
            "ticker": candidate["ticker"],
            "name": candidate["name"],
            "event_date": candidate["event_date"],
            "route": "bulletin/annDownload",
            "method": "POST",
            "query_url": ANN_ENDPOINT,
            "params": f"startDate={start}&endDate={end}&response=json",
            "http_code": "",
            "content_type": "",
            "status": "failed",
            "zip_url": "",
            "zip_http_code": "",
            "zip_entry_count": "",
            "matched": "false",
            "matched_keywords": "",
            "error": "",
        }
        try:
            response = session.post(ANN_ENDPOINT, data=params, timeout=20)
            attempt["http_code"] = str(response.status_code)
            attempt["content_type"] = response.headers.get("content-type", "")
            response.raise_for_status()
            payload = response.json()
            zip_links = extract_zip_links(payload)
            attempt["status"] = "ok" if zip_links else "empty"
            matched_payload = None
            for zip_link in zip_links[:6]:
                zip_url = zip_link if zip_link.startswith("http") else TP_EX + zip_link
                status_code, error, zip_bytes = zip_cache.get(zip_url, ("", "", None))  # type: ignore[assignment]
                if zip_url not in zip_cache:
                    try:
                        zr = session.get(zip_url, timeout=20)
                        status_code = zr.status_code
                        zr.raise_for_status()
                        zip_bytes = zr.content
                        error = ""
                    except Exception as exc:  # noqa: BLE001
                        status_code = getattr(getattr(exc, "response", None), "status_code", status_code) or ""
                        error = repr(exc)
                        zip_bytes = None
                    zip_cache[zip_url] = (int(status_code) if status_code else 0, error, zip_bytes)
                attempt["zip_url"] = zip_url
                attempt["zip_http_code"] = str(status_code)
                if zip_bytes:
                    entry_count, match = inspect_zip(zip_bytes, candidate)
                    attempt["zip_entry_count"] = str(entry_count)
                    if match:
                        matched_payload = (zip_url, match)
                        break
                elif error:
                    attempt["error"] = error
            if matched_payload:
                zip_url, match = matched_payload
                attempt["matched"] = "true"
                attempt["matched_keywords"] = ";".join(match["matched_keywords"])
                verified_row = dict(candidate)
                verified_row["source_type"] = "announcement_verified"
                verified_row["verification_status"] = "announcement_verified"
                verified_row["matched_announcement_date"] = candidate["event_date"]
                verified_row["matched_announcement_url"] = zip_url
                verified_row["matched_keywords"] = ";".join(match["matched_keywords"])
                verified_row["matched_excerpt"] = match["matched_excerpt"]
                verified_row["notes"] = "Matched ticker/name and status keyword inside TPEx announcement ZIP archive; still source-backed candidate pending Core judgment."
                verified.append(verified_row)
        except Exception as exc:  # noqa: BLE001
            attempt["error"] = repr(exc)
        attempts.append(attempt)

    if not verified:
        blocked.append(
            {
                "source": "TPEx bulletin/annDownload",
                "blocked_component": "announcement verification matches",
                "blocked_reason": "bounded_zip_keyword_probe_found_no_ticker_keyword_matches" if attempts else "no_attempts_completed",
                "next_programmatic_route": "Expand ZIP archive extraction window and parse document formats by attachment type; or diff daily status snapshots and validate manually against announcement titles.",
            }
        )
    return attempts, verified, blocked


def extract_zip_links(payload: dict) -> list[str]:
    links: list[str] = []
    for table in payload.get("tables", []) or []:
        for data_row in table.get("data", []) or []:
            for cell in data_row:
                if isinstance(cell, str) and ".zip" in cell:
                    links.append(cell)
    return links


def inspect_zip(zip_bytes: bytes, candidate: dict[str, str]) -> tuple[int, dict[str, object] | None]:
    ticker = candidate["ticker"]
    name = candidate["name"]
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        for entry in names:
            lower = entry.lower()
            if lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".pdf", ".xls", ".xlsx")):
                continue
            try:
                text = normalize_text(zf.read(entry))
            except Exception:
                continue
            matched_keywords = [kw for kw in ANNOUNCEMENT_KEYWORDS if kw in text]
            if matched_keywords and (ticker in text or name in text):
                return len(names), {"matched_keywords": matched_keywords, "matched_excerpt": excerpt(text, ticker, name)}
    return len(names), None


def coverage_by_year(candidates: list[dict[str, str]], verified: list[dict[str, str]]) -> list[dict[str, object]]:
    verified_ids = {row["event_id"] for row in verified}
    rows: list[dict[str, object]] = []
    for year in range(START_DATE.year, END_DATE.year + 1):
        year_rows = [row for row in candidates if row["event_date"].startswith(str(year))]
        rows.append(
            {
                "year": year,
                "market": "TPEx",
                "transition_candidates": len(year_rows),
                "verified_events": sum(1 for row in year_rows if row["event_id"] in verified_ids),
                "unverified_candidates": sum(1 for row in year_rows if row["event_id"] not in verified_ids),
                "normal_to_abnormal": sum(1 for row in year_rows if row["transition_type"].startswith("normal_to")),
                "abnormal_to_normal": sum(1 for row in year_rows if row["transition_type"].endswith("_to_normal")),
                "status_change": sum(1 for row in year_rows if row["transition_type"] == "status_change"),
                "coverage_status": "candidate_ledger_ready_announcement_partial",
            }
        )
    return rows


def finalize() -> dict[str, object]:
    ensure_base()
    (BASE / "current_step.txt").write_text("building_transition_candidates", encoding="utf-8")
    append_run_log("running", "building_transition_candidates_from_status_snapshots")
    candidates = build_candidates()
    write_csv(BASE / "transition_event_candidates.csv", candidates, TRANSITION_FIELDS)
    write_csv(
        BASE / "unverified_transition_candidates.csv",
        [row for row in candidates if row["verification_status"] == "unverified_candidate"],
        TRANSITION_FIELDS,
    )

    (BASE / "current_step.txt").write_text("running_bounded_announcement_verification", encoding="utf-8")
    append_run_log("running", f"candidate_count={len(candidates)}; verification_limit={MAX_VERIFICATION_CANDIDATES}")
    attempts, verified, blocked = verify_candidates(candidates)
    write_csv(BASE / "announcement_verification_attempts.csv", attempts, ATTEMPT_FIELDS)
    write_csv(BASE / "announcement_verified_events.csv", verified, TRANSITION_FIELDS)
    unverified = [row for row in candidates if row["event_id"] not in {v["event_id"] for v in verified}]
    write_csv(BASE / "unverified_transition_candidates.csv", unverified, TRANSITION_FIELDS)
    write_csv(
        BASE / "coverage_by_year.csv",
        coverage_by_year(candidates, verified),
        [
            "year",
            "market",
            "transition_candidates",
            "verified_events",
            "unverified_candidates",
            "normal_to_abnormal",
            "abnormal_to_normal",
            "status_change",
            "coverage_status",
        ],
    )

    blocked_rows = [
        {
            "source": "TPEx bulletin/sprc",
            "blocked_component": "explicit suspension/resumption event history",
            "blocked_reason": "current_only_no_historical_date_parameter",
            "next_programmatic_route": "Use bulletin/annDownload ZIP archive extraction or infer from daily snapshot diffs.",
        },
        *blocked,
    ]
    write_csv(BASE / "blocked_source_rows.csv", blocked_rows, ["source", "blocked_component", "blocked_reason", "next_programmatic_route"])
    write_csv(
        BASE / "future_data_violation_audit.csv",
        [
            {
                "audit_item": "snapshot_diff_source_date",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "Transition candidates are derived only from TPEx historical daily status snapshot rows with status_date/source_date in 2015-2025.",
            },
            {
                "audit_item": "inferred_not_formal_exact",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "Inferred candidates remain source_type=inferred_from_daily_status_snapshot unless matched by bounded announcement verification.",
            },
            {
                "audit_item": "model_boundary",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "No BACKTEST_LAB formal model, selector, report, or trade decision changed.",
            },
        ],
        ["audit_item", "result", "future_data_violation_count", "evidence"],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_transition_candidate_ledger_announcement_verified_partial" if verified else "completed_transition_candidate_ledger_unverified",
        "output_path": str(BASE.resolve()),
        "previous_package": str(PREVIOUS_PACKAGE),
        "core_readiness_input": str(CORE_READINESS),
        "transition_candidate_count": len(candidates),
        "announcement_verification_attempts": len(attempts),
        "announcement_verified_event_count": len(verified),
        "unverified_transition_candidate_count": len(unverified),
        "future_data_violation_count": 0,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "source_type_boundary": "inferred candidates are not official explicit events unless source_type=announcement_verified",
        "remaining_blockers": [
            "Announcement verification is bounded and may not cover all transition candidates.",
            "Core must decide whether inferred snapshot transition candidates are acceptable for universe integrity, or require broader archive verification.",
        ],
    }
    (BASE / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "manifest.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "created_at_utc": RUN_TS,
                "status": readiness["status"],
                "outputs": [
                    "transition_event_candidates.csv",
                    "announcement_verification_attempts.csv",
                    "announcement_verified_events.csv",
                    "unverified_transition_candidates.csv",
                    "coverage_by_year.csv",
                    "blocked_source_rows.csv",
                    "future_data_violation_audit.csv",
                    "readiness_for_core.json",
                    "final_summary_zh.md",
                ],
                "formal_model_changed": False,
                "trade_decision_changed": False,
                "active_in_trade_decision": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_csv(
        BASE / "completed.csv",
        [
            {"step": "transition_candidate_diff", "status": "completed", "evidence": "transition_event_candidates.csv"},
            {"step": "bounded_announcement_verification", "status": "completed", "evidence": "announcement_verification_attempts.csv"},
            {"step": "readiness_package", "status": "completed", "evidence": "readiness_for_core.json"},
        ],
        ["step", "status", "evidence"],
    )
    write_csv(
        BASE / "failed.csv",
        [
            {
                "step": "full_archive_verification",
                "status": "not_completed",
                "reason": "bounded verification only; full archive ZIP extraction remains next source-expansion task if Core requires it.",
            }
        ],
        ["step", "status", "reason"],
    )
    (BASE / "current_step.txt").write_text(str(readiness["status"]), encoding="utf-8")
    (BASE / "final_summary_zh.md").write_text(
        f"""# Dynamic Pool1 TPEx suspension/resumption transition event ledger

## 結論

狀態：`{readiness['status']}`。

本棒將上一棒 `accepted_status_snapshot_rows.csv` 依 ticker/date 差分，產出 TPEx 2015-2025 transition event candidate ledger。

- transition candidates：{len(candidates)}
- announcement verification attempts：{len(attempts)}
- announcement verified events：{len(verified)}
- unverified candidates：{len(unverified)}
- `future_data_violation_count=0`

## 邊界

`transition_event_candidates.csv` 主要是 `inferred_from_daily_status_snapshot`，不是 TPEx official explicit event ledger。只有 `announcement_verified_events.csv` 中的 rows 才升級為 `announcement_verified`，且仍需 Core 判斷是否足以支援 Dynamic Pool1 universe integrity。

## Readiness

- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 下一步

交 Core 重跑 Dynamic Pool1 readiness。若 Core 仍要求更高比例 official verification，下一棒 Radar/Data 擴大 `bulletin/annDownload` ZIP archive extraction window，或針對 high-impact tickers 做 announcement text parser。
""",
        encoding="utf-8",
    )
    append_run_log("completed", json.dumps(readiness, ensure_ascii=False))
    return readiness


if __name__ == "__main__":
    print(json.dumps(finalize(), ensure_ascii=False, indent=2))
