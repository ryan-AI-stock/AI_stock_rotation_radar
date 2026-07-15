from __future__ import annotations

import importlib.util
from pathlib import Path


OUT = Path(__file__).resolve().parent
ITER6 = OUT.parent / "radar_vnext_p1_p2_ma_slope_cd50_action_leg_frontier_iteration_006_20260715" / "run_iteration_006.py"

spec = importlib.util.spec_from_file_location("frontier_iteration_006", ITER6)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load iteration-006 runner: {ITER6}")
iteration6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iteration6)
runner = iteration6.runner

iteration6.OUT = OUT
iteration6.iteration5.OUT = OUT
iteration6.iteration5.iteration4.OUT = OUT
runner.OUT = OUT
runner.RAW_CACHE = OUT / "raw_audit_samples"
runner.LOCAL_CLASSIFICATION = OUT / "incumbent_continuity_local_classification.csv.gz"
runner.LOCAL_FRONTIER = OUT / "frontier_official_raw_local_reuse_patch.csv"
runner.NETWORK_PATCH = OUT / "frontier_official_raw_bounded_fill_patch.csv"
runner.SOURCE_MANIFEST = OUT / "frontier_source_manifest.csv"
runner.REGISTRY_REUSE = OUT / "incumbent_local_registry_exact_key_reuse.csv.gz"
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-007"
runner.EXPECTED_FRONTIER_ROWS = 84
runner.EXPECTED_REQUEST_SPANS = 19
runner.EXPECTED_POLICY_ROWS = 42
runner.EXPECTED_UNCLASSIFIED_ROWS = 4650
runner.PROVISIONAL_GAP_ROWS = 9169


SAME_MARKET_RETRY_AUDIT_COLUMNS = [
    "variant_id", "period", "ticker", "decision_date", "requested_execution_date",
    "market", "prior_cache_hash", "prior_cache_evidence_path", "retry_http_status",
    "retry_schema_ok", "retry_response_rows", "retry_exact_rows", "retry_outcome",
    "source_url", "source_hash", "raw_cache_path", "silent_fill",
    "future_data_violation_count",
]


