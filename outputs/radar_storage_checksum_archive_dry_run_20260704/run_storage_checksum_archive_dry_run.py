import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO / "outputs" / "radar_storage_governance_audit_20260704"
OUT_DIR = Path(__file__).resolve().parent
TASK_ID = "TASK-RADAR-DATA-STORAGE-CHECKSUM-ARCHIVE-DRY-RUN-20260704"

RAW_HINTS = ("raw_sources", "browser", "html", "pdf", "payload", "response")
RAW_EXTS = {".pdf", ".html", ".htm", ".json", ".zip", ".txt", ".log", ".xml", ".csv"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compression_ratio(path: Path) -> float:
    ext = path.suffix.lower()
    if ext in {".json", ".html", ".htm", ".xml", ".txt", ".log", ".csv"}:
        return 0.25
    if ext == ".pdf":
        return 0.90
    if ext == ".zip":
        return 0.98
    return 0.60


def is_archive_candidate(path: Path) -> bool:
    rel = path.as_posix().lower()
    return any(h in rel for h in RAW_HINTS) or path.suffix.lower() in RAW_EXTS


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    current_step = OUT_DIR / "current_step.txt"
    current_step.write_text("running checksum dry-run\n", encoding="utf-8")
    run_log = []
    rows = []
    audit_path = AUDIT_DIR / "archive_or_compress_candidates.csv"
    with audit_path.open("r", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)

    checksum_rows = []
    package_rows = []
    approval_rows = []
    seen_hash: dict[str, dict] = {}
    duplicates = []

    for row in rows:
        package = row["package"]
        rel_root = row["relative_path"]
        root = REPO / rel_root
        files = [p for p in root.rglob("*") if p.is_file() and is_archive_candidate(p)]
        package_size = 0
        package_estimated_zip = 0
        package_files = 0
        for path in files:
            rel = path.relative_to(REPO).as_posix()
            size = path.stat().st_size
            digest = sha256_file(path)
            est_zip = int(size * compression_ratio(path))
            duplicate_of = seen_hash.get(digest, {}).get("relative_path", "")
            is_dup = bool(duplicate_of)
            if not is_dup:
                seen_hash[digest] = {"relative_path": rel, "size": size}
            else:
                duplicates.append({"relative_path": rel, "duplicate_of": duplicate_of, "sha256": digest, "size_bytes": size})
            checksum_rows.append(
                {
                    "package": package,
                    "relative_path": rel,
                    "size_bytes": size,
                    "size_mb": round(size / 1024 / 1024, 6),
                    "sha256": digest,
                    "duplicate_of": duplicate_of,
                    "archive_candidate": True,
                    "estimated_compressed_bytes": est_zip,
                    "estimated_compressed_mb": round(est_zip / 1024 / 1024, 6),
                    "delete_allowed": False,
                    "compress_executed": False,
                    "move_executed": False,
                    "restore_source": rel,
                }
            )
            package_size += size
            package_estimated_zip += est_zip
            package_files += 1

        package_rows.append(
            {
                "package": package,
                "candidate_files": package_files,
                "candidate_size_mb": round(package_size / 1024 / 1024, 6),
                "estimated_compressed_mb": round(package_estimated_zip / 1024 / 1024, 6),
                "delete_allowed": False,
                "compress_executed": False,
                "move_executed": False,
                "approval_required": True,
                "source_audit_relative_path": rel_root,
            }
        )
        if package_files:
            approval_rows.append(
                {
                    "package": package,
                    "relative_path": rel_root,
                    "candidate_size_mb": round(package_size / 1024 / 1024, 6),
                    "estimated_compressed_mb": round(package_estimated_zip / 1024 / 1024, 6),
                    "reason": "raw/browser/source artifacts can be archived only after user approval and checksum review",
                    "restore_source": "checksum_manifest + original repo path",
                    "approval_required": True,
                    "delete_allowed": False,
                }
            )

    unique_size = sum(v["size"] for v in seen_hash.values())
    total_size = sum(r["size_bytes"] for r in checksum_rows)
    estimated_zip_unique = sum(
        r["estimated_compressed_bytes"] for r in checksum_rows if not r["duplicate_of"]
    )

    write_csv(
        OUT_DIR / "file_checksum_manifest.csv",
        checksum_rows,
        [
            "package",
            "relative_path",
            "size_bytes",
            "size_mb",
            "sha256",
            "duplicate_of",
            "archive_candidate",
            "estimated_compressed_bytes",
            "estimated_compressed_mb",
            "delete_allowed",
            "compress_executed",
            "move_executed",
            "restore_source",
        ],
    )
    write_csv(
        OUT_DIR / "archive_dry_run_candidates.csv",
        package_rows,
        [
            "package",
            "candidate_files",
            "candidate_size_mb",
            "estimated_compressed_mb",
            "delete_allowed",
            "compress_executed",
            "move_executed",
            "approval_required",
            "source_audit_relative_path",
        ],
    )
    write_csv(OUT_DIR / "duplicate_hash_rows.csv", duplicates, ["relative_path", "duplicate_of", "sha256", "size_bytes"])
    write_csv(
        OUT_DIR / "user_approval_table.csv",
        approval_rows,
        [
            "package",
            "relative_path",
            "candidate_size_mb",
            "estimated_compressed_mb",
            "reason",
            "restore_source",
            "approval_required",
            "delete_allowed",
        ],
    )

    manifest = {
        "task_id": TASK_ID,
        "status": "completed_dry_run_no_delete_no_compress",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_audit": str(AUDIT_DIR),
        "candidate_packages": len(rows),
        "checksum_rows": len(checksum_rows),
        "unique_hash_count": len(seen_hash),
        "duplicate_rows": len(duplicates),
        "candidate_size_mb": round(total_size / 1024 / 1024, 6),
        "deduplicated_candidate_size_mb": round(unique_size / 1024 / 1024, 6),
        "estimated_compressed_deduplicated_mb": round(estimated_zip_unique / 1024 / 1024, 6),
        "delete_executed": False,
        "move_executed": False,
        "compress_executed": False,
        "raw_data_deleted": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "user_approval_required_for_delete": True,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "completed.csv").write_text("task_id,status\n%s,completed\n" % TASK_ID, encoding="utf-8")
    (OUT_DIR / "failed.csv").write_text("task_id,status,reason\n", encoding="utf-8")
    run_log.append({"step": "checksum_dry_run", "status": "completed", "rows": len(checksum_rows)})
    write_csv(OUT_DIR / "run_log.csv", run_log, ["step", "status", "rows"])
    summary = f"""# Radar/Data storage checksum archive dry-run

- 狀態：`completed_dry_run_no_delete_no_compress`
- 來源 audit：`{AUDIT_DIR}`
- 候選 packages：`{len(rows)}`
- checksum rows：`{len(checksum_rows)}`
- unique hashes：`{len(seen_hash)}`
- duplicate rows：`{len(duplicates)}`
- 候選大小：`{manifest['candidate_size_mb']} MB`
- 去重後候選大小：`{manifest['deduplicated_candidate_size_mb']} MB`
- 估算壓縮後大小：`{manifest['estimated_compressed_deduplicated_mb']} MB`

## 邊界
- `delete_executed=false`
- `move_executed=false`
- `compress_executed=false`
- `raw_data_deleted=false`
- 所有刪除/封存仍需使用者批准。
"""
    (OUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    current_step.write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
