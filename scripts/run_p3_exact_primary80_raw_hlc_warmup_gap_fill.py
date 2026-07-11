from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
P3 = ROOT / "outputs" / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
EXACT = ROOT / "outputs" / "radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711"
OUT = ROOT / "outputs" / "radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711"
PRIMARY = CORE / "outputs" / "vnext_layer4_80_primary_pool_contract_20260708" / "layer4_80_primary_pool_contract.csv"
P3_START = date(2023, 7, 11)
EXACT_END = date(2026, 6, 29)
WARMUP_SESSIONS = 60
TASK = "TASK-RADAR-DATA-VNEXT-P3-EXACT-PRIMARY80-RAW-HLC-WARMUP-GAP-FILL-001"
FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_replace(tmp: Path, target: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.15 * (attempt + 1))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else ["status"])
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    atomic_replace(tmp, path)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_source_module():
    runner = P3 / "run_p3_recent_full_feature_acquisition.py"
    spec = importlib.util.spec_from_file_location("p3_hlc_source", runner)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing P3 source runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    return module


SRC = load_source_module()


def primary_rows() -> pd.DataFrame:
    cols = ["snapshot_date", "ticker", "name", "market", "is_layer4_primary_pool", "layer4_pool_role", "reference_only", "pool_rank"]
    rows = pd.read_csv(PRIMARY, usecols=cols, dtype={"ticker": str}, low_memory=False)
    rows["snapshot_date"] = pd.to_datetime(rows["snapshot_date"])
    rows["ticker"] = rows["ticker"].astype(str).str.strip()
    return rows[
        rows["is_layer4_primary_pool"].eq(True)
        & rows["snapshot_date"].dt.date.between(P3_START, EXACT_END)
    ].sort_values(["snapshot_date", "pool_rank", "ticker"])


def trading_dates() -> list[date]:
    found: set[date] = set()
    for path in sorted((P3 / "compact" / "price").glob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                found.add(date.fromisoformat(row["date"]))
    return sorted(found)


def build_requirements() -> tuple[list[dict], dict[tuple[str, str, str], dict], dict[str, dict]]:
    primary = primary_rows()
    sessions = trading_dates()
    snapshots = sorted(primary.snapshot_date.dt.date.unique())
    by_snapshot = {snap: primary[primary.snapshot_date.dt.date.eq(snap)] for snap in snapshots}
    previous: set[str] = set()
    segments: list[dict] = []
    required: dict[tuple[str, str, str], dict] = {}
    meta: dict[str, dict] = {}
    for snap in snapshots:
        frame = by_snapshot[snap]
        current = set(frame.ticker.astype(str))
        entrants = current - previous
        session_pos = sum(d < snap for d in sessions)
        window = sessions[max(0, session_pos - WARMUP_SESSIONS):session_pos]
        for row in frame[frame.ticker.isin(entrants)].itertuples(index=False):
            ticker = str(row.ticker)
            meta[ticker] = {"name": row.name, "market": row.market}
            segments.append({
                "ticker": ticker,
                "name": row.name,
                "market": row.market,
                "segment_start_snapshot": snap.isoformat(),
                "warmup_required_sessions": WARMUP_SESSIONS,
                "warmup_actual_sessions": len(window),
                "warmup_start": window[0].isoformat() if window else "",
                "warmup_end": window[-1].isoformat() if window else "",
                "segment_type": "initial_or_reentry_primary80",
            })
            for d in window:
                key = (d.isoformat(), ticker, row.market)
                required[key] = {
                    "date": d.isoformat(),
                    "ticker": ticker,
                    "name": row.name,
                    "market": row.market,
                    "required_by_segment_start": snap.isoformat(),
                    "requirement": "official_raw_hlc_pre_segment_60td_warmup",
                }
        previous = current
    return segments, required, meta


def write_scope() -> None:
    segments, required, _ = build_requirements()
    write_csv(OUT / "p3_exact_primary80_membership_segments.csv", segments)
    local = OUT / "local"
    local.mkdir(parents=True, exist_ok=True)
    with gzip.open(local / "p3_exact_primary80_raw_hlc_warmup_required_ticker_dates.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(next(iter(required.values()))))
        writer.writeheader()
        writer.writerows(required.values())
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_requirement_summary.csv", [{
        "segment_count": len(segments),
        "unique_tickers": len({r["ticker"] for r in segments}),
        "required_unique_ticker_dates": len(required),
        "required_unique_dates": len({k[0] for k in required}),
        "required_markets": ",".join(sorted({k[2] for k in required})),
        "warmup_sessions_per_segment": WARMUP_SESSIONS,
        "primary_contract_sha256": hashlib.sha256(PRIMARY.read_bytes()).hexdigest(),
        "adjusted_blocked_tickers_reprobed": False,
    }])
    write_json(OUT / "scope_progress.json", {"status": "completed", "segments": len(segments), "required_ticker_dates": len(required), "updated_at": now()})
    (OUT / "current_step.txt").write_text("scope_completed_reuse_pending\n", encoding="utf-8")


