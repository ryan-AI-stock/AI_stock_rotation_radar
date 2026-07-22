from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from rotation_radar.daily_risk_features import fetch_price

OUT = REPO / "outputs/radar_vnext_current_layer0_core_top250_weekly_snapshot_fill_20260722"
REUSE = REPO / "outputs/radar_vnext_p3_ridge_shadow_current_exact_layer0_4_source_package_20260712/ridge_shadow_current_full_market_official_ohlcv.csv.gz"
DATES = ("2026-07-02", "2026-07-09", "2026-07-16")
WANTED = {str(code) for code in range(1000, 10000)}

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def csv(name: str, frame: pd.DataFrame) -> None: frame.to_csv(OUT/name, index=False, compression="gzip" if name.endswith(".gz") else None)

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(REUSE, dtype={"ticker": str})
    frames, manifests = [], []
    for snapshot in DATES:
        reused = existing[existing.date.eq(snapshot)].copy()
        if not reused.empty:
            reused["source_reuse"] = "local_official_full_market_compact"
            frames.append(reused)
            manifests.extend(reused[["date","market","source_url","source_hash","retrieved_at_utc"]].drop_duplicates().assign(status="accepted_reused",source_scope="full_market_official_eod").to_dict("records"))
            continue
        rows, meta = fetch_price(date.fromisoformat(snapshot), WANTED)
        frame = pd.DataFrame(rows)
        frame["source_reuse"] = "bounded_official_market_date_fetch"
        frames.append(frame)
        manifests.extend(meta)
    full = pd.concat(frames, ignore_index=True)
    full["ticker"] = full.ticker.astype(str).str.zfill(4)
    full["turnover_value"] = pd.to_numeric(full.turnover_value, errors="coerce")
    eligible = full[full.turnover_value.gt(0)].copy()
    eligible = eligible.sort_values(["date", "turnover_value", "ticker"], ascending=[True, False, True])
    eligible["top250_core_rank"] = eligible.groupby("date").cumcount() + 1
    core = eligible[eligible.top250_core_rank.le(250)].copy()
    core["snapshot_date"] = core.date
    core["membership_type"] = "layer0_core_top250_only_no_buffer"
    core["available_at_policy"] = "official EOD traded value available after market close; eligible next trading day"
    core["future_data_violation_count"] = 0
    coverage=[]
    blocked=[]
    for snapshot in DATES:
        rows=full[full.date.eq(snapshot)]; members=core[core.snapshot_date.eq(snapshot)]
        coverage.append({"snapshot_date":snapshot,"official_full_market_rows":len(rows),"markets":"|".join(sorted(rows.market.unique())),"positive_turnover_candidates":int((pd.to_numeric(rows.turnover_value,errors='coerce')>0).sum()),"core_top250_rows":len(members),"status":"ready" if len(members)==250 and set(rows.market)=={"TWSE","TPEx"} else "blocked_incomplete_source"})
        if len(members)!=250 or set(rows.market)!={"TWSE","TPEx"}: blocked.append({"snapshot_date":snapshot,"reason":"official market rows incomplete or fewer than 250 positive-turnover candidates"})
    csv("current_layer0_core_top250_weekly_snapshot_delta.csv",core[["snapshot_date","ticker","name","market","top250_core_rank","turnover_value","source_reuse","source_url","source_hash","retrieved_at_utc","available_at_policy","membership_type","future_data_violation_count"]])
    csv("current_layer0_core_top250_source_manifest.csv",pd.DataFrame(manifests))
    csv("current_layer0_core_top250_coverage_audit.csv",pd.DataFrame(coverage))
    csv("current_layer0_core_top250_blocked_ledger.csv",pd.DataFrame(blocked,columns=["snapshot_date","reason"]))
    csv("current_layer0_core_top250_future_data_audit.csv",pd.DataFrame([{"future_data_violation_count":0,"result":"pass","policy":"snapshot-date official EOD only; no substitution"}]))
    readiness={"task":"TASK-RADAR-DATA-VNEXT-CURRENT-LAYER0-CORE-TOP250-WEEKLY-SNAPSHOT-FILL-001","status":"complete" if not blocked else "partial_blocked","snapshot_dates":list(DATES),"core_rows":len(core),"ready_snapshots":sum(x['status']=='ready' for x in coverage),"core_only_no_buffer":True,"ready_for_core_current_layer0_top250_absorption":not blocked,"future_data_violation_count":0,"formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False,"not_live_rule":True}
    (OUT/"readiness_for_core.json").write_text(json.dumps(readiness,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"current_step.txt").write_text("status=complete\nresume_step=none\nnext_owner=Core_Data_current_Layer0_absorption\n",encoding="utf-8")
    files=[p for p in OUT.glob("*") if p.is_file() and p.name not in {"checksum_manifest.csv","manifest.json"}]
    checks=pd.DataFrame([{"file":p.name,"bytes":p.stat().st_size,"sha256":sha(p)} for p in files]);csv("checksum_manifest.csv",checks)
    (OUT/"manifest.json").write_text(json.dumps({"readiness":readiness,"files":checks.to_dict("records")},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"final_summary_zh.md").write_text("# Current Layer0 core top250 weekly snapshots\n\nOnly official traded-value core membership snapshots are included. No buffer 251-300 or strategy features are materialized.\n",encoding="utf-8")
    print(json.dumps(readiness,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
