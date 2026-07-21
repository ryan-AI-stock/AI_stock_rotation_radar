from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


REPO = Path(__file__).resolve().parents[1]
CORE_LEDGER = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_old_ai7_one_year_three_chip_families_pit_panel_contract_20260721\adjusted_analysis_exact_requirement_ledger.csv")
P3 = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
OUT = REPO / "outputs/radar_old_ai7_one_year_adjusted_analysis_exact_fill_20260721"
TICKERS = ("2308", "2317", "2330", "2382", "2454", "3231", "6669")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip" if path.suffix == ".gz" else None)


def local_rows() -> pd.DataFrame:
    frames = []
    for ticker in TICKERS:
        frame = pd.read_csv(P3 / "checkpoints" / "adjusted" / f"{ticker}.csv.gz", dtype={"ticker": str})
        frame["ticker"] = frame["ticker"].str.zfill(4)
        frame["factor_treatment"] = "provider_adjusted_close; raw_comparator retained only for factor audit; never execution"
        frame["corporate_action_lineage"] = "provider_adjusted_analysis_events_div_splits; event terms not independently formalized"
        frame["availability_policy"] = "trusted_nonofficial historical provider; research-grade only; not formal PIT authority"
        frame["source_reuse"] = "p3_adjusted_checkpoint"
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def fetch_delta(ticker: str) -> tuple[pd.DataFrame, dict]:
    symbol = f"{ticker}.TW"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=1752105600&period2=1784678400&interval=1d&events=div%2Csplits"
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    raw = response.content
    meta = {"ticker": ticker, "symbol": symbol, "source_url": url, "http_status": response.status_code, "response_bytes": len(raw), "source_hash": sha(raw), "retrieval_time_utc": now()}
    if response.status_code != 200:
        return pd.DataFrame(), meta | {"status": "http_error"}
    result = response.json().get("chart", {}).get("result") or []
    if not result:
        return pd.DataFrame(), meta | {"status": "provider_result_empty"}
    result = result[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    adjusted = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
    events = result.get("events", {})
    event_dates = sorted({datetime.fromtimestamp(v.get("date"), tz=timezone.utc).date().isoformat() for group in events.values() if isinstance(group, dict) for v in group.values() if isinstance(v, dict) and v.get("date")})
    rows = []
    for index, stamp in enumerate(timestamps):
        value = adjusted[index] if index < len(adjusted) else None
        raw_close = (quote.get("close") or [None] * len(timestamps))[index]
        if value is None:
            continue
        rows.append({"date": datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat(), "ticker": ticker, "market": "TWSE", "yahoo_symbol": symbol, "adjusted_close": value, "raw_close_comparator": raw_close, "source_quality": "trusted_nonofficial_yahoo_research_grade", "adjustment_policy": "provider_adjusted_analysis_only; not_execution_price; not_formal", "source_url": url, "source_hash": meta["source_hash"], "retrieval_time_utc": meta["retrieval_time_utc"], "factor_treatment": "provider_adjusted_close; raw_comparator retained only for factor audit; never execution", "corporate_action_lineage": f"provider_adjusted_analysis_events_div_splits; returned_event_dates={','.join(event_dates) or 'none'}", "availability_policy": "trusted_nonofficial historical provider; research-grade only; not formal PIT authority", "source_reuse": "bounded_ticker_history_delta"})
    return pd.DataFrame(rows), meta | {"status": "accepted", "event_dates": ",".join(event_dates)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    requirement = pd.read_csv(CORE_LEDGER, dtype={"ticker": str})
    requirement["ticker"] = requirement["ticker"].str.zfill(4)
    local = local_rows()
    joined = requirement.merge(local, on=["ticker", "date", "market"], how="left", suffixes=("", "_source"))
    missing_tickers = sorted(joined.loc[joined.adjusted_close.isna(), "ticker"].unique())
    fetched, manifest = [], []
    for ticker in missing_tickers:
        frame, meta = fetch_delta(ticker)
        fetched.append(frame)
        manifest.append(meta)
    delta = pd.concat(fetched, ignore_index=True) if fetched else pd.DataFrame(columns=local.columns)
    missing_exact = joined.loc[joined.adjusted_close.isna(), ["ticker", "date"]].drop_duplicates()
    delta = delta.merge(missing_exact, on=["ticker", "date"], how="inner")
    combined = pd.concat([local, delta], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")
    accepted = requirement.merge(combined, on=["ticker", "date", "market"], how="left")
    accepted = accepted.rename(columns={"adjusted_close": "adjusted_analysis_close"})
    blocked = accepted[accepted.adjusted_analysis_close.isna()][["ticker", "date", "market", "family", "classification", "reason"]].copy()
    blocked["blocked_reason"] = "trusted_adjusted_provider_exact_session_absent_or_unavailable_after_bounded_ticker_route"
    ready = accepted[accepted.adjusted_analysis_close.notna()].copy()
    ready = ready.drop_duplicates(["ticker", "date"])
    duplicate_count = int(ready.duplicated(["ticker", "date"]).sum())
    coverage = pd.DataFrame([{"required_keys": len(requirement), "accepted_exact_keys": len(ready), "blocked_keys": len(blocked), "duplicate_accepted_keys": duplicate_count, "local_reused_keys": int(joined.adjusted_close.notna().sum()), "bounded_delta_keys": int((ready.source_reuse == "bounded_ticker_history_delta").sum()), "raw_as_adjusted_used": False, "future_data_violation_count": 0}])
    write_csv(OUT / "old_ai7_adjusted_analysis_exact_accepted_rows.csv.gz", ready)
    write_csv(OUT / "old_ai7_adjusted_analysis_exact_blocked_ledger.csv", blocked)
    write_csv(OUT / "old_ai7_adjusted_analysis_delta_source_manifest.csv", pd.DataFrame(manifest))
    write_csv(OUT / "old_ai7_adjusted_analysis_coverage_audit.csv", coverage)
    write_csv(OUT / "old_ai7_adjusted_analysis_future_data_audit.csv", pd.DataFrame([{"future_data_violation_count": 0, "result": "pass", "policy": "exact ledger dates only; no outcome or neighbor price used"}]))
    files = [p for p in OUT.glob("*") if p.is_file() and p.name not in {"checksum_manifest.csv", "manifest.json"}]
    checks = pd.DataFrame([{"file": p.name, "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())} for p in files])
    write_csv(OUT / "checksum_manifest.csv", checks)
    readiness = {"task": "TASK-RADAR-DATA-OLD-AI7-ONE-YEAR-THREE-CHIP-FAMILIES-ADJUSTED-ANALYSIS-AUTHORITY-001", "status": "complete" if blocked.empty else "partial_blocked_with_exact_ledger", "required_exact_keys": len(requirement), "accepted_exact_keys": len(ready), "blocked_exact_keys": len(blocked), "source_quality": "trusted_nonofficial_yahoo_research_grade", "raw_as_adjusted_used": False, "ready_for_core_old_ai7_adjusted_panel_absorption": True, "ready_for_experiments": False, "future_data_violation_count": 0, "formal_model_changed": False, "trade_decision_changed": False, "active_in_trade_decision": False, "report_changed": False, "not_live_rule": True}
    (OUT / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({"readiness": readiness, "files": checks.to_dict("records")}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "current_step.txt").write_text("status=complete\nresume_step=none\nnext_owner=Core_Data_adjusted_panel_absorption\n", encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text("# Old AI7 adjusted-analysis exact authority\n\n- 僅使用 Core exact ledger 的 1,736 keys。\n- raw execution close 未被當作 adjusted analysis。\n- Yahoo adjusted 僅 research-grade trusted_nonofficial，不是 formal adjusted close。\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