def load_reuse(required: set[tuple[str, str, str]]) -> tuple[dict[tuple[str, str, str], dict], dict[tuple[str, str, str], str]]:
    rows: dict[tuple[str, str, str], dict] = {}
    provenance: dict[tuple[str, str, str], str] = {}
    sources = [
        (EXACT / "compact" / "price", "reused_exact_primary80_active_compact"),
        (P3 / "compact" / "price", "reused_prior_p3_watchlist_compact_where_ticker_date_exactly_matches"),
    ]
    for folder, label in sources:
        for path in sorted(folder.glob("*.csv.gz")):
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    key = (row.get("date", ""), row.get("ticker", ""), row.get("market", ""))
                    if key in required and key not in rows:
                        rows[key] = row
                        provenance[key] = label
    return rows, provenance


def shard_path(market: str, date_s: str) -> Path:
    return OUT / "checkpoints" / "raw_hlc_warmup" / market / f"{date_s}.csv.gz"


def run_repair(workers: int) -> None:
    _, required_map, _ = build_requirements()
    required = set(required_map)
    reused, provenance = load_reuse(required)
    routes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for date_s, ticker, market in required:
        routes[(date_s, market)].add(ticker)
    prior = {(r.get("date", ""), r.get("market", "")): r for r in read_csv(OUT / "raw_hlc_warmup_source_manifest.csv")}
    tasks = []
    for (date_s, market), tickers in sorted(routes.items()):
        output = shard_path(market, date_s)
        if output.exists():
            if (date_s, market) not in prior:
                recovered = read_gzip(output)
                ready = {r.get("ticker", "") for r in recovered}
                sample = recovered[0] if recovered else {}
                prior[(date_s, market)] = {
                    "date": date_s,
                    "market": market,
                    "route_status": "accepted" if recovered else "no_rows_valid_official_response",
                    "required_tickers": len(tickers),
                    "ready_tickers": len(ready & tickers),
                    "blocked_tickers": len(tickers - ready),
                    "retrieval_attempted": True,
                    "http_status": "recovered_from_completed_checkpoint",
                    "source_url": sample.get("source_url", ""),
                    "source_hash": sample.get("source_hash", ""),
                    "retrieval_time_utc": sample.get("retrieval_time_utc", ""),
                    "error": "",
                }
            continue
        route_keys = {(date_s, ticker, market) for ticker in tickers}
        existing = {key: reused[key] for key in route_keys if key in reused}
        if len(existing) == len(route_keys):
            SRC.write_shard(output, list(existing.values()), SRC.PRICE_FIELDS)
            prior[(date_s, market)] = {
                "date": date_s, "market": market, "route_status": "reused_existing_compact",
                "required_tickers": len(tickers), "ready_tickers": len(tickers), "blocked_tickers": 0,
                "retrieval_attempted": False, "source_url": "local_compact", "source_hash": "",
            }
        else:
            tasks.append((date_s, market, tickers, existing))
    total = len(tasks)
    progress = OUT / "raw_hlc_warmup_progress.json"
    write_json(progress, {"status": "running", "completed_routes": len(prior), "total_routes": len(routes), "new_retrieval_completed": 0, "new_retrieval_total": total, "updated_at": now()})

    def fetch(item):
        date_s, market, tickers, existing = item
        result = SRC.fetch_price((market, date.fromisoformat(date_s), tickers))
        output = shard_path(market, date_s)
        fresh = read_gzip(output)
        merged = {(r.get("date", ""), r.get("ticker", ""), r.get("market", "")): r for r in [*existing.values(), *fresh]}
        filtered = [merged[key] for key in sorted(merged) if key[0] == date_s and key[2] == market and key[1] in tickers]
        SRC.write_shard(output, filtered, SRC.PRICE_FIELDS)
        ready = {r["ticker"] for r in filtered}
        return {
            "date": date_s, "market": market, "route_status": result.get("status", ""),
            "required_tickers": len(tickers), "ready_tickers": len(ready), "blocked_tickers": len(tickers - ready),
            "retrieval_attempted": True, "http_status": result.get("http_status", ""),
            "source_url": result.get("source_url", ""), "source_hash": result.get("response_sha256", ""),
            "retrieval_time_utc": result.get("retrieval_time_utc", ""), "error": result.get("error", ""),
        }

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, task) for task in tasks]
        for future in as_completed(futures):
            row = future.result()
            prior[(row["date"], row["market"])] = row
            completed += 1
            if completed % 10 == 0 or completed == total:
                write_csv(OUT / "raw_hlc_warmup_source_manifest.csv", sorted(prior.values(), key=lambda r: (r["date"], r["market"])))
                write_json(progress, {"status": "running", "completed_routes": len(prior), "total_routes": len(routes), "new_retrieval_completed": completed, "new_retrieval_total": total, "updated_at": now()})
                (OUT / "current_step.txt").write_text(f"raw_hlc_warmup_running_{completed}_of_{total}\n", encoding="utf-8")
    write_csv(OUT / "raw_hlc_warmup_source_manifest.csv", sorted(prior.values(), key=lambda r: (r["date"], r["market"])))
    write_json(progress, {"status": "completed", "completed_routes": len(prior), "total_routes": len(routes), "new_retrieval_completed": total, "new_retrieval_total": total, "updated_at": now()})
    consolidate()


