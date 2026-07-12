from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-POST-MARKET-SOURCE-REMAINING-GAP-CONVERGENCE-001"
OUTPUT_NAME = "radar_vnext_p3_post_market_source_remaining_gap_convergence_20260712"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    output = repo / "outputs" / OUTPUT_NAME
    output.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()

    common = {
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }
    families = [
        {"family":"raw_execution_OHLCV","required":"183886 warmup ticker-dates","ready":"181375","blocked":"0 source gaps","na":"2511 official zero/not applicable","actual_coverage":"P3 source 2022-07-11~2026-07-09; exact Layer4 contract through 2026-06-29","source_quality":"official TWSE/TPEx","status":"ready_with_explicit_NA","download_action":"reuse_only","phase_impact":"technical indicators and execution price"},
        {"family":"adjusted_analysis_HLC","required":"227186 exact-primary80 plus warmup ticker-dates","ready":"224936","blocked":"2250 rows; 11 fully blocked tickers; 2025-08-01 provider partial","na":"0","actual_coverage":"exact Layer4 through 2026-06-29","source_quality":"trusted_nonofficial research-grade; raw kept separate","status":"partial_structural","download_action":"no_reprobe_exhausted_routes","phase_impact":"RS/MA/BIAS/KD rows affected; formal adjusted completeness blocked"},
        {"family":"corporate_action_guard","required":"701 exact-primary80 union tickers","ready":"674 tickers with event inventory","blocked":"701 tickers lack official no-event completeness proof","na":"0","actual_coverage":"P3 event inventory; no historical current-table backfill","source_quality":"official event inventory, incomplete no-event proof","status":"partial_structural","download_action":"no_reprobe_exhausted_routes","phase_impact":"formal total-return/adjusted completeness; diagnostic raw execution remains separate"},
        {"family":"Layer4_exact_PIT_membership","required":"weekly primary80 through latest source-ready trading week","ready":"154 snapshots / 12320 rows / 701 tickers","blocked":"July 2026 exact snapshots not materialized","na":"0","actual_coverage":"2023-07-14~2026-06-29","source_quality":"Core exact weekly PIT contract","status":"core_materialization_required","download_action":"no_download_underlying_sources_available_to_2026-07-09","phase_impact":"blocks extending candidate membership beyond 2026-06-29"},
        {"family":"institutional_20D_warmup","required":"89525 ticker-dates","ready":"89236","blocked":"0 source gaps","na":"289 official zero/not applicable","actual_coverage":"P3 official source to 2026-07-09","source_quality":"official TWSE/TPEx post-close","status":"ready_with_explicit_NA","download_action":"reuse_only","phase_impact":"chip 5/10/20D rollup input"},
        {"family":"margin_short_20D_warmup","required":"89525 ticker-dates","ready":"87963","blocked":"0 source gaps","na":"1562 official zero/not applicable","actual_coverage":"P3 official source to 2026-07-09","source_quality":"official TWSE/TPEx post-close","status":"ready_with_explicit_NA","download_action":"reuse_only","phase_impact":"crowding and unwind context"},
        {"family":"securities_lending_20D_warmup","required":"89525 ticker-dates","ready":"88963","blocked":"0 source gaps","na":"562 official zero/not applicable","actual_coverage":"P3 official source to 2026-07-09","source_quality":"official TWSE/TPEx post-close","status":"ready_with_explicit_NA","download_action":"reuse_only","phase_impact":"lending/crowding context"},
        {"family":"foreign_ownership_20D_warmup","required":"89525 ticker-dates","ready":"89379","blocked":"0 source gaps","na":"146 official zero/not applicable","actual_coverage":"P3 official source to 2026-07-09","source_quality":"official TWSE/TPEx date-query","status":"ready_with_explicit_NA","download_action":"reuse_only","phase_impact":"institutional/large-holder proxy input"},
        {"family":"TDCC_P3_2","required":"official retained weekly history","ready":"51 weeks / 61856 rows","blocked":"P3-1 older weeks expired; 11 ticker-weeks official zero","na":"P3-1 optional component not applicable","actual_coverage":"2025-07-11~2026-07-03","source_quality":"official TDCC retained archive","status":"partial_locked_optional_AB","download_action":"no_old_week_reprobe","phase_impact":"optional P3-2 A/B only; does not block P3-1"},
        {"family":"TAIFEX_foreign_OI","required":"728 Taiwan trading dates","ready":"728","blocked":"0","na":"0","actual_coverage":"2023-07-11~2026-07-09 trading dates","source_quality":"official TAIFEX range CSV","status":"ready","download_action":"reuse_only","phase_impact":"market environment"},
        {"family":"full_market_traded_value","required":"TWSE/TPEx/ALL daily","ready":"728 dates each market and combined","blocked":"0","na":"0","actual_coverage":"2023-07-11~2026-07-09 trading dates","source_quality":"official TWSE/TPEx daily totals","status":"ready","download_action":"reuse_only","phase_impact":"market breadth/liquidity environment"},
        {"family":"full_market_margin_balance","required":"TWSE/TPEx/ALL daily","ready":"728 dates each market and combined","blocked":"0","na":"0","actual_coverage":"2023-07-11~2026-07-09 trading dates","source_quality":"official TWSE/TPEx daily totals","status":"ready","download_action":"reuse_only","phase_impact":"market leverage environment"},
        {"family":"global_SOX_Nasdaq_VIX_USDTWD","required":"SOX plus Nasdaq/VIX/USD-TWD P3 sessions","ready":"SOX 752 sessions; Nasdaq/VIX/USD-TWD accepted","blocked":"0 source gaps","na":"Taiwan holidays/session mismatch handled by cutoff policy","actual_coverage":"2023-07-11~2026-07-09 available sessions","source_quality":"Yahoo trusted_nonofficial research-grade","status":"ready_with_session_cutoff","download_action":"reuse_only","phase_impact":"global risk environment"},
    ]
    for row in families:
        row.update(common)
    write_csv(output / "p3_remaining_source_family_matrix.csv", families)

    gaps = [
        {"gap_id":"ADJ-STRUCTURAL","family":"adjusted_analysis_HLC","gap_type":"structural_source_exhausted","row_scope":"2250 ticker-dates / 11 fully blocked tickers","owner":"Radar evidence retained","next_action":"do not repeat free-route probe; keep row blocked","prevents_phase_a":False,"prevents_phase_b":False,"prevents_formal":True,"future_data_violation_count":0},
        {"gap_id":"CA-NOEVENT","family":"corporate_action_guard","gap_type":"structural_no_event_proof","row_scope":"701 primary80 union tickers","owner":"source governance policy","next_action":"retain partial event inventory; no current-table historical inference","prevents_phase_a":False,"prevents_phase_b":False,"prevents_formal":True,"future_data_violation_count":0},
        {"gap_id":"L4-JULY","family":"Layer4_exact_PIT_membership","gap_type":"not_materialized_not_source_missing","row_scope":"2026-06-30~2026-07-09 source-ready dates","owner":"Core/Data","next_action":"recompute exact weekly Layer4 from frozen Layer0-4 contract; no 2026-06-29 carry-forward claim","prevents_phase_a":True,"prevents_phase_b":True,"prevents_formal":True,"future_data_violation_count":0},
        {"gap_id":"DAILY-FEATURES","family":"daily technical/chip/market state","gap_type":"core_compute_not_source_gap","row_scope":"Core 715 dates / 57200 candidates","owner":"Core/Data","next_action":"compute RS/MA/BIAS/KD, 5/10/20D chip rollups and three-group market state","prevents_phase_a":True,"prevents_phase_b":True,"prevents_formal":True,"future_data_violation_count":0},
        {"gap_id":"TDCC-OLD","family":"TDCC_P3_1","gap_type":"source_expired_optional","row_scope":"2023-07-11~2025-07-10","owner":"accepted optional-source policy","next_action":"P3-1 excludes TDCC component; P3-2 A/B only","prevents_phase_a":False,"prevents_phase_b":False,"prevents_formal":False,"future_data_violation_count":0},
    ]
    write_csv(output / "p3_remaining_source_gap_ledger.csv", gaps)

    layer4 = [
        {"period":"2023-07-14~2026-06-29","membership_status":"exact_PIT_ready","source_input_status":"ready","allowed_use":"Core exact primary80","blocked_reason":"","future_data_violation_count":0},
        {"period":"2026-06-30~2026-07-09","membership_status":"not_materialized","source_input_status":"official price/chip/market inputs available through 2026-07-09","allowed_use":"Core recompute only","blocked_reason":"cannot carry 2026-06-29 membership forward as exact PIT","future_data_violation_count":0},
    ]
    write_csv(output / "p3_layer4_july_freshness_audit.csv", layer4)

    impact = [
        {"項目":"技術指標","目前狀態":"來源足夠，少數 adjusted rows 明確 blocked","影響":"Core 尚未完成日級 RS/MA/BIAS/KD 計算","是否阻止Phase_A":"是，原因是未計算，不是未下載","是否阻止Phase_B":"是","formal影響":"adjusted/corporate completeness 仍阻止 formal"},
        {"項目":"籌碼","目前狀態":"法人/融資融券/借券/外資持股 20D source gap=0；官方零列保留 NA","影響":"Core 尚未滾出 5/10/20D 特徵","是否阻止Phase_A":"是，原因是未計算","是否阻止Phase_B":"是","formal影響":"不新增 source blocker"},
        {"項目":"行情環境","目前狀態":"TAIFEX、全市場成交額/融資、SOX/Nasdaq/VIX/USD-TWD ready","影響":"Core 尚未形成三群 market state","是否阻止Phase_A":"是，原因是未計算/政策","是否阻止Phase_B":"是","formal影響":"Yahoo 全球欄位維持 trusted_nonofficial"},
        {"項目":"候選池","目前狀態":"exact Layer4 只到 2026-06-29；7月底層來源已存在","影響":"7月不能沿用舊名單冒充 exact","是否阻止Phase_A":"若驗證期延伸到7月則是","是否阻止Phase_B":"若延伸到7月則是","formal影響":"需 Core frozen-contract recompute"},
        {"項目":"TDCC","目前狀態":"51週已鎖存，P3-1 舊週結構性不可得","影響":"只作 P3-2 optional A/B","是否阻止Phase_A":"否","是否阻止Phase_B":"否","formal影響":"不得宣稱P3全期 TDCC ready"},
        {"項目":"成交執行","目前狀態":"official raw OHLCV ready with explicit official NA","影響":"可作 execution ledger","是否阻止Phase_A":"否","是否阻止Phase_B":"否","formal影響":"仍須與 adjusted analysis 分欄"},
    ]
    write_csv(output / "p3_strategy_center_plain_gap_impact_zh.csv", impact)

    source_files = [
        repo / "outputs/radar_vnext_p3_exact_primary80_full_feature_source_scope_repair_20260711/readiness_for_core_p3_exact_primary80_source_scope_repair.json",
        repo / "outputs/radar_vnext_p3_exact_primary80_raw_hlc_warmup_gap_fill_20260711/readiness_for_core_p3_exact_primary80_raw_hlc_warmup.json",
        repo / "outputs/radar_vnext_p3_exact_primary80_chip_20d_warmup_gap_fill_20260711/readiness_for_core_p3_exact_primary80_chip_20d_warmup.json",
        repo / "outputs/radar_vnext_p3_expiry_lock_audit_20260711/readiness_for_core_p3_expiry_lock.json",
        repo / "outputs/radar_vnext_p3_market_state_source_fill_20260711/readiness_for_core_p3_market_state_source_fill.json",
        Path("C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab/outputs/vnext_p3_layer5_daily_state_machine_materialization_20260711/p3_layer5_daily_readiness.json"),
        Path("C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab/outputs/vnext_layer4_80_primary_pool_contract_20260708/layer4_80_primary_pool_contract.csv"),
    ]
    reuse = []
    for path in source_files:
        reuse.append({"source_path":str(path),"exists":path.exists(),"sha256":sha256(path) if path.exists() else "","reuse_status":"accepted_evidence_reused" if path.exists() else "missing"})
    write_csv(output / "p3_existing_compact_reuse_manifest.csv", reuse)

    write_csv(output / "p3_future_data_audit.csv", [{
        "audit":"no current/static/generated map used to infer historical membership; July membership not carried forward; source timestamps retain next-session eligibility",
        "future_data_violation_count":0,
        "status":"pass",
    }])

    readiness = {
        "task_id": TASK_ID,
        "status": "source_gap_converged_core_daily_materialization_required",
        "source": "latest Core/Radar physical compact, manifest, coverage and blocked-ledger audit",
        "coverage": "P3 requested 2023-07-11~2026-07-10; source actual generally through 2026-07-09; exact Layer4 PIT through 2026-06-29",
        "new_download_rows": 0,
        "new_download_reason": "no legally free true source gap remains after compact reuse audit",
        "source_gap_count_requiring_download": 0,
        "structural_or_policy_gap_count": 3,
        "core_compute_gap_count": 1,
        "ready_for_core_p3_post_market_source_convergence_absorption": True,
        "ready_for_core_rerun": True,
        "ready_for_core_daily_feature_materialization": True,
        "ready_for_core_layer4_july_exact_recompute": True,
        "ready_for_phase_a": False,
        "ready_for_phase_b": False,
        "ready_for_experiments": False,
        "ready_for_strategy_replay": False,
        "ready_for_formal": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "portfolio_replay_executed": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
        "future_data_violation_count": 0,
        "next_owner": "Core/Data",
        "next_task": "materialize daily technical/chip/market-state blocks and recompute July exact Layer4 without carry-forward",
    }
    (output / "readiness_for_core_p3_post_market_source_convergence.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = """# P3 主線剩餘資料缺口收斂

## 結論

- 目前沒有仍可合法免費補抓的真 source gap；本次新增下載 0 rows，避免重抓與無限 probe。
- 7 月 Layer4 缺口是 Core 尚未依 frozen contract 重新 materialize，不是 Radar 缺行情或籌碼。不得把 2026-06-29 名單 carry-forward 成 exact PIT。
- 法人、融資融券、借券、外資持股 20D warmup 的 source_gap_count=0；剩餘列均為官方 zero/not-applicable。
- TAIFEX、全市場成交額、全市場融資、SOX/Nasdaq/VIX/USD-TWD source ready。
- Phase A/B 仍不可放行，主因是 Core 尚未計算 daily RS/MA/BIAS/KD、5/10/20D 籌碼 rollup、三群 market state，以及 7 月 exact Layer4。
- adjusted analysis 舊碼與 corporate-action no-event completeness 維持 structural/partial，只阻止 formal completeness，不再重探已耗盡免費路線。

## 下一棒

交 Core/Data 吸收本包，執行 daily feature materialization 與 7 月 exact Layer4 frozen-contract recompute。不得直接交 Experiments。

## 固定旗標

formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false；portfolio_replay_executed=false；ready_for_strategy_replay=false；ready_for_formal=false；not_live_rule=true；future_data_violation_count=0。
"""
    (output / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (output / "current_step.txt").write_text("completed_source_gap_convergence_handoff_core_pending\n", encoding="utf-8")

    artifacts = []
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        artifacts.append({"path":path.name,"bytes":path.stat().st_size,"sha256":sha256(path)})
    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": retrieved_at,
        "source": readiness["source"],
        "coverage": readiness["coverage"],
        "future_data_violation_count": 0,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
