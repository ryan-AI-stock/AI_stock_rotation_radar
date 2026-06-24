from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELDS = [
    "source_id",
    "source_url",
    "source_title",
    "source_date",
    "source_type",
    "exact_or_proxy",
    "download_status",
    "http_status",
    "content_type",
    "bytes",
    "local_path",
    "parse_status",
    "future_data_violation_check",
    "license_or_usage_note",
    "notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Pool2 TW50 exact PIT official source package from Taiwan Index notices."
    )
    parser.add_argument("--input-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    readiness = build_package(
        input_manifest=Path(args.input_manifest),
        output_dir=Path(args.output_dir),
        sleep_seconds=args.sleep_seconds,
        limit=args.limit or None,
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


def build_package(
    *,
    input_manifest: Path,
    output_dir: Path,
    sleep_seconds: float = 1.5,
    limit: int | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "technical_notices_pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".gitignore").write_text("technical_notices_pdf/\n*.pdf\n*.bin\n", encoding="utf-8")

    input_rows = _read_rows(input_manifest)
    if limit is not None:
        input_rows = input_rows[:limit]

    audit_rows: list[dict[str, str]] = []
    for index, row in enumerate(input_rows, start=1):
        source_id = row.get("source_id") or row.get("file", "").replace(".pdf", "")
        filename = row.get("filename") or f"{source_id}.pdf"
        local_path = pdf_dir / filename
        current = _base_row(row, source_id, local_path)
        if local_path.exists() and local_path.stat().st_size > 0:
            current.update(
                {
                    "download_status": "downloaded_cached",
                    "http_status": "",
                    "content_type": "application/pdf",
                    "bytes": str(local_path.stat().st_size),
                    "parse_status": "ready_for_core_parser",
                }
            )
        else:
            current.update(_download_pdf(row.get("source_url", ""), local_path))
        audit_rows.append(current)
        _write_rows(output_dir / "source_audit.csv", FIELDS, audit_rows)
        (output_dir / "current_step.txt").write_text(
            f"{_now_iso()} processed {index}/{len(input_rows)} {source_id} {current['download_status']}\n",
            encoding="utf-8",
        )
        if sleep_seconds and index < len(input_rows):
            time.sleep(sleep_seconds)

    accepted = [row for row in audit_rows if row["download_status"] in {"downloaded", "downloaded_cached"}]
    failed = [row for row in audit_rows if row not in accepted]
    blocked_rows = _blocked_rows(accepted, failed)

    _write_rows(output_dir / "accepted_sources.csv", FIELDS, accepted)
    _write_rows(output_dir / "failed.csv", FIELDS, failed)
    _write_rows(output_dir / "blocked_sources.csv", ["blocker", "status", "details", "next_step"], blocked_rows)

    readiness = _readiness(output_dir, audit_rows, accepted, failed, blocked_rows)
    _write_json(output_dir / "readiness_manifest.json", readiness)
    _write_summary(output_dir / "final_summary_zh.md", readiness, accepted, failed)
    return readiness


def _base_row(row: dict[str, str], source_id: str, local_path: Path) -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_url": row.get("source_url", ""),
        "source_title": row.get("source_title", ""),
        "source_date": row.get("source_date", ""),
        "source_type": "official_technical_notice",
        "exact_or_proxy": "exact_candidate",
        "download_status": "pending",
        "http_status": "",
        "content_type": "",
        "bytes": "0",
        "local_path": str(local_path),
        "parse_status": "parse_pending",
        "future_data_violation_check": "pass_source_date_only",
        "license_or_usage_note": "Official Taiwan Index public technical notice; commit metadata only, do not redistribute raw PDF in repo.",
        "notes": "Source row is official event evidence only. A complete official baseline snapshot is still required before exact PIT intervals can be formal-ready.",
    }


def _download_pdf(url: str, local_path: Path) -> dict[str, str]:
    if not url:
        return {"download_status": "missing_url", "http_status": "", "content_type": "", "bytes": "0", "parse_status": "blocked_missing_url"}
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RotationRadarDataAudit/1.0)",
            "Accept": "application/pdf,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Referer": "https://taiwanindex.com.tw/downloads/technical_notice",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
            status = str(getattr(response, "status", ""))
            content_type = response.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001 - source audit must record remote failure.
        return {
            "download_status": f"download_failed:{type(exc).__name__}:{exc}",
            "http_status": "",
            "content_type": "",
            "bytes": "0",
            "parse_status": "download_failed",
        }
    if not data.startswith(b"%PDF"):
        return {
            "download_status": "downloaded_non_pdf",
            "http_status": status,
            "content_type": content_type,
            "bytes": str(len(data)),
            "parse_status": "blocked_non_pdf",
        }
    local_path.write_bytes(data)
    return {
        "download_status": "downloaded",
        "http_status": status,
        "content_type": content_type,
        "bytes": str(len(data)),
        "parse_status": "ready_for_core_parser",
    }


