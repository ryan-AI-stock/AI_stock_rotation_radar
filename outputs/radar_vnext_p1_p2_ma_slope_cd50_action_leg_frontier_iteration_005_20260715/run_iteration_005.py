from __future__ import annotations

import importlib.util
from pathlib import Path


OUT = Path(__file__).resolve().parent
ITER4 = OUT.parent / "radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_iteration_004_20260715" / "run_iteration_004.py"

spec = importlib.util.spec_from_file_location("frontier_iteration_004", ITER4)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load iteration-004 runner: {ITER4}")
iteration4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration4)
runner = iteration4.runner

iteration4.OUT = OUT
runner.OUT = OUT
runner.RAW_CACHE = OUT / "raw_audit_samples"
runner.LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
runner.LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
runner.NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
runner.SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
runner.REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-005"
runner.EXPECTED_FRONTIER_ROWS = 84
runner.EXPECTED_REQUEST_SPANS = 16
runner.EXPECTED_POLICY_ROWS = 50
runner.EXPECTED_UNCLASSIFIED_ROWS = 7405
runner.PROVISIONAL_GAP_ROWS = 10772


DATE_AUDIT_COLUMNS = [
    "variant_id", "period", "ticker", "role", "decision_date",
    "authority_requested_execution_date", "resolved_execution_date", "resolution_policy",
    "market", "http_status", "schema_ok", "official_month_rows", "source_url", "source_hash",
    "retrieved_at", "raw_cache_path", "cache_reused", "silent_fill",
    "future_data_violation_count",
]
FALLBACK_AUDIT_COLUMNS = [
    "variant_id", "period", "ticker", "decision_date", "requested_execution_date",
    "primary_market", "primary_outcome", "alternate_market", "alternate_outcome",
    "alternate_exact_rows", "source_url", "source_hash", "silent_fill",
    "future_data_violation_count",
]


def prepare_exact_authority() -> None:
    authority = runner.pd.read_csv(runner.FRONTIER, dtype=str)
    if authority["requested_execution_date"].fillna("").eq("").any():
        raise RuntimeError("iteration-005 authority unexpectedly contains a null execution date")
    resolved_path = OUT / "frontier_authority_resolved.csv"
    authority.to_csv(resolved_path, index=False)
    runner.pd.DataFrame(columns=DATE_AUDIT_COLUMNS).to_csv(
        OUT / "frontier_missing_execution_date_resolution_audit.csv", index=False
    )
    runner.FRONTIER = resolved_path


def prepare_bounded_historical_market_mapping() -> None:
    authority = runner.pd.read_csv(runner.FRONTIER, dtype=str)
    target = authority[authority["ticker"].eq("2325")]
    if len(target) != 1:
        raise RuntimeError("expected exactly one bounded 2325 frontier row")
    row = target.iloc[0]
    ticker = row["ticker"]
    target_date = row["requested_execution_date"]
    month = target_date[:7]
    audit_rows: list[dict] = []
    accepted_markets: list[str] = []
    runner.RAW_CACHE.mkdir(parents=True, exist_ok=True)
    for market in ["TWSE", "TPEx"]:
        route_id = f"{ticker}_{market}_{month}"
        cache = runner.RAW_CACHE / f"{route_id}.json"
        url = runner.official_month_url(ticker, market, month)
        if cache.exists():
            raw = cache.read_bytes()
            status = 200
            final_url = url
            cache_reused = True
        else:
            response = runner.requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 RadarFrontierBounded/1.0"},
                timeout=45,
            )
            status = response.status_code
            final_url = response.url
            response.raise_for_status()
            raw = response.content
            cache.write_bytes(raw)
            cache_reused = False
        digest = runner.hashlib.sha256(raw).hexdigest()
        schema_ok, parsed = runner.parse_official(
            iteration4.json.loads(raw.decode("utf-8-sig")), ticker, market
        )
        exact_rows = [value for value in parsed if value["date"] == target_date]
        if schema_ok and exact_rows:
            accepted_markets.append(market)
        audit_rows.append({
            "period": row["period"],
            "ticker": ticker,
            "decision_date": row["decision_date"],
            "requested_execution_date": target_date,
            "market_probe": market,
            "http_status": status,
            "schema_ok": schema_ok,
            "response_rows": len(parsed),
            "exact_target_rows": len(exact_rows),
            "source_url": final_url,
            "source_hash": digest,
            "raw_cache_path": str(cache),
            "cache_reused": cache_reused,
            "future_data_violation_count": 0,
        })
    if accepted_markets != ["TWSE"]:
        raise RuntimeError(f"bounded historical market mapping is not unique: {accepted_markets}")
    runner.pd.DataFrame(audit_rows).to_csv(OUT / "frontier_historical_market_inference_audit.csv", index=False)
    original_infer = runner.infer_market_for_tickers

    def infer_with_bounded_historical_evidence(tickers: set[str]) -> dict[str, str]:
        result = original_infer(tickers)
        if ticker in tickers:
            result[ticker] = "TWSE"
        return result

    runner.infer_market_for_tickers = infer_with_bounded_historical_evidence


def retry_schema_failed_routes_if_needed() -> None:
    blocked = runner.pd.read_csv(OUT / "frontier_remaining_blocked.csv", dtype=str)
    if blocked.empty or "blocked_reason" not in blocked.columns:
        runner.pd.DataFrame(columns=FALLBACK_AUDIT_COLUMNS).to_csv(
            OUT / "frontier_market_route_fallback_audit.csv", index=False
        )
        return
    iteration4.retry_schema_failed_routes_on_alternate_market()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    runner.pd.DataFrame([
        {
            "dependency": "iteration_004_runner",
            "path": str(ITER4),
            "bytes": ITER4.stat().st_size,
            "sha256": runner.sha256(ITER4),
        },
        {
            "dependency": "parameterized_frontier_base_runner",
            "path": str(iteration4.BASE),
            "bytes": iteration4.BASE.stat().st_size,
            "sha256": runner.sha256(iteration4.BASE),
        },
    ]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    prepare_exact_authority()
    prepare_bounded_historical_market_mapping()
    runner.main()
    retry_schema_failed_routes_if_needed()
    iteration4.refresh_governance_outputs()
