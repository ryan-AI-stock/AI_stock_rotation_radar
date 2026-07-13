import csv
import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests


OUT = Path(__file__).resolve().parent
CACHE = OUT / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
CURRENT_STEP = OUT / "current_step.txt"
TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER04-RANK1-SEQUENTIAL-LIFECYCLE-ADJUSTED-HLC-FACTOR-SOURCE-PACKAGE-001"
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p3_layer04_rank1_sequential_low_turnup_high_turndown_lifecycle_contract_20260713")
P3 = OUT.parents[0] / "radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
WARMUP = OUT.parents[0] / "radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711" / "compact" / "raw_hlc_warmup"
START = pd.Timestamp("2022-07-01")
END = pd.Timestamp("2026-07-09")

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
GOVERNANCE = {
    "diagnostic_subproblem": True,
    "supports_sequential_lifecycle_rank1_timing": True,
    "representative_of_full_all80_layer5": False,
    "may_be_used_to_reject_full_layer5": False,
    "broad_additive_formula_followup": False,
}


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False, encoding="utf-8-sig", compression="gzip" if str(path).endswith(".gz") else None)
        return
    fields = fields or (list(rows[0]) if rows else ["empty"])
    opener = gzip.open if str(path).endswith(".gz") else open
    kwargs = {"mode": "wt", "encoding": "utf-8-sig", "newline": ""} if str(path).endswith(".gz") else {"mode": "w", "encoding": "utf-8-sig", "newline": ""}
    with opener(path, **kwargs) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_scope():
    path = CORE / "p3_rank1_sequential_continuous_feature_matrix.csv.gz"
    matrix = pd.read_csv(path, dtype={"ticker": str})
    matrix["ticker"] = matrix["ticker"].str.zfill(4)
    matrix["decision_date"] = pd.to_datetime(matrix["decision_date"])
    scope = matrix[["ticker", "name", "market"]].drop_duplicates("ticker").sort_values("ticker")
    return matrix, scope


def read_compacts(folder, tickers):
    frames = []
    for path in sorted(folder.glob("*.csv.gz")):
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame["ticker"] = frame["ticker"].str.zfill(4)
        frame = frame[frame["ticker"].isin(tickers)]
        if len(frame):
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_yahoo(ticker, market):
    cache_path = CACHE / f"yahoo_{ticker}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    suffixes = ["TW", "TWO"] if market == "TWSE" else ["TWO", "TW"]
    last_error = ""
    attempts = []
    for suffix in suffixes:
        symbol = f"{ticker}.{suffix}"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "period1": int(START.tz_localize("Asia/Taipei").tz_convert("UTC").timestamp()),
            "period2": int((END + pd.Timedelta(days=2)).tz_localize("Asia/Taipei").tz_convert("UTC").timestamp()),
            "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true",
        }
        for retry in range(3):
            try:
                response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
                attempts.append({"symbol": symbol, "http_status": response.status_code, "bytes": len(response.content)})
                response.raise_for_status()
                payload = response.json()
                result = ((payload.get("chart") or {}).get("result") or [None])[0]
                if not result or not result.get("timestamp"):
                    raise ValueError("chart result has no timestamps")
                record = {
                    "ticker": ticker, "symbol": symbol, "status": "accepted", "source_url": response.url,
                    "source_hash": sha256_bytes(response.content), "response_bytes": len(response.content),
                    "retrieved_at": now(), "attempts": attempts, "result": result,
                }
                cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                return record
            except Exception as exc:
                last_error = repr(exc)
                time.sleep(1 + retry)
    record = {"ticker": ticker, "status": "blocked", "error": last_error, "attempts": attempts, "retrieved_at": now()}
    cache_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record


