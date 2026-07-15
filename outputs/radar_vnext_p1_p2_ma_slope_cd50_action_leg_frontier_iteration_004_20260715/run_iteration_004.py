from __future__ import annotations

import importlib.util
import json
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
runner.TASK_ID = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-ACTION-LEG-FRONTIER-ITERATION-004"
runner.EXPECTED_FRONTIER_ROWS = 75
runner.EXPECTED_REQUEST_SPANS = 29
runner.EXPECTED_POLICY_ROWS = 40
runner.EXPECTED_UNCLASSIFIED_ROWS = 6518
runner.PROVISIONAL_GAP_ROWS = 10625


def resolve_missing_authority_execution_dates() -> None:
    authority = runner.pd.read_csv(runner.FRONTIER, dtype=str)
    missing = authority["requested_execution_date"].fillna("").eq("")
    audit_rows: list[dict] = []
    runner.RAW_CACHE.mkdir(parents=True, exist_ok=True)
    for index, row in authority.loc[missing].iterrows():
        ticker = row["ticker"]
        decision_date = row["decision_date"]
        market = runner.infer_market_for_tickers({ticker}).get(ticker)
        if market is None:
            raise RuntimeError(f"cannot resolve market for blank authority date: {ticker}")
        month = decision_date[:7]
        route_id = f"{ticker}_{market}_{month}"
        cache = runner.RAW_CACHE / f"{route_id}.json"
        url = runner.official_month_url(ticker, market, month)
        retrieved_at = runner.now()
        if cache.exists():
            raw = cache.read_bytes()
            cache_reused = True
            status = 200
            final_url = url
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
        payload = json.loads(raw.decode("utf-8-sig"))
        schema_ok, parsed = runner.parse_official(payload, ticker, market)
        candidates = sorted(value["date"] for value in parsed if value["date"] > decision_date)
        if not schema_ok or not candidates:
            raise RuntimeError(
                f"official route cannot resolve first post-decision trading date: {ticker} {decision_date}"
            )
        resolved_date = candidates[0]
        digest = runner.hashlib.sha256(raw).hexdigest()
        authority.loc[index, "requested_execution_date"] = resolved_date
        audit_rows.append({
            "variant_id": row["variant_id"],
            "period": row["period"],
            "ticker": ticker,
            "role": row["role"],
            "decision_date": decision_date,
            "authority_requested_execution_date": "",
            "resolved_execution_date": resolved_date,
            "resolution_policy": "first_official_ticker_trading_day_after_decision_date",
            "market": market,
            "http_status": status,
            "schema_ok": schema_ok,
            "official_month_rows": len(parsed),
            "source_url": final_url,
            "source_hash": digest,
            "retrieved_at": retrieved_at,
            "raw_cache_path": str(cache),
            "cache_reused": cache_reused,
            "silent_fill": False,
            "future_data_violation_count": 0,
        })
    resolved_path = OUT / "frontier_authority_resolved.csv"
    authority.to_csv(resolved_path, index=False)
    runner.pd.DataFrame(audit_rows).to_csv(
        OUT / "frontier_missing_execution_date_resolution_audit.csv", index=False
    )
    runner.FRONTIER = resolved_path


def refresh_governance_outputs() -> None:
    audit = runner.pd.read_csv(OUT / "frontier_missing_execution_date_resolution_audit.csv", dtype=str)
    readiness_path = OUT / "readiness_for_core_rechain.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness.update({
        "authority_blank_execution_date_rows": int(len(audit)),
        "authority_blank_date_resolved_rows": int(len(audit)),
        "authority_date_resolution_policy": "first_official_ticker_trading_day_after_decision_date",
        "authority_date_resolution_silent_fill": False,
    })
    runner.write_json(readiness_path, readiness)
    summary_path = OUT / "final_summary_zh.md"
    summary = summary_path.read_text(encoding="utf-8")
    summary += (
        "\n## Authority date resolution\n\n"
        f"- Core authority 有 {len(audit)} 筆 execution date 空值；均以官方 ticker-month route 的 decision date 後首個實際交易日解析。\n"
        "- 原始空值、resolved date、URL、raw hash 與 policy 均獨立保存，silent_fill=false。\n"
    )
    summary_path.write_text(summary, encoding="utf-8")
    output_files = [
        path for path in OUT.iterdir() if path.is_file() and path.name not in {
            "manifest.json", "checksum_manifest.csv", "readiness_for_core_rechain.json", "final_summary_zh.md"
        }
    ]
    checksums = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": runner.sha256(path)}
        for path in sorted(output_files)
    ]
    runner.pd.DataFrame(checksums).to_csv(OUT / "checksum_manifest.csv", index=False)
    all_files = [path for path in OUT.iterdir() if path.is_file() and path.name != "manifest.json"]
    runner.write_json(OUT / "manifest.json", {
        "task": readiness["task"],
        "generated_at": runner.now(),
        "output_path": str(OUT),
        "files": [
            {"file": path.name, "bytes": path.stat().st_size, "sha256": runner.sha256(path)}
            for path in sorted(all_files)
        ],
        "flags": runner.FLAGS,
        "future_data_violation_count": 0,
    })