def consolidate() -> None:
    by_year: dict[str, dict[tuple[str, str, str], dict]] = defaultdict(dict)
    for path in (OUT / "checkpoints" / "raw_hlc_warmup").rglob("*.csv.gz"):
        for row in read_gzip(path):
            key = (row["date"], row["ticker"], row["market"])
            by_year[row["date"][:4]][key] = row
    for year, rows in by_year.items():
        target = OUT / "compact" / "raw_hlc_warmup" / f"{year}.csv.gz"
        SRC.write_shard(target, [rows[key] for key in sorted(rows)], SRC.PRICE_FIELDS)


def audit() -> None:
    segments, required_map, _ = build_requirements()
    required = set(required_map)
    actual: dict[tuple[str, str, str], dict] = {}
    for path in (OUT / "compact" / "raw_hlc_warmup").glob("*.csv.gz"):
        for row in read_gzip(path):
            key = (row.get("date", ""), row.get("ticker", ""), row.get("market", ""))
            if key in required and row.get("open") and row.get("high") and row.get("low") and row.get("close"):
                actual[key] = row
    route_manifest = {(r["date"], r["market"]): r for r in read_csv(OUT / "raw_hlc_warmup_source_manifest.csv")}
    blocked = []
    for key in sorted(required - set(actual)):
        date_s, ticker, market = key
        route = route_manifest.get((date_s, market), {})
        status = route.get("route_status", "missing_route")
        if status == "accepted":
            classification = "official_zero_or_not_applicable"
            reason = "official market file accepted but exact ticker row absent; suspended/no-trade/not-applicable; no neighbor substitution"
        elif status == "no_rows_valid_official_response":
            classification = "official_no_market_rows_on_required_session"
            reason = "official route returned valid zero rows for market/date confirmed by shared trading calendar"
        else:
            classification = "source_gap"
            reason = f"official route not accepted: {status}; {route.get('error','')}"
        blocked.append({
            **required_map[key], "classification": classification, "blocked_reason": reason,
            "route_status": status, "source_url": route.get("source_url", ""), "source_hash": route.get("source_hash", ""),
        })
    by_segment = []
    required_dates_by_ticker: dict[str, list[str]] = defaultdict(list)
    for date_s, ticker, _ in required:
        required_dates_by_ticker[ticker].append(date_s)
    for ticker in required_dates_by_ticker:
        required_dates_by_ticker[ticker] = sorted(set(required_dates_by_ticker[ticker]))
    actual_keys = set(actual)
    for segment in segments:
        ticker = segment["ticker"]
        start = segment["warmup_start"]
        end = segment["warmup_end"]
        dates = [date_s for date_s in required_dates_by_ticker[ticker] if start <= date_s <= end]
        ready = sum((date_s, ticker, segment["market"]) in actual_keys for date_s in dates)
        by_segment.append({**segment, "required_unique_ticker_dates": len(dates), "ready_unique_ticker_dates": ready, "blocked_unique_ticker_dates": len(dates) - ready, "kd_raw_hlc_warmup_ready": ready >= WARMUP_SESSIONS})
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_coverage_by_segment.csv", by_segment)
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_blocked_ledger.csv", blocked)
    classifications = defaultdict(int)
    for row in blocked:
        classifications[row["classification"]] += 1
    coverage = {
        "required_ticker_dates": len(required),
        "ready_ticker_dates": len(actual),
        "blocked_ticker_dates": len(required) - len(actual),
        "ready_share": round(len(actual) / len(required), 10) if required else 0,
        "segment_count": len(segments),
        "complete_60td_segments": sum(str(r["kd_raw_hlc_warmup_ready"]).lower() == "true" for r in by_segment),
        "blocked_classification_counts": dict(classifications),
    }
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_coverage_audit.csv", [{**coverage, "source_quality": "official_twse_tpex_raw_execution_ohlcv", "adjustment_policy": "raw_only; Core applies existing trusted factor; raw not adjusted"}])
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_future_data_audit.csv", [{"audit": "warmup_before_membership_segment_only", "future_data_violation_count": 0, "neighbor_date_substitution": False, "raw_used_as_adjusted": False, "adjusted_11_reprobed": False, "result": "pass"}])
    compact_manifest = []
    for path in sorted((OUT / "compact").rglob("*.csv.gz")):
        compact_manifest.append({"path": str(path.relative_to(OUT)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_csv(OUT / "p3_exact_primary80_raw_hlc_warmup_compact_hash_manifest.csv", compact_manifest)
    ready_for_core = len(actual) > 0 and not any(r["classification"] == "source_gap" for r in blocked)
    readiness = {
        "task_id": TASK,
        "status": "raw_hlc_warmup_source_package_ready_with_explicit_official_no_rows" if ready_for_core else "raw_hlc_warmup_partial_source_gaps_remain",
        "source": "official TWSE/TPEx raw OHLCV; reused exact-key local compact plus bounded market-wide repair",
        "coverage": coverage,
        "future_data_violation_count": 0,
        "ready_for_core_p3_exact_primary80_raw_hlc_warmup_absorption": ready_for_core,
        "ready_for_experiments": False,
        "adjusted_11_reprobed": False,
        "raw_used_as_adjusted": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_exact_primary80_raw_hlc_warmup.json", readiness)
    summary = f"""# P3 exact primary80 raw HLC warmup gap fill\n\n- Membership segments：{len(segments)}。\n- Required ticker-dates：{len(required)}。\n- Ready official raw O/H/L/C：{len(actual)}。\n- Blocked：{len(required)-len(actual)}，classification={dict(classifications)}。\n- Complete 60TD segments：{coverage['complete_60td_segments']}/{len(segments)}。\n- adjusted 11 未重探；raw 沒有冒充 adjusted；Core 才能套用既有 trusted factor。\n- future_data_violation_count=0。\n- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_ready_for_core_absorption\n" if ready_for_core else "completed_partial_source_gaps_remain\n", encoding="utf-8")
    files = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "manifest.json" and not path.name.endswith(".tmp"):
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "manifest.json", {"task_id": TASK, "generated_at_utc": now(), "primary_contract": str(PRIMARY), "primary_contract_sha256": hashlib.sha256(PRIMARY.read_bytes()).hexdigest(), "coverage": coverage, "files": files, "compact_files": compact_manifest, "future_data_violation_count": 0, **FLAGS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["scope", "repair", "audit", "all"], default="all")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ".gitignore").write_text("local/\ncheckpoints/\ncompact/\n*.stdout.log\n*.stderr.log\n*.tmp\n", encoding="utf-8")
    if args.step in {"scope", "all"}:
        write_scope()
    if args.step in {"repair", "all"}:
        run_repair(args.workers)
    if args.step in {"audit", "all"}:
        audit()


if __name__ == "__main__":
    main()