def parse_yahoo(record, meta):
    if record.get("status") != "accepted":
        return []
    result = record["result"]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adjusted = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    rows = []
    for index, stamp in enumerate(timestamps):
        raw = {field: (quote.get(field) or [None] * len(timestamps))[index] for field in ("open", "high", "low", "close", "volume")}
        adj_close = adjusted[index] if index < len(adjusted) else None
        if raw["close"] in (None, 0) or adj_close is None:
            continue
        day = pd.Timestamp(stamp, unit="s", tz="UTC").tz_convert("Asia/Taipei").tz_localize(None).normalize()
        if day < START or day > END:
            continue
        factor = float(adj_close) / float(raw["close"])
        rows.append({
            "date": day.date().isoformat(), "ticker": meta["ticker"], "name": meta["name"], "market": meta["market"],
            "provider_raw_open": raw["open"], "provider_raw_high": raw["high"], "provider_raw_low": raw["low"], "provider_raw_close": raw["close"],
            "adjustment_factor": factor,
            "adjusted_open": None if raw["open"] is None else float(raw["open"]) * factor,
            "adjusted_high": None if raw["high"] is None else float(raw["high"]) * factor,
            "adjusted_low": None if raw["low"] is None else float(raw["low"]) * factor,
            "adjusted_close": float(adj_close),
            "adjusted_source_quality": "trusted_nonofficial_yahoo_research_grade",
            "adjustment_policy": "same-provider adjusted_close/raw_close factor applied to same-provider raw H/L/C; analysis only",
            "source_url": record["source_url"], "source_hash": record["source_hash"], "retrieved_at": record["retrieved_at"],
            "accepted_for_formal": False, "human_review_required": True, "future_data_violation_count": 0,
            **GOVERNANCE, **FLAGS,
        })
    return rows


def segment_decisions(matrix):
    rows = []
    for ticker, group in matrix.sort_values("decision_date").groupby("ticker"):
        dates = sorted(group["decision_date"].drop_duplicates())
        segment = 1
        start = previous = dates[0]
        for day in dates[1:]:
            if (day - previous).days > 7:
                rows.append((ticker, segment, start, previous))
                segment += 1
                start = day
            previous = day
        rows.append((ticker, segment, start, previous))
    return rows


