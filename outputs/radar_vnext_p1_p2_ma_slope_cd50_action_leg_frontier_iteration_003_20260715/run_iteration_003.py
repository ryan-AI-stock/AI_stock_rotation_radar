from __future__ import annotations

import importlib.util
from pathlib import Path


OUT = Path(__file__).resolve().parent
BASE = OUT.parent / "radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_local_audit_bounded_fill_20260715" / "run_frontier_local_audit_bounded_fill.py"

spec = importlib.util.spec_from_file_location("frontier_base", BASE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load base runner: {BASE}")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

runner.OUT = OUT
runner.RAW_CACHE = OUT / "raw_audit_samples"
runner.LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
runner.LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
runner.NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
runner.SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
runner.REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-003"
runner.EXPECTED_FRONTIER_ROWS = 56
runner.EXPECTED_REQUEST_SPANS = 25
runner.EXPECTED_POLICY_ROWS = 39
runner.EXPECTED_UNCLASSIFIED_ROWS = 7404
runner.PROVISIONAL_GAP_ROWS = 10421


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    runner.pd.DataFrame([{
        "dependency": "parameterized_frontier_base_runner",
        "path": str(BASE),
        "bytes": BASE.stat().st_size,
        "sha256": runner.sha256(BASE),
    }]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    runner.main()
