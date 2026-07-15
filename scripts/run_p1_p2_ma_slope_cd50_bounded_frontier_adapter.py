from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
MATURE_RUNNER = (
    REPO
    / "outputs/radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_iteration_007_20260715/run_iteration_007.py"
)
FRONTIER_FILE = "p1_p2_MA_slope_CD50_frontier_official_raw_gap_ledger.csv"
INCUMBENT_REQUEST_FILE = "p1_p2_MA_slope_CD50_incumbent_continuity_local_audit_request.csv"
INCUMBENT_EXACT_FILE = "p1_p2_MA_slope_CD50_incumbent_analysis_gap_audit.csv.gz"
ATOMIC_FILE = "p1_p2_MA_slope_CD50_atomic_policy_blocker_ledger.csv"
CORE_READINESS_FILE = "readiness_for_action_leg_first.json"
PATCH_COLUMNS = [
    "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date",
    "market", "name", "open", "high", "low", "close", "source_quality",
    "adjustment_policy", "source_url", "source_hash", "retrieved_at", "source_path",
    "exact_key_ready", "fill_mode", "future_data_violation_count",
]
POLICY_COLUMNS = [
    "iteration", "blocker_code", "blocker_detail", "scope", "network_download_authorized",
    "future_data_violation_count",
]