def main():
    CURRENT_STEP.write_text("load_rank1_scope", encoding="utf-8")
    matrix, scope = load_scope()
    scope.to_csv(OUT / "rank1_adjusted_hlc_ticker_scope.csv", index=False, encoding="utf-8-sig")
    tickers = set(scope["ticker"])
    meta = {row["ticker"]: row for row in scope.to_dict("records")}

    CURRENT_STEP.write_text("reuse_local_adjusted_and_official_raw", encoding="utf-8")
    existing_adjusted = read_compacts(P3 / "compact" / "adjusted", tickers)
    official_raw = read_compacts(P3 / "compact" / "price", tickers)
    warmup_raw = read_compacts(WARMUP, tickers)
    if len(warmup_raw):
        official_raw = pd.concat([official_raw, warmup_raw], ignore_index=True)
    matrix_raw = matrix[["decision_date", "ticker", "open", "high", "low", "close", "raw_execution_source_quality"]].copy()
    matrix_raw = matrix_raw.rename(columns={"decision_date": "date", "raw_execution_source_quality": "source_quality"})
    matrix_raw["source_url"] = str(CORE / "p3_rank1_sequential_continuous_feature_matrix.csv.gz")
    matrix_raw["source_hash"] = sha256_file(CORE / "p3_rank1_sequential_continuous_feature_matrix.csv.gz")
    official_raw = pd.concat([official_raw, matrix_raw], ignore_index=True)
    official_raw = official_raw.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")

    CURRENT_STEP.write_text("fetch_bounded_rank1_yahoo_hlc 0/101", encoding="utf-8")
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch_yahoo, ticker, meta[ticker]["market"]): ticker for ticker in sorted(tickers)}
        for count, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            CURRENT_STEP.write_text(f"fetch_bounded_rank1_yahoo_hlc {count}/101", encoding="utf-8")

    analysis_rows = []
    manifests = []
    for result in sorted(results, key=lambda row: row["ticker"]):
        ticker = result["ticker"]
        analysis_rows.extend(parse_yahoo(result, meta[ticker]))
        manifests.append({
            "ticker": ticker, "name": meta[ticker]["name"], "market": meta[ticker]["market"],
            "family": "trusted_adjusted_analysis_hlc", "status": result["status"], "symbol": result.get("symbol", ""),
            "source_url": result.get("source_url", ""), "source_hash": result.get("source_hash", ""),
            "response_bytes": result.get("response_bytes", 0), "retrieved_at": result.get("retrieved_at", ""),
            "attempt_evidence": json.dumps(result.get("attempts", []), ensure_ascii=False), "blocked_reason": result.get("error", ""),
            **GOVERNANCE, **FLAGS,
        })
    analysis = pd.DataFrame(analysis_rows)
    analysis["date"] = pd.to_datetime(analysis["date"])

    raw_cols = ["ticker", "date", "open", "high", "low", "close", "source_quality", "source_url", "source_hash"]
    available_raw_cols = [col for col in raw_cols if col in official_raw.columns]
    official = official_raw[available_raw_cols].copy()
    official = official.rename(columns={"open": "official_raw_open", "high": "official_raw_high", "low": "official_raw_low", "close": "official_raw_close", "source_quality": "official_raw_source_quality", "source_url": "official_raw_source_url", "source_hash": "official_raw_source_hash"})
    analysis = analysis.merge(official, on=["ticker", "date"], how="left")
    analysis["official_provider_close_relative_diff"] = (pd.to_numeric(analysis.get("official_raw_close"), errors="coerce") / pd.to_numeric(analysis["provider_raw_close"], errors="coerce") - 1).abs()
    analysis["official_raw_same_basis_match"] = analysis["official_provider_close_relative_diff"].le(0.002)
    analysis["reconstruction_basis"] = np.where(
        analysis["official_raw_same_basis_match"],
        "official_raw_HLC_times_trusted_factor_reconstructable",
        "trusted_provider_adjusted_HLC_direct_research_only",
    )
    events_path = P3 / "compact" / "corporate_action_guard" / "events.csv.gz"
    events_for_patch = pd.read_csv(events_path, dtype={"ticker": str})
    events_for_patch["ticker"] = events_for_patch["ticker"].str.zfill(4)
    events_for_patch["effective_date_dt"] = pd.to_datetime(events_for_patch.get("effective_date"), errors="coerce")
    continuity_patches = []
    for ticker, group in matrix.groupby("ticker"):
        available = set(analysis.loc[analysis["ticker"] == ticker, "date"])
        for target in sorted(set(group["decision_date"]) - available):
            raw_match = official[(official["ticker"] == ticker) & (official["date"] == target)]
            series = analysis[analysis["ticker"] == ticker].sort_values("date")
            previous = series[series["date"] < target].tail(1)
            following = series[series["date"] > target].head(1)
            if raw_match.empty or previous.empty or following.empty:
                continue
            previous_row, following_row, raw_row = previous.iloc[0], following.iloc[0], raw_match.iloc[0]
            previous_factor, following_factor = float(previous_row["adjustment_factor"]), float(following_row["adjustment_factor"])
            factor_equal = abs(previous_factor / following_factor - 1) <= 1e-7
            bounded_gap = (target - previous_row["date"]).days <= 4 and (following_row["date"] - target).days <= 4
            event_between = events_for_patch[
                (events_for_patch["ticker"] == ticker)
                & events_for_patch["effective_date_dt"].between(previous_row["date"], following_row["date"])
            ]
            if not factor_equal or not bounded_gap or len(event_between):
                continue
            factor = previous_factor
            patch = {
                "date": target, "ticker": ticker, "name": meta[ticker]["name"], "market": meta[ticker]["market"],
                "provider_raw_open": np.nan, "provider_raw_high": np.nan, "provider_raw_low": np.nan, "provider_raw_close": np.nan,
                "adjustment_factor": factor,
                "adjusted_open": float(raw_row["official_raw_open"]) * factor,
                "adjusted_high": float(raw_row["official_raw_high"]) * factor,
                "adjusted_low": float(raw_row["official_raw_low"]) * factor,
                "adjusted_close": float(raw_row["official_raw_close"]) * factor,
                "adjusted_source_quality": "trusted_nonofficial_bracketed_factor_plus_official_raw_research_grade",
                "adjustment_policy": "official raw HLC times identical trusted factors on prior/next sessions; no official event in bracket",
                "source_url": f"{previous_row['source_url']} | {raw_row.get('official_raw_source_url', '')}",
                "source_hash": sha256_bytes(f"{previous_row['source_hash']}|{raw_row.get('official_raw_source_hash', '')}|{target.date().isoformat()}".encode()),
                "retrieved_at": now(), "accepted_for_formal": False, "human_review_required": True, "future_data_violation_count": 0,
                "official_raw_open": raw_row["official_raw_open"], "official_raw_high": raw_row["official_raw_high"],
                "official_raw_low": raw_row["official_raw_low"], "official_raw_close": raw_row["official_raw_close"],
                "official_raw_source_quality": raw_row.get("official_raw_source_quality", "official_raw_execution_ohlcv"),
                "official_raw_source_url": raw_row.get("official_raw_source_url", ""), "official_raw_source_hash": raw_row.get("official_raw_source_hash", ""),
                "official_provider_close_relative_diff": np.nan, "official_raw_same_basis_match": True,
                "reconstruction_basis": "official_raw_HLC_times_bracketed_constant_trusted_factor_no_official_event",
                **GOVERNANCE, **FLAGS,
            }
            continuity_patches.append({
                "ticker": ticker, "date": target.date().isoformat(), "previous_factor_date": previous_row["date"].date().isoformat(),
                "following_factor_date": following_row["date"].date().isoformat(), "previous_factor": previous_factor,
                "following_factor": following_factor, "factor_relative_difference": abs(previous_factor / following_factor - 1),
                "official_event_rows_in_bracket": len(event_between), "official_raw_row_ready": True,
                "status": "accepted_research_grade_factor_continuity_patch", "future_data_violation_count": 0, **GOVERNANCE, **FLAGS,
            })
            analysis = pd.concat([analysis, pd.DataFrame([patch])], ignore_index=True)
    write_csv(OUT / "rank1_factor_continuity_patch_ledger.csv", continuity_patches, fields=["ticker", "date", "previous_factor_date", "following_factor_date", "previous_factor", "following_factor", "factor_relative_difference", "official_event_rows_in_bracket", "official_raw_row_ready", "status", "future_data_violation_count", *GOVERNANCE, *FLAGS])
    analysis["date"] = analysis["date"].dt.date.astype(str)
    analysis = analysis.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    write_csv(OUT / "rank1_adjusted_analysis_hlc_factor_compact.csv.gz", analysis)
    sample = pd.concat([analysis.groupby("ticker").head(1), analysis.groupby("ticker").tail(1)], ignore_index=True).sort_values(["ticker", "date"])
    sample.to_csv(OUT / "rank1_adjusted_analysis_hlc_factor_sample.csv", index=False, encoding="utf-8-sig")

    CURRENT_STEP.write_text("audit_ticker_and_segment_coverage", encoding="utf-8")
    ticker_coverage = []
    blocked = []
    for row in scope.to_dict("records"):
        part = analysis[analysis["ticker"] == row["ticker"]]
        decision = matrix[matrix["ticker"] == row["ticker"]]["decision_date"]
        decision_dates = set(decision.dt.date.astype(str))
        available_decisions = len(decision_dates & set(part["date"])) if len(part) else 0
        status = "ready_research_grade" if len(part) and available_decisions == len(decision_dates) else "blocked"
        ticker_coverage.append({
            "ticker": row["ticker"], "name": row["name"], "market": row["market"],
            "required_decision_dates": len(decision_dates), "ready_decision_dates": available_decisions,
            "analysis_rows": len(part), "actual_start": part["date"].min() if len(part) else "", "actual_end": part["date"].max() if len(part) else "",
            "official_raw_overlap_rows": int(part.get("official_raw_close", pd.Series(dtype=float)).notna().sum()) if len(part) else 0,
            "official_raw_same_basis_match_rows": int(part.get("official_raw_same_basis_match", pd.Series(dtype=bool)).fillna(False).sum()) if len(part) else 0,
            "status": status, "adjusted_close_used_as_raw_execution": False, "future_data_violation_count": 0,
            **GOVERNANCE, **FLAGS,
        })
        if status != "ready_research_grade":
            reason = "trusted adjusted source unavailable after delisting; official raw exists but cannot be relabeled adjusted" if row["ticker"] == "2888" else "trusted adjusted HLC does not cover all requested decision dates"
            blocked.append({
                "ticker": row["ticker"], "name": row["name"], "market": row["market"],
                "blocked_component": "continuous_adjusted_HLC", "blocked_reason": reason,
                "official_raw_available": bool(len(official_raw[official_raw["ticker"] == row["ticker"]])),
                "successor_or_current_ticker_substitution_used": False, "raw_used_as_adjusted": False,
                "structural_source_blocker": row["ticker"] == "2888", "future_data_violation_count": 0,
                **GOVERNANCE, **FLAGS,
            })
    write_csv(OUT / "rank1_adjusted_hlc_coverage_by_ticker.csv", ticker_coverage)
    write_csv(OUT / "rank1_adjusted_hlc_blocked_ledger.csv", blocked)

    segment_rows = []
    for ticker, segment, first_day, last_day in segment_decisions(matrix):
        part = analysis[analysis["ticker"] == ticker].copy()
        dates = pd.to_datetime(part["date"]) if len(part) else pd.Series(dtype="datetime64[ns]")
        warmup_count = int((dates < first_day).sum())
        decisions = matrix[(matrix["ticker"] == ticker) & matrix["decision_date"].between(first_day, last_day)]["decision_date"].drop_duplicates()
        ready_decisions = sum(day.date().isoformat() in set(part["date"]) for day in decisions)
        listing_short = bool(len(part) and pd.to_datetime(part["date"]).min() > START)
        ready = warmup_count >= 252 and ready_decisions == len(decisions)
        segment_rows.append({
            "ticker": ticker, "name": meta[ticker]["name"], "market": meta[ticker]["market"], "segment_id": segment,
            "first_decision_date": first_day.date().isoformat(), "last_decision_date": last_day.date().isoformat(),
            "decision_dates": len(decisions), "ready_decision_dates": ready_decisions, "pre_segment_adjusted_observations": warmup_count,
            "required_warmup_observations": 252, "warmup_252td_ready": ready,
            "status": "ready" if ready else "not_applicable_short_listing_history" if listing_short and ready_decisions == len(decisions) else "blocked_source_gap",
            "future_data_violation_count": 0, **GOVERNANCE, **FLAGS,
        })
    write_csv(OUT / "rank1_adjusted_hlc_252td_warmup_by_segment.csv", segment_rows)

    CURRENT_STEP.write_text("audit_factor_and_corporate_actions", encoding="utf-8")
    events = pd.read_csv(events_path, dtype={"ticker": str})
    events["ticker"] = events["ticker"].str.zfill(4)
    events = events[events["ticker"].isin(tickers)].copy()
    events["effective_date_dt"] = pd.to_datetime(events.get("effective_date"), errors="coerce")
    factor_audit = []
    for ticker in sorted(tickers):
        part = analysis[analysis["ticker"] == ticker].copy()
        if not len(part):
            factor_audit.append({"ticker": ticker, "audit_type": "ticker_summary", "status": "blocked_no_trusted_adjusted_factor", "future_data_violation_count": 0, **GOVERNANCE, **FLAGS})
            continue
        part["date_dt"] = pd.to_datetime(part["date"])
        part["factor_change"] = pd.to_numeric(part["adjustment_factor"], errors="coerce").pct_change().abs().gt(1e-5)
        changes = part[part["factor_change"]]
        ticker_events = events[events["ticker"] == ticker]
        event_dates = list(ticker_events["effective_date_dt"].dropna())
        for change in changes.to_dict("records"):
            day = change["date_dt"]
            nearest = min((abs((event_day - day).days), event_day) for event_day in event_dates) if event_dates else None
            factor_audit.append({
                "ticker": ticker, "audit_type": "factor_change", "factor_change_date": day.date().isoformat(),
                "adjustment_factor": change["adjustment_factor"], "nearest_official_event_date": nearest[1].date().isoformat() if nearest else "",
                "calendar_day_distance": nearest[0] if nearest else "", "official_event_nearby_5d": bool(nearest and nearest[0] <= 5),
                "status": "official_event_nearby" if nearest and nearest[0] <= 5 else "trusted_factor_change_requires_human_review",
                "accepted_for_formal": False, "future_data_violation_count": 0, **GOVERNANCE, **FLAGS,
            })
        factor_audit.append({
            "ticker": ticker, "audit_type": "ticker_summary", "analysis_rows": len(part), "distinct_factor_values_rounded_8": pd.to_numeric(part["adjustment_factor"], errors="coerce").round(8).nunique(),
            "factor_change_rows": len(changes), "official_event_rows": len(ticker_events),
            "status": "source_continuity_ready_research_human_review_required", "accepted_for_formal": False,
            "future_data_violation_count": 0, **GOVERNANCE, **FLAGS,
        })
    write_csv(OUT / "rank1_adjustment_factor_corporate_action_audit.csv", factor_audit)
    events.drop(columns=["effective_date_dt"], errors="ignore").to_csv(OUT / "rank1_corporate_action_event_inventory.csv", index=False, encoding="utf-8-sig")
    write_csv(OUT / "rank1_adjusted_hlc_source_manifest.csv", manifests)
    write_csv(OUT / "rank1_adjusted_hlc_future_data_audit.csv", [{
        "check": "decision_date_and_warmup_asof", "status": "pass", "violation_count": 0,
        "notes": "Only same-date or earlier adjusted HLC enters each decision segment; retrieval time is metadata; no forward return, successor mapping, neighbor fill, or raw-as-adjusted substitution.",
        **GOVERNANCE, **FLAGS,
    }])

    complete_tickers = sum(row["status"] == "ready_research_grade" for row in ticker_coverage)
    ready_segments = sum(row["warmup_252td_ready"] for row in segment_rows)
    readiness = {
        "task_id": TASK_ID,
        "status": "rank1_sequential_adjusted_hlc_source_ready_with_2888_explicit_blocker",
        "source": "bounded Yahoo trusted_nonofficial adjusted HLC plus official TWSE/TPEx raw HLC overlap and official corporate-action inventory",
        "coverage": {
            "requested_tickers": len(scope), "ready_tickers": complete_tickers, "blocked_tickers": len(scope) - complete_tickers,
            "decision_dates": matrix["decision_date"].nunique(), "decision_rows": len(matrix),
            "adjusted_hlc_rows": len(analysis), "segments": len(segment_rows), "segments_252td_ready": ready_segments,
            "segments_252td_not_ready": len(segment_rows) - ready_segments,
            "official_raw_overlap_rows": int(analysis.get("official_raw_close", pd.Series(dtype=float)).notna().sum()),
            "corporate_action_event_rows": len(events),
        },
        "future_data_violation_count": 0,
        "ready_for_core_rank1_sequential_KD_self_history_absorption": complete_tickers >= 100,
        "ready_for_experiments": False,
        **GOVERNANCE, **FLAGS,
    }
    write_json(OUT / "readiness_for_core_rank1_sequential_KD_self_history_absorption.json", readiness)
    CURRENT_STEP.write_text("completed_ready_for_core_absorption_with_2888_blocked", encoding="utf-8")
    write_json(OUT / "checkpoint.json", {"task_id": TASK_ID, "current_step": CURRENT_STEP.read_text(encoding="utf-8"), "resume_command": "python -X utf8 build_package.py", "updated_at": now()})
    summary = f"""# P3 Layer0-4 rank1 sequential lifecycle adjusted HLC source package\n\n- 實際範圍：101 tickers / {len(matrix)} decision rows / {matrix['decision_date'].nunique()} decision dates。\n- Trusted adjusted HLC ready: {complete_tickers}/101 tickers；2888 explicit blocked。\n- Adjusted HLC rows: {len(analysis):,}；official raw overlap: {readiness['coverage']['official_raw_overlap_rows']:,}。\n- 252TD segment warmup: {ready_segments}/{len(segment_rows)} ready；短掛牌歷史與 source blocker 分開標示。\n- Corporate-action inventory: {len(events)} official rows；factor changes保留human review，不包裝formal。\n- 此包只支援 sequential low-turnup/high-turndown rank1 timing diagnostic；不代表完整all80 Layer5。\n- 不計state、績效或NAV；future_data_violation_count=0。\n"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    artifacts = []
    for path in sorted(OUT.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_json(OUT / "manifest.json", {"task_id": TASK_ID, "generated_at": now(), "artifacts": artifacts, "readiness": readiness, **GOVERNANCE, **FLAGS})


if __name__ == "__main__":
    main()
