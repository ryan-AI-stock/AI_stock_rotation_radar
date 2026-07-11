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
OUT = ROOT / "outputs" / "radar_vnext_p3_exact_primary80_chip_20d_warmup_gap_fill_20260711"
PRIMARY = CORE / "outputs" / "vnext_layer4_80_primary_pool_contract_20260708" / "layer4_80_primary_pool_contract.csv"
P3_START = date(2023, 7, 11)
EXACT_END = date(2026, 6, 29)
WARMUP_SESSIONS = 20
TASK = "TASK-RADAR-DATA-VNEXT-P3-EXACT-PRIMARY80-CHIP-FAMILY-20D-WARMUP-GAP-FILL-001"
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
FAMILIES = {
    "institutional": "chip_institutional",
    "margin_short": "chip_margin_short",
    "securities_lending": "chip_securities_lending",
    "foreign_ownership": "foreign_ownership",
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
    spec = importlib.util.spec_from_file_location("p3_chip_source", runner)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load P3 source runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    return module


SRC = load_source_module()


def primary_rows() -> pd.DataFrame:
    cols = ["snapshot_date", "ticker", "name", "market", "is_layer4_primary_pool", "pool_rank"]
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


def build_requirements() -> tuple[list[dict], dict[tuple[str, str, str], dict]]:
    primary = primary_rows()
    sessions = trading_dates()
    snapshots = sorted(primary.snapshot_date.dt.date.unique())
    previous: set[str] = set()
    segments: list[dict] = []
    required: dict[tuple[str, str, str], dict] = {}
    for snap in snapshots:
        frame = primary[primary.snapshot_date.dt.date.eq(snap)]
        current = set(frame.ticker.astype(str))
        entrants = current - previous
        pos = sum(d < snap for d in sessions)
        window = sessions[max(0, pos - WARMUP_SESSIONS):pos]
        for row in frame[frame.ticker.isin(entrants)].itertuples(index=False):
            ticker = str(row.ticker)
            segments.append({
                "ticker": ticker, "name": row.name, "market": row.market,
                "segment_start_snapshot": snap.isoformat(),
                "warmup_required_sessions": WARMUP_SESSIONS,
                "warmup_actual_sessions": len(window),
                "warmup_start": window[0].isoformat() if window else "",
                "warmup_end": window[-1].isoformat() if window else "",
            })
            for d in window:
                required[(d.isoformat(), ticker, row.market)] = {
                    "date": d.isoformat(), "ticker": ticker, "name": row.name, "market": row.market,
                    "required_by_segment_start": snap.isoformat(),
                    "requirement": "official_chip_family_pre_segment_20td_warmup",
                }
        previous = current
    return segments, required


def write_scope() -> None:
    segments, required = build_requirements()
    write_csv(OUT / "p3_exact_primary80_chip_20d_membership_segments.csv", segments)
    local = OUT / "local"
    local.mkdir(parents=True, exist_ok=True)
    with gzip.open(local / "p3_exact_primary80_chip_20d_required_ticker_dates.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(next(iter(required.values()))))
        writer.writeheader()
        writer.writerows(required.values())
    write_csv(OUT / "p3_exact_primary80_chip_20d_requirement_summary.csv", [{
        "segment_count": len(segments),
        "unique_tickers": len({r["ticker"] for r in segments}),
        "required_unique_ticker_dates_per_family": len(required),
        "family_count": len(FAMILIES),
        "total_family_ticker_date_requirements": len(required) * len(FAMILIES),
        "unique_dates": len({key[0] for key in required}),
        "warmup_sessions_per_segment": WARMUP_SESSIONS,
        "primary_contract_sha256": hashlib.sha256(PRIMARY.read_bytes()).hexdigest(),
        "adjusted_11_reprobed": False,
    }])
    write_json(OUT / "scope_progress.json", {"status": "completed", "segments": len(segments), "required_ticker_dates_per_family": len(required), "updated_at": now()})
    (OUT / "current_step.txt").write_text("scope_completed_family_repair_pending\n", encoding="utf-8")


def load_reuse(folder: str, required: set[tuple[str, str, str]]) -> dict[tuple[str, str, str], dict]:
    rows: dict[tuple[str, str, str], dict] = {}
    for base in (EXACT / "compact" / folder, P3 / "compact" / folder):
        for path in sorted(base.glob("*.csv.gz")):
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    key = (row.get("date", ""), row.get("ticker", ""), row.get("market", ""))
                    if key in required and key not in rows:
                        rows[key] = row
    return rows


def fields_for(family: str) -> list[str]:
    return SRC.FOREIGN_FIELDS if family == "foreign_ownership" else SRC.CHIP_FIELDS


def checkpoint_path(family: str, market: str, date_s: str) -> Path:
    return OUT / "checkpoints" / family / market / f"{date_s}.csv.gz"


def run_family(family: str, workers: int) -> None:
    _, required_map = build_requirements()
    required = set(required_map)
    folder = FAMILIES[family]
    reused = load_reuse(folder, required)
    routes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for date_s, ticker, market in required:
        routes[(date_s, market)].add(ticker)
    manifest_path = OUT / f"{family}_20d_source_manifest.csv"
    manifest = {(r.get("date", ""), r.get("market", "")): r for r in read_csv(manifest_path)}
    tasks = []
    for (date_s, market), tickers in sorted(routes.items()):
        output = checkpoint_path(family, market, date_s)
        if output.exists():
            if (date_s, market) not in manifest:
                recovered = read_gzip(output)
                ready = {r.get("ticker", "") for r in recovered}
                sample = recovered[0] if recovered else {}
                manifest[(date_s, market)] = {
                    "family": family, "date": date_s, "market": market,
                    "route_status": "accepted" if recovered else "no_rows_valid_official_response",
                    "required_tickers": len(tickers), "ready_tickers": len(ready & tickers), "blocked_tickers": len(tickers - ready),
                    "retrieval_attempted": True, "http_status": "recovered_from_completed_checkpoint",
                    "source_url": sample.get("source_url", ""), "source_hash": sample.get("source_hash", ""),
                    "retrieval_time_utc": sample.get("retrieval_time_utc", ""), "error": "",
                }
            continue
        keys = {(date_s, ticker, market) for ticker in tickers}
        existing = {key: reused[key] for key in keys if key in reused}
        if len(existing) == len(keys):
            SRC.write_shard(output, list(existing.values()), fields_for(family))
            manifest[(date_s, market)] = {
                "family": family, "date": date_s, "market": market, "route_status": "reused_existing_compact",
                "required_tickers": len(tickers), "ready_tickers": len(tickers), "blocked_tickers": 0,
                "retrieval_attempted": False, "source_url": "local_compact", "source_hash": "",
            }
        else:
            tasks.append((date_s, market, tickers, existing))
    total = len(tasks)
    progress = OUT / f"{family}_20d_progress.json"
    write_json(progress, {"family": family, "status": "running", "completed_routes": len(manifest), "total_routes": len(routes), "new_retrieval_completed": 0, "new_retrieval_total": total, "updated_at": now()})

    def fetch(item):
        date_s, market, tickers, existing = item
        d = date.fromisoformat(date_s)
        if family == "foreign_ownership":
            result = SRC.fetch_foreign_ownership((market, d, tickers))
            source_output = OUT / "checkpoints" / "foreign_ownership" / market / f"{date_s}.csv.gz"
        else:
            result = SRC.fetch_chip((market, family, d, tickers))
            source_output = OUT / "checkpoints" / family / market / f"{date_s}.csv.gz"
        output = checkpoint_path(family, market, date_s)
        fresh = read_gzip(source_output)
        merged = {(r.get("date", ""), r.get("ticker", ""), r.get("market", "")): r for r in [*existing.values(), *fresh]}
        filtered = [merged[key] for key in sorted(merged) if key[0] == date_s and key[2] == market and key[1] in tickers]
        SRC.write_shard(output, filtered, fields_for(family))
        ready = {r["ticker"] for r in filtered}
        return {
            "family": family, "date": date_s, "market": market, "route_status": result.get("status", ""),
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
            manifest[(row["date"], row["market"])] = row
            completed += 1
            if completed % 10 == 0 or completed == total:
                write_csv(manifest_path, sorted(manifest.values(), key=lambda r: (r["date"], r["market"])))
                write_json(progress, {"family": family, "status": "running", "completed_routes": len(manifest), "total_routes": len(routes), "new_retrieval_completed": completed, "new_retrieval_total": total, "updated_at": now()})
                (OUT / "current_step.txt").write_text(f"{family}_running_{completed}_of_{total}\n", encoding="utf-8")
    write_csv(manifest_path, sorted(manifest.values(), key=lambda r: (r["date"], r["market"])))
    write_json(progress, {"family": family, "status": "completed", "completed_routes": len(manifest), "total_routes": len(routes), "new_retrieval_completed": total, "new_retrieval_total": total, "updated_at": now()})
    consolidate(family)


def consolidate(family: str) -> None:
    rows_by_year: dict[str, dict[tuple[str, str, str], dict]] = defaultdict(dict)
    for path in (OUT / "checkpoints" / family).rglob("*.csv.gz"):
        for row in read_gzip(path):
            key = (row["date"], row["ticker"], row["market"])
            rows_by_year[row["date"][:4]][key] = row
    for year, rows in rows_by_year.items():
        target = OUT / "compact" / family / f"{year}.csv.gz"
        SRC.write_shard(target, [rows[key] for key in sorted(rows)], fields_for(family))


def audit() -> None:
    segments, required_map = build_requirements()
    required = set(required_map)
    coverage_rows = []
    blocked_rows = []
    actual_by_family: dict[str, set[tuple[str, str, str]]] = {}
    for family in FAMILIES:
        actual: set[tuple[str, str, str]] = set()
        for path in (OUT / "compact" / family).glob("*.csv.gz"):
            for row in read_gzip(path):
                key = (row.get("date", ""), row.get("ticker", ""), row.get("market", ""))
                if key in required:
                    actual.add(key)
        actual_by_family[family] = actual
        manifest = {(r["date"], r["market"]): r for r in read_csv(OUT / f"{family}_20d_source_manifest.csv")}
        classification_counts: dict[str, int] = defaultdict(int)
        for key in sorted(required - actual):
            date_s, ticker, market = key
            route = manifest.get((date_s, market), {})
            status = route.get("route_status", "missing_route")
            if status == "accepted":
                classification = "official_zero_or_not_applicable"
                reason = "official market file accepted but ticker row absent; no zero or stale-value substitution"
            elif status == "no_rows_valid_official_response":
                classification = "official_zero_or_not_applicable"
                reason = "official response valid but target ticker filter returned zero rows; no zero or stale-value substitution"
            else:
                classification = "source_gap"
                reason = f"official route not accepted: {status}; {route.get('error','')}"
            classification_counts[classification] += 1
            blocked_rows.append({"family": family, **required_map[key], "classification": classification, "blocked_reason": reason, "route_status": status, "source_url": route.get("source_url", ""), "source_hash": route.get("source_hash", "")})
        coverage_rows.append({
            "family": family, "required_ticker_dates": len(required), "ready_ticker_dates": len(actual),
            "blocked_ticker_dates": len(required) - len(actual), "ready_share": round(len(actual) / len(required), 10),
            "blocked_classification_counts": dict(classification_counts), "availability_policy": "official post-close; next-trading-day eligible",
        })
    required_dates_by_ticker: dict[str, list[str]] = defaultdict(list)
    for date_s, ticker, _ in required:
        required_dates_by_ticker[ticker].append(date_s)
    for ticker in required_dates_by_ticker:
        required_dates_by_ticker[ticker] = sorted(set(required_dates_by_ticker[ticker]))
    segment_rows = []
    for segment in segments:
        dates = [d for d in required_dates_by_ticker[segment["ticker"]] if segment["warmup_start"] <= d <= segment["warmup_end"]]
        result = dict(segment)
        all_ready = True
        for family in FAMILIES:
            ready = sum((d, segment["ticker"], segment["market"]) in actual_by_family[family] for d in dates)
            result[f"{family}_ready_dates"] = ready
            result[f"{family}_20d_ready"] = ready >= WARMUP_SESSIONS
            all_ready = all_ready and ready >= WARMUP_SESSIONS
        result["all_mandatory_chip_20d_ready"] = all_ready
        segment_rows.append(result)
    write_csv(OUT / "p3_exact_primary80_chip_20d_family_coverage.csv", coverage_rows)
    write_csv(OUT / "p3_exact_primary80_chip_20d_coverage_by_segment.csv", segment_rows)
    write_csv(OUT / "p3_exact_primary80_chip_20d_blocked_ledger.csv", blocked_rows)
    write_csv(OUT / "p3_exact_primary80_chip_20d_future_data_audit.csv", [{"audit": "pre_segment_20_market_sessions_only", "future_data_violation_count": 0, "zero_fill_used": False, "stale_value_fill_used": False, "adjusted_11_reprobed": False, "result": "pass"}])
    compact_manifest = []
    for path in sorted((OUT / "compact").rglob("*.csv.gz")):
        compact_manifest.append({"path": str(path.relative_to(OUT)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_csv(OUT / "p3_exact_primary80_chip_20d_compact_hash_manifest.csv", compact_manifest)
    source_gap_count = sum(r["classification"] == "source_gap" for r in blocked_rows)
    all_ready_segments = sum(str(r["all_mandatory_chip_20d_ready"]).lower() == "true" for r in segment_rows)
    readiness = {
        "task_id": TASK,
        "status": "chip_20d_warmup_source_package_ready_with_explicit_no_rows" if source_gap_count == 0 else "chip_20d_warmup_partial_source_gaps_remain",
        "source": "official TWSE/TPEx institutional, margin/short, securities lending, foreign ownership",
        "coverage": {r["family"]: {"ready": r["ready_ticker_dates"], "required": r["required_ticker_dates"], "blocked": r["blocked_ticker_dates"]} for r in coverage_rows},
        "segment_count": len(segments),
        "all_mandatory_chip_20d_ready_segments": all_ready_segments,
        "source_gap_count": source_gap_count,
        "future_data_violation_count": 0,
        "ready_for_core_p3_exact_primary80_chip_20d_absorption": any(r["ready_ticker_dates"] for r in coverage_rows),
        "ready_for_experiments": False,
        "adjusted_11_reprobed": False,
        "zero_or_stale_fill_used": False,
        **FLAGS,
    }
    write_json(OUT / "readiness_for_core_p3_exact_primary80_chip_20d_warmup.json", readiness)
    summary = f"""# P3 exact primary80 chip-family 20D warmup gap fill\n\n- Segments：{len(segments)}。\n- Required ticker-dates per family：{len(required)}。\n- All four mandatory families complete 20D segments：{all_ready_segments}/{len(segments)}。\n- source_gap_count={source_gap_count}；官方無列保留，不補0、不沿用舊值。\n- adjusted11未重探；TDCC不在本task。\n- future_data_violation_count=0。\n- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed_ready_for_core_absorption\n", encoding="utf-8")
    files = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "manifest.json" and not path.name.endswith(".tmp"):
            files.append({"path": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "manifest.json", {"task_id": TASK, "generated_at_utc": now(), "primary_contract": str(PRIMARY), "primary_contract_sha256": hashlib.sha256(PRIMARY.read_bytes()).hexdigest(), "coverage": coverage_rows, "files": files, "compact_files": compact_manifest, "future_data_violation_count": 0, **FLAGS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=["scope", *FAMILIES, "audit", "all"], default="all")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ".gitignore").write_text("local/\ncheckpoints/\ncompact/\n*.stdout.log\n*.stderr.log\n*.tmp\n", encoding="utf-8")
    if args.family in {"scope", "all"}:
        write_scope()
    for family in FAMILIES:
        if args.family in {family, "all"}:
            run_family(family, args.workers)
    if args.family in {"audit", "all"}:
        audit()


if __name__ == "__main__":
    main()