class PolicyBlocker(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def write_checkpoint(output: Path, iteration: int, authority_hash: str, stage: str, **extra: object) -> None:
    atomic_json(
        output / "adapter_checkpoint.json",
        {
            "iteration": iteration,
            "authority_hash": authority_hash,
            "stage": stage,
            "updated_at": now(),
            "resume_command": (
                f'python "{Path(__file__).resolve()}" --iteration {iteration} '
                f'--core-output "{extra.get("core_output", "")}" --output "{output}"'
            ),
            **extra,
        },
    )
    (output / "current_step.txt").write_text(stage + "\n", encoding="utf-8")


def rebuild_governance(output: Path, task: str) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv", "readiness_for_core_rechain.json", "final_summary_zh.md"}
    files = sorted(path for path in output.iterdir() if path.is_file() and path.name not in excluded)
    pd.DataFrame(
        [{"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files]
    ).to_csv(output / "checksum_manifest.csv", index=False)
    manifest_files = sorted(path for path in output.iterdir() if path.is_file() and path.name != "manifest.json")
    atomic_json(
        output / "manifest.json",
        {
            "task": task,
            "generated_at": now(),
            "output_path": str(output),
            "files": [
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in manifest_files
            ],
            "future_data_violation_count": 0,
        },
    )


def load_scope(core_output: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, int, int]:
    required = [FRONTIER_FILE, INCUMBENT_REQUEST_FILE, INCUMBENT_EXACT_FILE, ATOMIC_FILE, CORE_READINESS_FILE]
    missing = [name for name in required if not (core_output / name).exists()]
    if missing:
        raise PolicyBlocker("required_core_artifact_missing", ",".join(missing))
    frontier = pd.read_csv(core_output / FRONTIER_FILE, dtype=str)
    request = pd.read_csv(core_output / INCUMBENT_REQUEST_FILE, dtype=str)
    atomic = pd.read_csv(core_output / ATOMIC_FILE, dtype=str)
    readiness = json.loads((core_output / CORE_READINESS_FILE).read_text(encoding="utf-8"))
    unclassified = int(pd.to_numeric(request.get("unclassified_dates"), errors="coerce").fillna(0).sum())
    provisional = int(readiness.get("all_provisional_unique_raw_gap_legs", -1))
    return frontier, request, atomic, readiness, unclassified, provisional


def validate_preflight(
    frontier: pd.DataFrame,
    request: pd.DataFrame,
    atomic: pd.DataFrame,
    readiness: dict,
    unclassified: int,
    provisional: int,
) -> None:
    required_frontier = {
        "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date"
    }
    if not required_frontier.issubset(frontier.columns):
        raise PolicyBlocker("frontier_schema_ambiguous", "missing required exact frontier columns")
    if frontier["requested_execution_date"].fillna("").eq("").any():
        raise PolicyBlocker("execution_date_ambiguous", "null requested_execution_date is not allowed")
    decision = pd.to_datetime(frontier["decision_date"], errors="coerce")
    execution = pd.to_datetime(frontier["requested_execution_date"], errors="coerce")
    if decision.isna().any() or execution.isna().any() or (execution <= decision).any():
        raise PolicyBlocker("execution_date_policy_ambiguous", "execution date must be valid and after decision date")
    keys = ["period", "ticker", "requested_execution_date"]
    if frontier.duplicated(keys).any():
        raise PolicyBlocker("frontier_exact_key_not_unique", "duplicate period/ticker/execution-date authority")
    if request.empty or request["network_download_authorized"].fillna("").str.lower().ne("false").any():
        raise PolicyBlocker("incumbent_network_policy_ambiguous", "all incumbent spans must remain local-only")
    if int(readiness.get("frontier_exact_official_raw_gap_legs", -1)) != len(frontier):
        raise PolicyBlocker("core_frontier_count_mismatch", "readiness and frontier ledger counts differ")
    if int(readiness.get("incumbent_analysis_unclassified_rows", -1)) != unclassified:
        raise PolicyBlocker("core_incumbent_count_mismatch", "readiness and local-only request counts differ")
    if int(readiness.get("atomic_policy_blockers", -1)) != len(atomic):
        raise PolicyBlocker("core_atomic_count_mismatch", "readiness and atomic ledger counts differ")
    if provisional < 0:
        raise PolicyBlocker("provisional_scope_count_missing", "Core readiness lacks provisional gap count")


def write_policy_stop(
    output: Path,
    iteration: int,
    core_output: Path,
    authority_hash: str,
    blocker: PolicyBlocker,
    frontier: pd.DataFrame | None,
    request_rows: int,
    unclassified: int,
    atomic_rows: int,
    provisional: int,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    frontier_rows = 0 if frontier is None else len(frontier)
    pd.DataFrame(
        [
            {"scope": "frontier_exact_legs", "rows": frontier_rows, "network_download_authorized": True, "loaded_for_download": False},
            {"scope": "incumbent_continuity_unclassified_exact_rows", "rows": unclassified, "network_download_authorized": False, "loaded_for_download": False},
            {"scope": "atomic_policy_blockers", "rows": atomic_rows, "network_download_authorized": False, "loaded_for_download": False},
            {"scope": "provisional_action_leg_gaps", "rows": provisional, "network_download_authorized": False, "loaded_for_download": False},
        ]
    ).to_csv(output / "authority_scope_guard_audit.csv", index=False)
    pd.DataFrame(
        [{
            "iteration": iteration,
            "blocker_code": blocker.code,
            "blocker_detail": blocker.detail,
            "scope": "adapter_preflight",
            "network_download_authorized": False,
            "future_data_violation_count": 0,
        }],
        columns=POLICY_COLUMNS,
    ).to_csv(output / "adapter_policy_blocker_ledger.csv", index=False)
    for name in [
        "frontier_official_raw_accepted_patch.csv",
        "frontier_official_raw_local_reuse_patch.csv",
        "frontier_official_raw_bounded_fill_patch.csv",
    ]:
        if not (output / name).exists():
            pd.DataFrame(columns=PATCH_COLUMNS).to_csv(output / name, index=False)
    if not (output / "frontier_official_no_trade_ledger.csv").exists():
        pd.DataFrame(columns=PATCH_COLUMNS + ["classification"]).to_csv(
            output / "frontier_official_no_trade_ledger.csv", index=False
        )
    blocked = frontier.copy() if frontier is not None else pd.DataFrame()
    blocked["blocked_reason"] = blocker.code
    blocked["future_data_violation_count"] = 0
    blocked.to_csv(output / "frontier_remaining_blocked.csv", index=False)
    if not (output / "incumbent_continuity_local_classification.csv.gz").exists():
        pd.DataFrame(columns=["period", "ticker", "date", "local_A_to_E_classification"]).to_csv(
            output / "incumbent_continuity_local_classification.csv.gz", index=False, compression="gzip"
        )
    pd.DataFrame([{
        "audit_item": "adapter_policy_ambiguity_stop",
        "status": "blocked",
        "future_data_violation_count": 0,
    }]).to_csv(output / "frontier_future_data_audit.csv", index=False)
    task = f"TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-{iteration:03d}"
    atomic_json(output / "readiness_for_core_rechain.json", {
        "task": task,
        "status": "policy_blocked_adapter_stopped",
        "frontier_authority_rows": frontier_rows,
        "frontier_closed_rows": 0,
        "frontier_exact_blocked_rows": frontier_rows,
        "incumbent_local_audit_request_spans": request_rows,
        "incumbent_network_download_rows": 0,
        "provisional_gap_rows_used_as_download_authority": 0,
        "atomic_policy_blocker_rows": atomic_rows,
        "adapter_policy_blocker_rows": 1,
        "ready_for_core_action_leg_frontier_rechain": False,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "not_live_rule": True,
    })
    write_checkpoint(
        output, iteration, authority_hash, "stopped_policy_blocker",
        core_output=str(core_output), blocker_code=blocker.code,
    )
    (output / "final_summary_zh.md").write_text(
        f"# Generic bounded adapter stopped\n\n- blocker: {blocker.code}\n- detail: {blocker.detail}\n"
        "- 未啟動 frontier 或 incumbent 網路下載。\n",
        encoding="utf-8",
    )
    rebuild_governance(output, task)


def import_mature_runner(output: Path, core_output: Path, iteration: int, counts: dict):
    spec = importlib.util.spec_from_file_location("generic_frontier_iteration_007", MATURE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load mature runner: {MATURE_RUNNER}")
    iteration7 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(iteration7)
    runner = iteration7.runner
    iteration7.OUT = output
    iteration7.iteration6.OUT = output
    iteration7.iteration6.iteration5.OUT = output
    iteration7.iteration6.iteration5.iteration4.OUT = output
    runner.OUT = output
    runner.CORE = core_output
    runner.FRONTIER = core_output / FRONTIER_FILE
    runner.INCUMBENT_REQUEST = core_output / INCUMBENT_REQUEST_FILE
    runner.INCUMBENT_EXACT = core_output / INCUMBENT_EXACT_FILE
    runner.POLICY = core_output / ATOMIC_FILE
    runner.RAW_CACHE = output / "raw_audit_samples"
    runner.LOCAL_CLASSIFICATION = output / "incumbent_continuity_local_classification.csv.gz"
    runner.LOCAL_FRONTIER = output / "frontier_official_raw_local_reuse_patch.csv"
    runner.NETWORK_PATCH = output / "frontier_official_raw_bounded_fill_patch.csv"
    runner.SOURCE_MANIFEST = output / "frontier_source_manifest.csv"
    runner.REGISTRY_REUSE = output / "incumbent_local_registry_exact_key_reuse.csv.gz"
    runner.TASK_ID = f"TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-{iteration:03d}"
    runner.EXPECTED_FRONTIER_ROWS = counts["frontier"]
    runner.EXPECTED_REQUEST_SPANS = counts["request_spans"]
    runner.EXPECTED_POLICY_ROWS = counts["atomic"]
    runner.EXPECTED_UNCLASSIFIED_ROWS = counts["unclassified"]
    runner.PROVISIONAL_GAP_ROWS = counts["provisional"]
    return iteration7, runner


def validate_route_plan(output: Path, frontier: pd.DataFrame) -> None:
    route = pd.read_csv(output / "frontier_bounded_route_plan.csv", dtype=str)
    if route.empty:
        return
    if not route["market"].fillna("").isin({"TWSE", "TPEx"}).all():
        raise PolicyBlocker("market_route_ambiguous", "route plan contains unresolved market")
    authority_keys = set(zip(frontier["period"], frontier["ticker"], frontier["requested_execution_date"]))
    route_keys = set(zip(route["period"], route["ticker"], route["requested_execution_date"]))
    if not route_keys.issubset(authority_keys):
        raise PolicyBlocker("network_authority_escape", "route plan contains non-frontier exact key")
    urls = route["trusted_raw_source_url"].fillna("")
    tw_conflict = urls.str.contains(r"\.TW(?:\?|$)", regex=True) & route["market"].ne("TWSE")
    two_conflict = urls.str.contains(r"\.TWO(?:\?|$)", regex=True) & route["market"].ne("TPEx")
    if tw_conflict.any() or two_conflict.any():
        raise PolicyBlocker("market_source_evidence_conflict", "trusted source suffix conflicts with route market")
    if route.groupby("ticker")["market"].nunique().gt(1).any():
        raise PolicyBlocker("historical_market_transition_requires_review", "ticker maps to multiple markets in one frontier")


def existing_complete(output: Path, counts: dict) -> bool:
    readiness_path = output / "readiness_for_core_rechain.json"
    guard_path = output / "authority_scope_guard_audit.csv"
    if not readiness_path.exists() or not guard_path.exists():
        return False
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    guard = pd.read_csv(guard_path)
    exact = guard.loc[guard.scope.eq("frontier_exact_legs")]
    return (
        readiness.get("frontier_authority_rows") == counts["frontier"]
        and readiness.get("frontier_closed_rows") == counts["frontier"]
        and readiness.get("frontier_exact_blocked_rows") == 0
        and readiness.get("incumbent_network_download_rows") == 0
        and readiness.get("provisional_gap_rows_used_as_download_authority") == 0
        and readiness.get("atomic_policy_blocker_rows") == counts["atomic"]
        and len(exact) == 1
        and int(exact.iloc[0].rows) == counts["frontier"]
    )


def finalize_adapter_metadata(
    output: Path,
    core_output: Path,
    iteration: int,
    authority_hash: str,
    counts: dict,
    resume_mode: str,
) -> None:
    pd.DataFrame(columns=POLICY_COLUMNS).to_csv(output / "adapter_policy_blocker_ledger.csv", index=False)
    dependencies = output / "runner_dependency_manifest.csv"
    frame = pd.read_csv(dependencies, dtype=str) if dependencies.exists() else pd.DataFrame()
    adapter_row = pd.DataFrame([{
        "dependency": "generic_bounded_frontier_adapter",
        "path": str(Path(__file__).resolve()),
        "bytes": Path(__file__).stat().st_size,
        "sha256": sha256(Path(__file__)),
    }])
    frame = pd.concat([frame[frame.get("dependency", pd.Series(dtype=str)).ne("generic_bounded_frontier_adapter")], adapter_row], ignore_index=True)
    frame.to_csv(dependencies, index=False)
    write_checkpoint(
        output, iteration, authority_hash, "complete_ready_for_core_rechain",
        core_output=str(core_output), resume_mode=resume_mode,
        frontier_authority_rows=counts["frontier"],
    )
    readiness_path = output / "readiness_for_core_rechain.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness.update({
        "generic_bounded_adapter": True,
        "adapter_iteration": iteration,
        "adapter_authority_hash": authority_hash,
        "adapter_checkpoint_resume_supported": True,
        "adapter_policy_blocker_rows": 0,
        "adapter_resume_mode": resume_mode,
    })
    atomic_json(readiness_path, readiness)
    rebuild_governance(output, readiness["task"])


def stop_after_runtime_blocker(
    output: Path,
    core_output: Path,
    iteration: int,
    authority_hash: str,
    blocker_code: str,
    blocked: pd.DataFrame,
) -> int:
    detail = ",".join(
        blocked[["period", "ticker", "requested_execution_date"]]
        .astype(str).agg("/".join, axis=1).tolist()
    )
    pd.DataFrame(
        [{
            "iteration": iteration,
            "blocker_code": blocker_code,
            "blocker_detail": detail,
            "scope": "frontier_exact_legs",
            "network_download_authorized": False,
            "future_data_violation_count": 0,
        }],
        columns=POLICY_COLUMNS,
    ).to_csv(output / "adapter_policy_blocker_ledger.csv", index=False)
    readiness_path = output / "readiness_for_core_rechain.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness.update({
        "status": "frontier_policy_blocked_adapter_stopped",
        "generic_bounded_adapter": True,
        "adapter_iteration": iteration,
        "adapter_authority_hash": authority_hash,
        "adapter_checkpoint_resume_supported": True,
        "adapter_policy_blocker_rows": len(blocked),
        "ready_for_core_action_leg_frontier_rechain": False,
    })
    atomic_json(readiness_path, readiness)
    write_checkpoint(
        output, iteration, authority_hash, "stopped_policy_blocker",
        core_output=str(core_output), blocker_code=blocker_code,
    )
    rebuild_governance(output, readiness["task"])
    print(f"policy_blocked:{blocker_code}:{detail}", file=sys.stderr)
    return 2


def run(args: argparse.Namespace) -> int:
    core_output = args.core_output.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    frontier: pd.DataFrame | None = None
    request = pd.DataFrame()
    atomic = pd.DataFrame()
    readiness: dict = {}
    unclassified = 0
    provisional = 0
    authority_hash = sha256(core_output / FRONTIER_FILE) if (core_output / FRONTIER_FILE).exists() else ""
    try:
        frontier, request, atomic, readiness, unclassified, provisional = load_scope(core_output)
        validate_preflight(frontier, request, atomic, readiness, unclassified, provisional)
        counts = {
            "frontier": len(frontier),
            "request_spans": len(request),
            "atomic": len(atomic),
            "unclassified": unclassified,
            "provisional": provisional,
        }
        checkpoint_path = output / "adapter_checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
        if checkpoint and checkpoint.get("authority_hash") != authority_hash:
            raise PolicyBlocker("authority_hash_mismatch_existing_output", "output belongs to a different frontier")
        if existing_complete(output, counts):
            finalize_adapter_metadata(
                output, core_output, args.iteration, authority_hash, counts, "existing_complete_output_adopted"
            )
            return 0
        non_checkpoint_files = [path for path in output.iterdir() if path.is_file() and path.name != "current_step.txt"]
        if non_checkpoint_files and not checkpoint:
            raise PolicyBlocker("nonempty_output_without_checkpoint", "refusing to mix an untracked partial output")

        iteration7, runner = import_mature_runner(output, core_output, args.iteration, counts)
        pd.DataFrame([{
            "dependency": "generic_bounded_frontier_adapter",
            "path": str(Path(__file__).resolve()),
            "bytes": Path(__file__).stat().st_size,
            "sha256": sha256(Path(__file__)),
        }, {
            "dependency": "mature_iteration_007_runner",
            "path": str(MATURE_RUNNER),
            "bytes": MATURE_RUNNER.stat().st_size,
            "sha256": sha256(MATURE_RUNNER),
        }]).to_csv(output / "runner_dependency_manifest.csv", index=False)
        iteration7.iteration6.prepare_exact_authority()
        stage = checkpoint.get("stage", "")
        if stage not in {"local_complete", "fill_complete"}:
            try:
                runner.local_audit()
            except RuntimeError as exc:
                if "unresolved market" in str(exc).lower():
                    raise PolicyBlocker("market_route_ambiguous", str(exc)) from exc
                raise
            validate_route_plan(output, frontier)
            write_checkpoint(
                output, args.iteration, authority_hash, "local_complete", core_output=str(core_output)
            )
        else:
            runner.FRONTIER = output / "frontier_authority_resolved.csv"
            validate_route_plan(output, frontier)
        if stage != "fill_complete":
            runner.bounded_fill()
            write_checkpoint(
                output, args.iteration, authority_hash, "fill_complete", core_output=str(core_output)
            )
        runner.finalize()
        blocked = pd.read_csv(output / "frontier_remaining_blocked.csv", dtype=str)
        if not blocked.empty and "blocked_reason" in blocked.columns:
            iteration7.retry_invalid_same_market_cache_if_needed()
        else:
            pd.DataFrame(columns=iteration7.SAME_MARKET_RETRY_AUDIT_COLUMNS).to_csv(
                output / "frontier_same_market_failed_only_retry_audit.csv", index=False
            )
        blocked = pd.read_csv(output / "frontier_remaining_blocked.csv", dtype=str)
        pd.DataFrame(columns=iteration7.iteration6.iteration5.FALLBACK_AUDIT_COLUMNS).to_csv(
            output / "frontier_market_route_fallback_audit.csv", index=False
        )
        if not blocked.empty:
            return stop_after_runtime_blocker(
                output, core_output, args.iteration, authority_hash,
                "exact_source_or_market_policy_review_required", blocked,
            )
        pd.DataFrame(columns=POLICY_COLUMNS).to_csv(output / "adapter_policy_blocker_ledger.csv", index=False)
        write_checkpoint(
            output, args.iteration, authority_hash, "complete_ready_for_core_rechain",
            core_output=str(core_output), resume_mode="checkpointed_bounded_execution",
        )
        iteration7.iteration6.iteration5.iteration4.refresh_governance_outputs()
        finalize_adapter_metadata(
            output, core_output, args.iteration, authority_hash, counts, "checkpointed_bounded_execution"
        )
        return 0
    except PolicyBlocker as blocker:
        write_policy_stop(
            output, args.iteration, core_output, authority_hash, blocker, frontier,
            len(request), unclassified, len(atomic), provisional,
        )
        print(f"policy_blocked:{blocker.code}:{blocker.detail}", file=sys.stderr)
        return 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Generic bounded MA-slope CD50 frontier adapter")
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--core-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