def retry_invalid_same_market_cache_if_needed() -> None:
    blocked_path = OUT / "frontier_remaining_blocked.csv"
    blocked = runner.pd.read_csv(blocked_path, dtype=str)
    failed = blocked[blocked["blocked_reason"].fillna("").str.startswith("source_route_failed")]
    audit_rows: list[dict] = []
    accepted_rows: list[dict] = []
    manifest_rows: list[dict] = []
    evidence_dir = runner.RAW_CACHE / "failed_original"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    route_plan = runner.pd.read_csv(OUT / "frontier_bounded_route_plan.csv", dtype=str)

    for row in failed.to_dict("records"):
        target = row["requested_execution_date"]
        plan = route_plan[
            route_plan["period"].eq(row["period"])
            & route_plan["ticker"].eq(row["ticker"])
            & route_plan["requested_execution_date"].eq(target)
        ]
        if len(plan) != 1:
            raise RuntimeError(f"same-market retry route plan is not unique: {row}")
        market = plan.iloc[0]["market"]
        month = target[:7]
        route_id = f'{row["ticker"]}_{market}_{month}'
        cache = runner.RAW_CACHE / f"{route_id}.json"
        url = runner.official_month_url(row["ticker"], market, month)
        prior_raw = cache.read_bytes() if cache.exists() else b""
        prior_hash = runner.hashlib.sha256(prior_raw).hexdigest() if prior_raw else ""
        evidence = evidence_dir / f"{route_id}.{prior_hash[:12] or 'empty'}.invalid_response"
        if prior_raw and not evidence.exists():
            evidence.write_bytes(prior_raw)

        raw = b""
        status = 0
        final_url = url
        error = ""
        schema_ok = False
        parsed: list[dict] = []
        for attempt in range(4):
            try:
                response = runner.requests.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 RadarFrontierBoundedFailedOnly/1.0",
                        "Accept": "application/json",
                        "Cache-Control": "no-cache",
                    },
                    timeout=45,
                )
                status, final_url = response.status_code, response.url
                response.raise_for_status()
                candidate = response.content
                payload = runner.json.loads(candidate.decode("utf-8-sig"))
                schema_ok, parsed = runner.parse_official(payload, row["ticker"], market)
                if schema_ok:
                    raw = candidate
                    break
                error = "schema_not_ok"
            except (runner.requests.RequestException, UnicodeDecodeError, runner.json.JSONDecodeError, TypeError) as exc:
                error = type(exc).__name__
            runner.time.sleep(0.8 * (attempt + 1))

        exact_rows = [value for value in parsed if value["date"] == target] if schema_ok else []
        retrieved_at = runner.now()
        if raw and schema_ok:
            temp = cache.with_name(f"{cache.name}.{runner.os.getpid()}.{runner.time.time_ns()}.tmp")
            temp.write_bytes(raw)
            verify_payload = runner.json.loads(temp.read_text(encoding="utf-8-sig"))
            verify_schema, _ = runner.parse_official(verify_payload, row["ticker"], market)
            if not verify_schema:
                raise RuntimeError(f"same-market retry temp verification failed: {temp}")
            runner.os.replace(temp, cache)
        digest = runner.hashlib.sha256(raw).hexdigest() if raw else ""
        outcome = "accepted_exact_row" if exact_rows else (
            "official_valid_no_target_row" if schema_ok else "source_route_failed"
        )
        for value in exact_rows:
            accepted_rows.append({
                **{key: row[key] for key in [
                    "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date"
                ]},
                "market": market,
                "name": runner.pd.NA,
                "open": value["open"],
                "high": value["high"],
                "low": value["low"],
                "close": value["close"],
                "source_quality": f"official_{market.lower()}_selected_ticker_month_unadjusted_execution",
                "adjustment_policy": "official_unadjusted_execution_only",
                "source_url": final_url,
                "source_hash": digest,
                "retrieved_at": retrieved_at,
                "source_path": str(cache),
                "exact_key_ready": True,
                "fill_mode": "bounded_official_same_market_failed_only_retry",
                "future_data_violation_count": 0,
            })
        manifest_rows.append({
            "route_id": route_id,
            "period": row["period"],
            "ticker": row["ticker"],
            "market": market,
            "target_date": target,
            "year_month": month,
            "outcome": outcome,
            "http_status": status,
            "schema_ok": schema_ok,
            "response_rows": len(parsed),
            "accepted_exact_rows": len(exact_rows),
            "source_url": final_url,
            "source_hash": digest,
            "response_bytes": len(raw),
            "retrieved_at": retrieved_at,
            "raw_cache_path": str(cache),
            "cache_reused": False,
            "route_error": error if not schema_ok else "",
            "download_authority": "frontier_exact_leg_same_market_failed_only_retry",
            "future_data_violation_count": 0,
        })
        audit_rows.append({
            "variant_id": row["variant_id"],
            "period": row["period"],
            "ticker": row["ticker"],
            "decision_date": row["decision_date"],
            "requested_execution_date": target,
            "market": market,
            "prior_cache_hash": prior_hash,
            "prior_cache_evidence_path": str(evidence) if prior_raw else "",
            "retry_http_status": status,
            "retry_schema_ok": schema_ok,
            "retry_response_rows": len(parsed),
            "retry_exact_rows": len(exact_rows),
            "retry_outcome": outcome,
            "source_url": final_url,
            "source_hash": digest,
            "raw_cache_path": str(cache),
            "silent_fill": False,
            "future_data_violation_count": 0,
        })

    runner.pd.DataFrame(audit_rows, columns=SAME_MARKET_RETRY_AUDIT_COLUMNS).to_csv(
        OUT / "frontier_same_market_failed_only_retry_audit.csv", index=False
    )
    if accepted_rows:
        network = runner.pd.read_csv(runner.NETWORK_PATCH, dtype=str)
        network = runner.pd.concat([network, runner.pd.DataFrame(accepted_rows)], ignore_index=True)
        network.drop_duplicates(["period", "ticker", "requested_execution_date"], keep="last").to_csv(
            runner.NETWORK_PATCH, index=False
        )
    if manifest_rows:
        manifest = runner.pd.read_csv(runner.SOURCE_MANIFEST, dtype=str)
        runner.pd.concat([manifest, runner.pd.DataFrame(manifest_rows)], ignore_index=True).to_csv(
            runner.SOURCE_MANIFEST, index=False
        )
    if audit_rows:
        runner.finalize()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    runner.pd.DataFrame([
        {
            "dependency": "iteration_006_runner",
            "path": str(ITER6),
            "bytes": ITER6.stat().st_size,
            "sha256": runner.sha256(ITER6),
        },
        {
            "dependency": "iteration_005_runner",
            "path": str(iteration6.ITER5),
            "bytes": iteration6.ITER5.stat().st_size,
            "sha256": runner.sha256(iteration6.ITER5),
        },
        {
            "dependency": "iteration_004_runner",
            "path": str(iteration6.iteration5.ITER4),
            "bytes": iteration6.iteration5.ITER4.stat().st_size,
            "sha256": runner.sha256(iteration6.iteration5.ITER4),
        },
        {
            "dependency": "parameterized_frontier_base_runner",
            "path": str(iteration6.iteration5.iteration4.BASE),
            "bytes": iteration6.iteration5.iteration4.BASE.stat().st_size,
            "sha256": runner.sha256(iteration6.iteration5.iteration4.BASE),
        },
    ]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    iteration6.prepare_exact_authority()
    runner.main()
    retry_invalid_same_market_cache_if_needed()
    iteration6.iteration5.retry_schema_failed_routes_if_needed()
    iteration6.iteration5.iteration4.refresh_governance_outputs()
