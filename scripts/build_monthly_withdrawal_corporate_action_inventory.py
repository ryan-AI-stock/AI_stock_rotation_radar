from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs")
OUT = REPO / "outputs" / "radar_vnext_all_strategy_monthly_withdrawal_corporate_action_inventory_20260730"
OLD = REPO / "outputs" / "radar_vnext_selected_stock_corporate_action_distribution_source_package_20260710"
START, END = "2015-05-18", "2026-07-22"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(name: str, frame: pd.DataFrame) -> Path:
    path = OUT / name
    frame.to_csv(path, index=False)
    return path


def empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def held_intervals(strategy: str, path: Path) -> tuple[pd.DataFrame, dict]:
    if not path.exists():
        return empty(["strategy", "ticker", "holding_start", "holding_end", "source_ledger", "authority_status"]), {
            "strategy": strategy, "source_ledger": str(path), "authority_status": "missing_local_ledger", "rows": 0
        }
    preview = pd.read_csv(path, compression="gzip", nrows=1)
    usecols = ["date", "held_ticker"] + (["variant_id"] if "variant_id" in preview.columns else [])
    daily = pd.read_csv(path, compression="gzip", usecols=usecols)
    if "variant_id" not in daily.columns:
        daily["variant_id"] = "default"
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["held_ticker"] = daily["held_ticker"].astype(str).str.strip().str.zfill(4)
    daily = daily[(daily.date >= START) & (daily.date <= END)].copy()
    daily.sort_values(["variant_id", "date"], inplace=True)
    daily["new_segment"] = daily.held_ticker.ne(daily.groupby("variant_id").held_ticker.shift())
    daily["segment"] = daily.groupby("variant_id").new_segment.cumsum()
    daily = daily[~daily.held_ticker.isin(["cash", "nan", "None", ""])].copy()
    result = (daily.groupby(["variant_id", "held_ticker", "segment"], as_index=False)
              .agg(holding_start=("date", "min"), holding_end=("date", "max"), trading_day_marks=("date", "size"))
              .rename(columns={"held_ticker": "ticker"}))
    result["ticker"] = result.ticker.astype(str).str.zfill(4)
    result.insert(0, "strategy", strategy)
    result["source_ledger"] = str(path)
    result["authority_status"] = "actual_daily_holding_ledger"
    result = result.drop(columns=["segment", "variant_id"]).drop_duplicates(
        ["strategy", "ticker", "holding_start", "holding_end"]
    )
    return result, {
        "strategy": strategy, "source_ledger": str(path), "authority_status": "actual_daily_holding_ledger", "rows": len(result)
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text(
        "status=complete_inventory_only\n"
        "resume_step=request_exact_v4d_and_0050_constituent_holding_authorities_from_core_before_any_event_route_acquisition\n",
        encoding="utf-8",
    )

    source_ledgers = {
        "old_ai7_three_chip": CORE / "old_ai7_three_chip_four_strategy_contract_20260721" / "corrected_NAV_daily_wealth_ledger.csv.gz",
        "old_ai7_relative_00631l_timing": CORE / "vnext_p1_p2_00631l_old_ai7_relative_ma_slope_switch_contract_20260719" / "corrected_NAV_daily_wealth_ledger.csv.gz",
        "old_ai7_priority_backup_00631l": CORE / "vnext_p1_p2_old_ai7_priority_00631l_backup_cd_override_contract_20260720" / "corrected_NAV_daily_wealth_ledger.csv.gz",
        "old_ai7_median_rs60_two_sleeve": CORE / "vnext_p1_p2_old_ai7_vs_00631l_weekly_median_rs60_two_sleeve_contract_20260719" / "corrected_NAV_daily_wealth_ledger.csv.gz",
    }
    interval_frames, discovery = [], []
    for strategy, path in source_ledgers.items():
        frame, row = held_intervals(strategy, path)
        interval_frames.append(frame)
        discovery.append(row)

    # Buy-and-hold has a fixed single-ticker authority; this is an authority declaration,
    # not a price or dividend event assertion.
    interval_frames.append(pd.DataFrame([{
        "strategy": "00631l_buyhold", "ticker": "00631L", "holding_start": START,
        "holding_end": END, "trading_day_marks": pd.NA,
        "source_ledger": "strategy_definition_fixed_buyhold", "authority_status": "fixed_strategy_definition"
    }]))
    discovery.append({"strategy": "00631l_buyhold", "source_ledger": "strategy_definition_fixed_buyhold", "authority_status": "fixed_strategy_definition", "rows": 1})

    # These requested strategies cannot be reconstructed from a static/current constituent map.
    for strategy, reason in [
        ("v4d", "exact_actual_held_ticker_date_ledger_not_found_in_mounted_core_outputs"),
        ("0050_constituent_all", "historical_constituent_all_holding_authority_not_found_in_mounted_core_outputs"),
        ("0050_constituent_top30", "historical_constituent_top30_holding_authority_not_found_in_mounted_core_outputs"),
    ]:
        discovery.append({"strategy": strategy, "source_ledger": "", "authority_status": "blocked_missing_exact_authority", "rows": 0, "blocked_reason": reason})

    intervals = pd.concat(interval_frames, ignore_index=True) if interval_frames else empty([])
    intervals["holding_start"] = intervals.holding_start.astype(str)
    intervals["holding_end"] = intervals.holding_end.astype(str)
    intervals.sort_values(["strategy", "ticker", "holding_start"], inplace=True)
    write_csv("monthly_withdrawal_strategy_holding_intervals_local_authority.csv", intervals)
    discovery_frame = pd.DataFrame(discovery).fillna("")
    write_csv("monthly_withdrawal_strategy_authority_discovery.csv", discovery_frame)

    old_cash = pd.read_csv(OLD / "selected_stock_cash_distribution_events.csv", dtype={"ticker": str})
    old_events = pd.read_csv(OLD / "selected_stock_corporate_action_events.csv", dtype={"ticker": str})
    old_cash["ticker"] = old_cash.ticker.str.zfill(4)
    old_events["ticker"] = old_events.ticker.str.zfill(4)
    universe = sorted(set(intervals.ticker.astype(str)).union({"00631L"}))
    candidate_cash = old_cash[old_cash.ticker.isin(universe)].copy()
    candidate_events = old_events[old_events.ticker.isin(universe)].copy()
    candidate_cash["exact_cash_event_ready"] = False
    candidate_cash["readiness_reason"] = "candidate_amount_only_exact_exdate_and_payment_date_absent"
    write_csv("monthly_withdrawal_local_cash_distribution_candidates.csv", candidate_cash)
    write_csv("monthly_withdrawal_local_corporate_action_candidates.csv", candidate_events)

    rows = []
    for ticker in universe:
        cash = candidate_cash[candidate_cash.ticker.eq(ticker)]
        events = candidate_events[candidate_events.ticker.eq(ticker)]
        rows.append({
            "ticker": ticker,
            "actual_holding_interval_count": int(intervals.ticker.eq(ticker).sum()),
            "cash_distribution_candidate_rows": len(cash),
            "candidate_cash_amount_rows": int(cash.cash_dividend_total_per_share_candidate.notna().sum()) if "cash_dividend_total_per_share_candidate" in cash else 0,
            "exact_exdate_rows": int(cash.ex_date.notna().sum()) if "ex_date" in cash else 0,
            "exact_payment_date_rows": int(cash.payment_date.notna().sum()) if "payment_date" in cash else 0,
            "capital_change_candidate_rows": 0,
            "cash_distribution_status": "blocked_missing_exact_exdate_payment_date" if len(cash) else "no_local_candidate_source",
            "capital_change_status": "blocked_no_local_exact_capital_change_event_source",
            "adjusted_factor_inference_used": False,
        })
    coverage = pd.DataFrame(rows)
    write_csv("monthly_withdrawal_corporate_action_local_coverage_audit.csv", coverage)

    blocked = []
    for _, row in discovery_frame[discovery_frame.authority_status.eq("blocked_missing_exact_authority")].iterrows():
        blocked.append({"scope": "strategy_authority", "strategy": row.strategy, "ticker": "", "blocked_field": "actual_held_ticker_date_authority", "reason": row.blocked_reason, "next_step": "Core must export frozen actual holding intervals before event acquisition", "network_acquisition_authorized": False})
    for _, row in coverage.iterrows():
        blocked.append({"scope": "cash_distribution", "strategy": "all_discovered", "ticker": row.ticker, "blocked_field": "exact_exdate_payment_date_cash_per_share_market_available_at", "reason": row.cash_distribution_status, "next_step": "official historical event route required after complete authority", "network_acquisition_authorized": False})
        blocked.append({"scope": "capital_change", "strategy": "all_discovered", "ticker": row.ticker, "blocked_field": "split_reduction_merger_conversion_effective_date_ratio_holder_treatment", "reason": row.capital_change_status, "next_step": "official historical corporate-action route required after complete authority", "network_acquisition_authorized": False})
    blocked_frame = pd.DataFrame(blocked)
    write_csv("monthly_withdrawal_corporate_action_blocked_ledger.csv", blocked_frame)

    manifest_rows = []
    for path in [*source_ledgers.values(), OLD / "selected_stock_cash_distribution_events.csv", OLD / "selected_stock_corporate_action_events.csv", OLD / "readiness_for_core_selected_stock_total_return_ledger.json"]:
        manifest_rows.append({"path": str(path), "exists": path.exists(), "sha256": sha256(path) if path.exists() else "", "retrieval_or_materialization_time_utc": now(), "role": "local_source_inventory"})
    manifest = pd.DataFrame(manifest_rows)
    write_csv("monthly_withdrawal_corporate_action_source_manifest.csv", manifest)

    future = pd.DataFrame([{
        "audit_scope": "local_inventory_only", "future_data_violation_count": 0,
        "policy": "no_adjusted_factor_event_inference_no_current_snapshot_backfill_no_performance_calculation",
        "asof_date": END,
    }])
    write_csv("monthly_withdrawal_corporate_action_future_data_audit.csv", future)

    readiness = {
        "task_id": "TASK-RADAR-DATA-ALL-STRATEGY-MONTHLY-WITHDRAWAL-CORPORATE-ACTION-INVENTORY-001",
        "status": "inventory_complete_event_acquisition_blocked_by_missing_strategy_authority_and_exact_event_dates",
        "requested_period": {"start": START, "end": END},
        "discovered_strategy_authority": {
            "strategy_rows": len(discovery_frame),
            "authority_ready_strategy_rows": int(discovery_frame.authority_status.isin(["actual_daily_holding_ledger", "fixed_strategy_definition"]).sum()),
            "authority_blocked_strategy_rows": int(discovery_frame.authority_status.eq("blocked_missing_exact_authority").sum()),
            "local_actual_holding_intervals": len(intervals),
            "local_actual_ticker_union": len(universe),
        },
        "local_event_inventory": {
            "cash_distribution_candidate_rows": len(candidate_cash),
            "corporate_action_candidate_rows": len(candidate_events),
            "exact_exdate_rows": int(candidate_cash.ex_date.notna().sum()) if len(candidate_cash) else 0,
            "exact_payment_date_rows": int(candidate_cash.payment_date.notna().sum()) if len(candidate_cash) else 0,
            "capital_change_exact_rows": 0,
        },
        "cash_dividend_ledger_ready": False,
        "capital_change_ledger_ready": False,
        "ready_for_core_monthly_withdrawal_total_return_rechain": False,
        "bounded_network_fill_started": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
        "next_handoff": "Core/Data must provide exact V4-D plus 0050 constituent all/top30 holding interval authority; then Radar can quantify bounded official historical event-route delta without inferring events from adjusted factors.",
    }
    (OUT / "readiness_for_core_monthly_withdrawal_corporate_action_inventory.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "final_summary_zh.md").write_text(
        "# 月提領公司行動資料稽核\n\n"
        "本封包只做本機 source inventory；沒有計算績效、調整後價格或股利再投入。\n\n"
        f"- 已從本機 daily holding ledger 識別 {len(universe)} 個 ticker、{len(intervals)} 段實際持有區間。\n"
        "- 00631L buyhold 納入固定策略 authority。\n"
        "- V4-D、0050 成分股 all、0050 前30 的 exact actual holding interval authority 未在掛載 Core outputs 找到，因此不能把候選事件包裝成完整策略 coverage。\n"
        f"- 舊官方候選包對目前 union 僅有 {len(candidate_cash)} 筆現金股利候選與 {len(candidate_events)} 筆公司行動候選；精確除息日、付款日均為 0，且非股利資本事件沒有可接受 exact ledger。\n"
        "- adjusted factor 未用來推定事件；缺失未填 0。下一步需 Core 匯出三條缺少策略的 frozen actual holding intervals，才可量化並授權歷史官方 event route delta。\n",
        encoding="utf-8",
    )
    files = sorted(p for p in OUT.iterdir() if p.is_file() and p.name not in {"manifest.json"})
    artifact_manifest = [{"file": p.name, "sha256": sha256(p), "bytes": p.stat().st_size} for p in files]
    (OUT / "manifest.json").write_text(json.dumps({"generated_at": now(), "artifacts": artifact_manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
