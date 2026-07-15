from __future__ import annotations

import importlib.util
from pathlib import Path


OUT = Path(__file__).resolve().parent
ITER5 = OUT.parent / "radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_iteration_005_20260715" / "run_iteration_005.py"

spec = importlib.util.spec_from_file_location("frontier_iteration_005", ITER5)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load iteration-005 runner: {ITER5}")
iteration5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration5)
runner = iteration5.runner

iteration5.OUT = OUT
iteration5.iteration4.OUT = OUT
runner.OUT = OUT
runner.RAW_CACHE = OUT / "raw_audit_samples"
runner.LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
runner.LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
runner.NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
runner.SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
runner.REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-006"
runner.EXPECTED_FRONTIER_ROWS = 94
runner.EXPECTED_REQUEST_SPANS = 17
runner.EXPECTED_POLICY_ROWS = 39
runner.EXPECTED_UNCLASSIFIED_ROWS = 2719
runner.PROVISIONAL_GAP_ROWS = 9686


HISTORICAL_MARKET_AUDIT_COLUMNS = [
    "period", "ticker", "decision_date", "requested_execution_date", "market_probe",
    "http_status", "schema_ok", "response_rows", "exact_target_rows", "source_url",
    "source_hash", "raw_cache_path", "cache_reused", "future_data_violation_count",
]


def prepare_exact_authority() -> None:
    authority = runner.pd.read_csv(runner.FRONTIER, dtype=str)
    if authority["requested_execution_date"].fillna("").eq("").any():
        raise RuntimeError("iteration-006 authority unexpectedly contains a null execution date")
    resolved_path = OUT / "frontier_authority_resolved.csv"
    authority.to_csv(resolved_path, index=False)
    runner.pd.DataFrame(columns=iteration5.DATE_AUDIT_COLUMNS).to_csv(
        OUT / "frontier_missing_execution_date_resolution_audit.csv", index=False
    )
    runner.pd.DataFrame(columns=HISTORICAL_MARKET_AUDIT_COLUMNS).to_csv(
        OUT / "frontier_historical_market_inference_audit.csv", index=False
    )
    runner.FRONTIER = resolved_path


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    runner.pd.DataFrame([
        {
            "dependency": "iteration_005_runner",
            "path": str(ITER5),
            "bytes": ITER5.stat().st_size,
            "sha256": runner.sha256(ITER5),
        },
        {
            "dependency": "iteration_004_runner",
            "path": str(iteration5.ITER4),
            "bytes": iteration5.ITER4.stat().st_size,
            "sha256": runner.sha256(iteration5.ITER4),
        },
        {
            "dependency": "parameterized_frontier_base_runner",
            "path": str(iteration5.iteration4.BASE),
            "bytes": iteration5.iteration4.BASE.stat().st_size,
            "sha256": runner.sha256(iteration5.iteration4.BASE),
        },
    ]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    prepare_exact_authority()
    runner.main()
    iteration5.retry_schema_failed_routes_if_needed()
    iteration5.iteration4.refresh_governance_outputs()