def _blocked_rows(
    accepted: list[dict[str, str]], failed: list[dict[str, str]]
) -> list[dict[str, str]]:
    rows = [
        {
            "blocker": "official_baseline_snapshot",
            "status": "blocked_missing",
            "details": "No complete official TW50 constituent baseline dated on or before first accepted event is included in this package.",
            "next_step": "Continue official baseline search or let Core combine accepted notices with a separately verified pre-event official baseline.",
        }
    ]
    if failed:
        rows.append(
            {
                "blocker": "technical_notice_downloads",
                "status": "partial_failed",
                "details": f"{len(failed)} official notice downloads failed.",
                "next_step": "Retry failed URLs with backoff; do not mark exact PIT ready until parser input set is complete enough for Core.",
            }
        )
    if not accepted:
        rows.append(
            {
                "blocker": "core_parser_input",
                "status": "blocked_no_pdfs",
                "details": "No official notice PDFs downloaded.",
                "next_step": "Retry Taiwan Index backend later or find official mirror/FTSE releases.",
            }
        )
    return rows


def _readiness(
    output_dir: Path,
    audit_rows: list[dict[str, str]],
    accepted: list[dict[str, str]],
    failed: list[dict[str, str]],
    blocked_rows: list[dict[str, str]],
) -> dict[str, Any]:
    first_event = min((row["source_date"] for row in accepted if row["source_date"]), default="")
    return {
        "generated_at": _now_iso(),
        "task_id": "TASK-BACKTEST-CORE-POOL2-PIT-REPLAY-COVERAGE-20260623",
        "package": output_dir.name,
        "status": "partial_exact_notice_pdfs_downloaded_baseline_missing" if accepted else "blocked_no_notice_pdfs",
        "ready": False,
        "formal_ready": False,
        "accepted_for_core_validator": False,
        "exact_or_proxy": "exact_candidate_event_sources_only",
        "source_type": "official_technical_notice",
        "candidate_notice_count": len(audit_rows),
        "downloaded_notice_count": len(accepted),
        "failed_notice_count": len(failed),
        "first_downloaded_event_source_date": first_event,
        "baseline_snapshot_status": "blocked_not_found",
        "official_baseline_found": False,
        "baseline_requirement": "Complete official TW50 constituent snapshot dated on or before the first accepted add/delete event.",
        "ready_for_core_parser": bool(accepted),
        "core_parser_input_dir": str(output_dir / "technical_notices_pdf"),
        "future_data_violation_count": 0,
        "public_source_exhausted": False,
        "blockers": [row["details"] for row in blocked_rows],
        "outputs": {
            "source_audit": "source_audit.csv",
            "accepted_sources": "accepted_sources.csv",
            "blocked_sources": "blocked_sources.csv",
            "failed": "failed.csv",
            "final_summary": "final_summary_zh.md",
        },
        "core_next_steps": [
            "Run Core tw50_technical_notice_events parser against core_parser_input_dir.",
            "Find or ingest a complete official baseline snapshot dated on or before the first accepted event.",
            "Only after parser events plus baseline are available, build exact PIT intervals and rerun Pool2/TW50 coverage validator.",
        ],
    }


def _write_summary(path: Path, readiness: dict[str, Any], accepted: list[dict[str, str]], failed: list[dict[str, str]]) -> None:
    lines = [
        "# Pool2/TW50 exact PIT source package",
        "",
        f"- 狀態：{readiness['status']}",
        f"- formal_ready：{readiness['formal_ready']}",
        f"- official technical notice PDFs：{len(accepted)} downloaded / {readiness['candidate_notice_count']} candidates",
        f"- failed downloads：{len(failed)}",
        f"- baseline snapshot：{readiness['baseline_snapshot_status']}",
        f"- Core parser input：{readiness['core_parser_input_dir']}",
        f"- future_data_violation_count：{readiness['future_data_violation_count']}",
        "",
        "## 邊界",
        "",
        "- 本包只包含 official technical notice event source，屬於 `exact_candidate`。",
        "- 事件來源本身不能單獨重建完整 50 檔 PIT 成分股；仍需要第一筆 event 前的官方完整 baseline snapshot。",
        "- 元大 0050 持股/月報/季報只能作 proxy_candidate，不在本包混入 exact。",
        "- raw PDF 放在 ignored folder，不提交 repo；commit 僅保留 metadata、manifest 與 audit。",
        "",
        "## Core 下一步",
        "",
        *[f"- {item}" for item in readiness["core_next_steps"]],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: str(value or "") for key, value in row.items()} for row in csv.DictReader(handle)]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    main()
