from __future__ import annotations

import importlib.util
from pathlib import Path


OUT = Path(__file__).resolve().parent
ITER7 = OUT.parent / "radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_iteration_007_20260715" / "run_iteration_007.py"

spec = importlib.util.spec_from_file_location("frontier_iteration_007", ITER7)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load iteration-007 runner: {ITER7}")
iteration7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration7)
runner = iteration7.runner

iteration7.OUT = OUT
iteration7.iteration6.OUT = OUT
iteration7.iteration6.iteration5.OUT = OUT
iteration7.iteration6.iteration5.iteration4.OUT = OUT
runner.OUT = OUT
runner.RAW_CACHE = OUT / "raw_audit_samples"
runner.LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
runner.LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
runner.NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
runner.SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
runner.REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-008"
runner.EXPECTED_FRONTIER_ROWS = 88
runner.EXPECTED_REQUEST_SPANS = 18
runner.EXPECTED_POLICY_ROWS = 42
runner.EXPECTED_UNCLASSIFIED_ROWS = 4227
runner.PROVISIONAL_GAP_ROWS = 8865


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    runner.pd.DataFrame([
        {
            "dependency": "iteration_007_runner",
            "path": str(ITER7),
            "bytes": ITER7.stat().st_size,
            "sha256": runner.sha256(ITER7),
        },
        {
            "dependency": "iteration_006_runner",
            "path": str(iteration7.ITER6),
            "bytes": iteration7.ITER6.stat().st_size,
            "sha256": runner.sha256(iteration7.ITER6),
        },
        {
            "dependency": "iteration_005_runner",
            "path": str(iteration7.iteration6.ITER5),
            "bytes": iteration7.iteration6.ITER5.stat().st_size,
            "sha256": runner.sha256(iteration7.iteration6.ITER5),
        },
        {
            "dependency": "iteration_004_runner",
            "path": str(iteration7.iteration6.iteration5.ITER4),
            "bytes": iteration7.iteration6.iteration5.ITER4.stat().st_size,
            "sha256": runner.sha256(iteration7.iteration6.iteration5.ITER4),
        },
        {
            "dependency": "parameterized_frontier_base_runner",
            "path": str(iteration7.iteration6.iteration5.iteration4.BASE),
            "bytes": iteration7.iteration6.iteration5.iteration4.BASE.stat().st_size,
            "sha256": runner.sha256(iteration7.iteration6.iteration5.iteration4.BASE),
        },
    ]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    iteration7.iteration6.prepare_exact_authority()
    runner.main()
    blocked = runner.pd.read_csv(OUT / "frontier_remaining_blocked.csv", dtype=str)
    if not blocked.empty and "blocked_reason" in blocked.columns:
        iteration7.retry_invalid_same_market_cache_if_needed()
    else:
        runner.pd.DataFrame(columns=iteration7.SAME_MARKET_RETRY_AUDIT_COLUMNS).to_csv(
            OUT / "frontier_same_market_failed_only_retry_audit.csv", index=False
        )
    iteration7.iteration6.iteration5.retry_schema_failed_routes_if_needed()
    iteration7.iteration6.iteration5.iteration4.refresh_governance_outputs()
