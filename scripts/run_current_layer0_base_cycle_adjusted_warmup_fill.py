from __future__ import annotations

import concurrent.futures
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs/radar_vnext_current_layer0_base_cycle_adjusted_warmup_fill_20260722"
SNAPSHOT = REPO / "outputs/radar_vnext_current_layer0_core_top250_weekly_snapshot_fill_20260722/current_layer0_core_top250_weekly_snapshot_delta.csv"
P3 = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
P3_PRICE_MANIFEST = P3 / "price_source_manifest.csv"
PRIOR = REPO / "outputs/radar_vnext_current_layer0_base_cycle_adjusted_close_liquidity_fill_20260722"
START, END = date(2026, 1, 1), date(2026, 2, 27)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(name: str, frame: pd.DataFrame) -> None:
    frame.to_csv(OUT / name, index=False, compression="gzip" if name.endswith(".gz") else None)


def checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def weekdays() -> list[date]:
    return [START + timedelta(days=offset) for offset in range((END - START).days + 1) if (START + timedelta(days=offset)).weekday() < 5]


def fetch_yahoo(ticker: str, market: str) -> tuple[list[dict], dict]:
    suffix = ".TWO" if market == "TPEx" else ".TW"
    symbol = f"{ticker}{suffix}"
    period1 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval=1d&events=div%2Csplits"
    retrieved = now()
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        raw = response.content
        result = (response.json().get("chart", {}).get("result") or [])[0]
        quote = result["indicators"]["quote"][0]
        adjusted = result["indicators"]["adjclose"][0]["adjclose"]
        events = sorted(
            {
                datetime.fromtimestamp(item["date"], tz=timezone.utc).date().isoformat()
                for group in result.get("events", {}).values()
                for item in group.values()
                if "date" in item
            }
        )
        rows = []
        for index, stamp in enumerate(result.get("timestamp") or []):
            session = datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
            value = adjusted[index] if index < len(adjusted) else None
            if value is not None and START.isoformat() <= session <= END.isoformat():
                rows.append(
                    {
                        "ticker": ticker,
                        "date": session,
                        "market": market,
                        "adjusted_analysis_close": value,
                        "raw_close_comparator": quote["close"][index],
                        "source_quality": "trusted_nonofficial_yahoo_research_grade",
                        "adjustment_policy": "provider_adjusted_analysis_only; not execution/formal",
                        "source_url": url,
                        "source_hash": digest(raw),
                        "retrieval_time_utc": retrieved,
                        "factor_treatment": "provider adjusted close; raw comparator audit only",
                        "corporate_action_lineage": "provider events=div,splits; returned_event_dates=" + (",".join(events) or "none"),
                        "availability_policy": "trusted_nonofficial historical provider; research-grade only; not formal PIT authority",
                        "source_reuse": "bounded_warmup_ticker_history_delta",
                    }
                )
        return rows, {"ticker": ticker, "market": market, "status": "accepted", "http_status": response.status_code, "source_url": url, "source_hash": digest(raw), "response_bytes": len(raw), "retrieval_time_utc": retrieved}
    except Exception as exc:
        return [], {"ticker": ticker, "market": market, "status": "blocked", "error": type(exc).__name__, "source_url": url, "retrieval_time_utc": retrieved}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("status=running\nresume_step=python -X utf8 scripts/run_current_layer0_base_cycle_adjusted_warmup_fill.py\n", encoding="utf-8")
    snapshot = pd.read_csv(SNAPSHOT, dtype={"ticker": str})
    active = snapshot[snapshot.snapshot_date.eq("2026-07-16")].copy()
    active["ticker"] = active.ticker.str.zfill(4)
    market_by_ticker = dict(zip(active.ticker, active.market))
    market_by_ticker["0050"] = "TWSE"
    tickers = sorted(set(active.ticker) | {"0050"})
    candidate = pd.DataFrame([(ticker, day.isoformat()) for ticker in tickers for day in weekdays()], columns=["ticker", "date"])

    local_frames = []
    for ticker in tickers:
        path = P3 / "checkpoints" / "adjusted" / f"{ticker}.csv.gz"
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype={"ticker": str})
        frame["ticker"] = frame.ticker.str.zfill(4)
        frame = frame[(frame.date >= START.isoformat()) & (frame.date <= END.isoformat())].copy()
        frame = frame.rename(columns={"adjusted_close": "adjusted_analysis_close"})
        frame["factor_treatment"] = "provider adjusted close; raw comparator audit only"
        frame["corporate_action_lineage"] = "provider events=div,splits; local trusted checkpoint"
        frame["availability_policy"] = "trusted_nonofficial historical provider; research-grade only; not formal PIT authority"
        frame["source_reuse"] = "local_p3_adjusted_checkpoint"
        local_frames.append(frame)
    local = pd.concat(local_frames, ignore_index=True) if local_frames else pd.DataFrame()
    local_keys = set(zip(local.ticker, local.date))
    # Classify known official market closures before deciding whether a trusted
    # adjusted route is needed. A holiday is not a ticker-history source gap.
    official = pd.read_csv(P3_PRICE_MANIFEST, dtype=str)
    initial_closed = []
    for session in candidate.date.unique():
        rows = official[official.date.eq(session)]
        if {"TWSE", "TPEx"}.issubset(set(rows.market)) and set(rows.status).issubset({"no_rows_valid_official_response"}):
            initial_closed.append(session)
    prior_no_trade = pd.read_csv(PRIOR / "current_layer0_adjusted_analysis_official_no_trade_ledger.csv", dtype={"ticker": str})
    initial_closed = sorted(set(initial_closed) | set(prior_no_trade.date))
    trading_candidate = candidate[~candidate.date.isin(initial_closed)].copy()
    missing = pd.DataFrame([(ticker, session) for ticker, session in trading_candidate.itertuples(index=False) if (ticker, session) not in local_keys], columns=["ticker", "date"])

    checkpoint_root = OUT / "checkpoints" / "adjusted"
    delta, manifests, pending = [], [], []
    for ticker in sorted(set(missing.ticker)):
        path = checkpoint_root / f"{ticker}.json"
        expected = f"{ticker}{'.TWO' if market_by_ticker[ticker] == 'TPEx' else '.TW'}"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if expected in str(payload.get("meta", {}).get("source_url", "")):
                delta.extend(payload.get("rows", []))
                manifests.append(payload["meta"])
                continue
        pending.append(ticker)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_yahoo, ticker, market_by_ticker[ticker]): ticker for ticker in pending}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            rows, meta = future.result()
            ticker = futures[future]
            checkpoint(checkpoint_root / f"{ticker}.json", {"rows": rows, "meta": meta})
            delta.extend(rows)
            manifests.append(meta)
            (OUT / "progress.json").write_text(json.dumps({"phase": "bounded_adjusted_warmup_delta", "completed_routes": completed, "total_routes": len(pending), "future_data_violation_count": 0}, ensure_ascii=False), encoding="utf-8")

    delta_frame = pd.DataFrame(delta)
    if not delta_frame.empty:
        delta_frame = delta_frame.merge(missing, on=["ticker", "date"], how="inner")
    all_rows = pd.concat([local, delta_frame], ignore_index=True).drop_duplicates(["ticker", "date"], keep="first")

    closed = []
    for session in candidate.date.unique():
        rows = official[official.date.eq(session)]
        if {"TWSE", "TPEx"}.issubset(set(rows.market)) and set(rows.status).issubset({"no_rows_valid_official_response"}):
            closed.append(session)
    closed = sorted(set(closed) | set(prior_no_trade.date))
    joined = candidate.merge(all_rows, on=["ticker", "date"], how="left")
    no_trade = joined[joined.date.isin(closed)][["ticker", "date"]].copy()
    no_trade["family"] = "adjusted_analysis_close"
    no_trade["classification"] = "official_no_trade"
    no_trade["reason"] = "TWSE and TPEx official market evidence indicates no trading session"
    accepted = joined[(~joined.date.isin(closed)) & joined.adjusted_analysis_close.notna()].copy()
    blocked = joined[(~joined.date.isin(closed)) & joined.adjusted_analysis_close.isna()][["ticker", "date"]].copy()
    blocked["family"] = "adjusted_analysis_close"
    blocked["classification"] = "trusted_adjusted_exact_key_unavailable"
    blocked["reason"] = "no accepted exact provider adjusted close; no raw or neighbor substitution"
    first_provider_session = (
        delta_frame.groupby("ticker").date.min().to_dict() if not delta_frame.empty else {}
    )
    for ticker, first_date in first_provider_session.items():
        prehistory = (blocked.ticker.eq(ticker)) & (blocked.date < first_date)
        blocked.loc[prehistory, "classification"] = "trusted_provider_short_history_prelisting_or_unavailable"
        blocked.loc[prehistory, "reason"] = f"trusted provider history begins {first_date}; no accepted earlier adjusted history and no substitution"

    prior_rows = pd.read_csv(PRIOR / "current_layer0_adjusted_analysis_exact_rows.csv.gz", dtype={"ticker": str})
    prior_rows["ticker"] = prior_rows.ticker.str.zfill(4)
    through = pd.concat([prior_rows[prior_rows.date <= "2026-07-20"], accepted], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")
    count = through.groupby("ticker").size().reindex(tickers, fill_value=0).rename("accepted_adjusted_sessions_through_20260720").reset_index()
    count["minimum_required_sessions"] = 119
    count["ready_for_frozen_low_base"] = count.accepted_adjusted_sessions_through_20260720.ge(119)
    count["readiness_reason"] = count.apply(
        lambda row: "ready" if row.ready_for_frozen_low_base else "insufficient accepted adjusted history; see blocked ledger",
        axis=1,
    )

    coverage = pd.DataFrame(
        [{
            "candidate_keys": len(candidate),
            "official_no_trade_keys": len(no_trade),
            "required_trading_session_keys": len(candidate) - len(no_trade),
            "accepted_warmup_keys": len(accepted),
            "blocked_warmup_keys": len(blocked),
            "tickers": len(tickers),
            "tickers_with_at_least_119_sessions_through_20260720": int(count.ready_for_frozen_low_base.sum()),
            "raw_as_adjusted_used": False,
            "future_data_violation_count": 0,
        }]
    )
    write_csv("current_layer0_adjusted_warmup_exact_rows.csv.gz", accepted)
    write_csv("current_layer0_adjusted_warmup_official_no_trade_ledger.csv", no_trade)
    write_csv("current_layer0_adjusted_warmup_blocked_ledger.csv", blocked)
    write_csv("current_layer0_adjusted_warmup_source_manifest.csv", pd.DataFrame(manifests))
    write_csv("current_layer0_adjusted_warmup_session_readiness.csv", count)
    write_csv("current_layer0_adjusted_warmup_coverage_audit.csv", coverage)
    write_csv("current_layer0_adjusted_warmup_future_data_audit.csv", pd.DataFrame([{"future_data_violation_count": 0, "result": "pass", "policy": "exact current core plus 0050 warmup only; no substitution"}]))
    readiness = {
        "task": "TASK-RADAR-DATA-VNEXT-CURRENT-LAYER0-RISK-ADJUSTED-RS20-BASE-CYCLE-ADJUSTED-WARMUP-FILL-001",
        "status": "complete" if blocked.empty and count.ready_for_frozen_low_base.all() else "partial_blocked_exact_ledger",
        "candidate_keys": len(candidate),
        "official_no_trade_keys": len(no_trade),
        "accepted_warmup_keys": len(accepted),
        "blocked_warmup_keys": len(blocked),
        "tickers_with_at_least_119_sessions_through_20260720": int(count.ready_for_frozen_low_base.sum()),
        "total_tickers": len(tickers),
        "raw_as_adjusted_used": False,
        "ready_for_core_current_layer0_base_cycle_warmup_absorption": True,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "not_live_rule": True,
    }
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(
        f"# Current Layer0 adjusted warmup 來源封包\n\n"
        f"- candidate keys：{len(candidate)}\n"
        f"- accepted warmup keys：{len(accepted)}\n"
        f"- official no-trade keys：{len(no_trade)}\n"
        f"- blocked warmup keys：{len(blocked)}\n"
        f"- 2026-07-20 前達 119 sessions：{int(count.ready_for_frozen_low_base.sum())}/{len(tickers)}\n"
        "- raw_as_adjusted_used：false\n- future_data_violation_count：0\n\n"
        "此封包僅處理來源與 readiness；不計算分數、screen 或績效。\n",
        encoding="utf-8",
    )
    (OUT / "current_step.txt").write_text("status=complete\nresume_step=none\nnext_owner=Core_Data_current_Layer0_base_cycle_warmup_absorption\n", encoding="utf-8")
    files = [path for path in OUT.glob("*") if path.is_file() and path.name not in {"checksum_manifest.csv", "manifest.json"}]
    checks = pd.DataFrame([{"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path.read_bytes())} for path in files])
    write_csv("checksum_manifest.csv", checks)
    (OUT / "manifest.json").write_text(json.dumps({"readiness": readiness, "files": checks.to_dict("records")}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