def retry_schema_failed_routes_on_alternate_market() -> None:
    blocked_path = OUT / "frontier_remaining_blocked.csv"
    blocked = runner.pd.read_csv(blocked_path, dtype=str)
    failed = blocked[blocked["blocked_reason"].fillna("").str.startswith("source_route_failed")]
    audit_rows: list[dict] = []
    accepted_rows: list[dict] = []
    manifest_rows: list[dict] = []
    for row in failed.to_dict("records"):
        ticker = row["ticker"]
        target = row["requested_execution_date"]
        month = target[:7]
        primary = runner.pd.read_csv(OUT / "frontier_bounded_route_plan.csv", dtype=str)
        primary_row = primary[
            primary["period"].eq(row["period"])
            & primary["ticker"].eq(ticker)
            & primary["requested_execution_date"].eq(target)
        ].iloc[0]
        primary_market = primary_row["market"]
        alternate_market = "TPEx" if primary_market == "TWSE" else "TWSE"
        route_id = f"{ticker}_{alternate_market}_{month}"
        cache = runner.RAW_CACHE / f"{route_id}.json"
        url = runner.official_month_url(ticker, alternate_market, month)
        retrieved_at = runner.now()
        if cache.exists():
            raw = cache.read_bytes()
            cache_reused = True
            status = 200
            final_url = url
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
            json.loads(raw.decode("utf-8-sig")), ticker, alternate_market
        )
        exact_rows = [value for value in parsed if value["date"] == target]
        outcome = "accepted_exact_row" if exact_rows else (
            "official_valid_no_target_row" if schema_ok else "source_route_failed"
        )
        for value in exact_rows:
            accepted_rows.append({
                **{key: row[key] for key in [
                    "variant_id", "period", "decision_date", "ticker", "role", "requested_execution_date"
                ]},
                "market": alternate_market,
                "name": runner.pd.NA,
                "open": value["open"],
                "high": value["high"],
                "low": value["low"],
                "close": value["close"],
                "source_quality": f"official_{alternate_market.lower()}_selected_ticker_month_unadjusted_execution",
                "adjustment_policy": "official_unadjusted_execution_only",
                "source_url": final_url,
                "source_hash": digest,
                "retrieved_at": retrieved_at,
                "source_path": str(cache),
                "exact_key_ready": True,
                "fill_mode": "bounded_official_alternate_market_ticker_month_route",
                "future_data_violation_count": 0,
            })
        manifest_rows.append({
            "route_id": route_id,
            "period": row["period"],
            "ticker": ticker,
            "market": alternate_market,
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
            "cache_reused": cache_reused,
            "route_error": "",
            "download_authority": "frontier_exact_leg_alternate_market_retry_only",
            "future_data_violation_count": 0,
        })
        audit_rows.append({
            "variant_id": row["variant_id"],
            "period": row["period"],
            "ticker": ticker,
            "decision_date": row["decision_date"],
            "requested_execution_date": target,
            "primary_market": primary_market,
            "primary_outcome": row["blocked_reason"],
            "alternate_market": alternate_market,
            "alternate_outcome": outcome,
            "alternate_exact_rows": len(exact_rows),
            "source_url": final_url,
            "source_hash": digest,
            "silent_fill": False,
            "future_data_violation_count": 0,
        })
    runner.pd.DataFrame(audit_rows).to_csv(OUT / "frontier_market_route_fallback_audit.csv", index=False)
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
    runner.pd.DataFrame([{
        "dependency": "parameterized_frontier_base_runner",
        "path": str(BASE),
        "bytes": BASE.stat().st_size,
        "sha256": runner.sha256(BASE),
    }]).to_csv(OUT / "runner_dependency_manifest.csv", index=False)
    resolve_missing_authority_execution_dates()
    runner.main()
    retry_schema_failed_routes_on_alternate_market()
    refresh_governance_outputs()
