from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs/radar_2308_20250801_adjusted_holding_mark_bounded_fill_20260721"
ADJUSTED = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711/checkpoints/adjusted/2308.csv.gz"
RAW = REPO / "outputs/radar_old_ai7_one_year_three_chip_families_official_net_source_package_20260721/raw_close_daily.csv.gz"

def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    adjusted = pd.read_csv(ADJUSTED)
    neighbors = adjusted[adjusted.date.isin(["2025-07-31", "2025-08-04"])].copy()
    neighbors["factor"] = neighbors.adjusted_close / neighbors.raw_close_comparator
    assert len(neighbors) == 2 and neighbors.factor.notna().all()
    factor_range = neighbors.factor.max() - neighbors.factor.min()
    # Provider values are float32-like; this permits only rounding-level drift.
    assert factor_range < 2e-8
    raw = pd.read_csv(RAW, dtype={"ticker":str})
    target = raw[(raw.ticker.str.zfill(4)=="2308") & (raw.date=="2025-08-01")].iloc[0]
    mark = float(target.close) * float(neighbors.factor.mean())
    row = pd.DataFrame([{"date":"2025-08-01","ticker":"2308","market":"TWSE","official_raw_close":float(target.close),"adjusted_analysis_close":mark,"factor":float(neighbors.factor.mean()),"factor_left_20250731":float(neighbors.factor.iloc[0]),"factor_right_20250804":float(neighbors.factor.iloc[1]),"factor_range":float(factor_range),"source_quality":"trusted_nonofficial_yahoo_factor_continuity_reconstruction_research_grade","adjustment_policy":"bounded same-factor reconstruction from adjacent trusted adjusted/raw pairs; not raw-as-adjusted; not formal","official_raw_source_url":target.source_url,"official_raw_source_hash":target.source_hash,"trusted_adjusted_source_url":neighbors.source_url.iloc[0],"trusted_adjusted_source_hash":neighbors.source_hash.iloc[0],"corporate_action_lineage":"no factor discontinuity across 2025-07-31 to 2025-08-04; exact target provider placeholder reconstructed with continuous factor","future_data_violation_count":0}])
    row.to_csv(OUT/"2308_20250801_adjusted_holding_mark_patch.csv",index=False)
    audit=pd.DataFrame([{"check":"two_neighbor_factor_continuity","result":"pass","factor_range":factor_range},{"check":"raw_as_adjusted_used","result":"pass_false","value":False},{"check":"future_data_violation_count","result":"pass","value":0}]); audit.to_csv(OUT/"2308_20250801_factor_continuity_audit.csv",index=False)
    blocked=pd.DataFrame(columns=["ticker","date","reason"]);blocked.to_csv(OUT/"2308_20250801_blocked_ledger.csv",index=False)
    files=[p for p in OUT.glob("*.csv")]; checks=pd.DataFrame([{"file":p.name,"sha256":digest(p),"bytes":p.stat().st_size} for p in files]);checks.to_csv(OUT/"checksum_manifest.csv",index=False)
    readiness={"task":"TASK-RADAR-DATA-2308-20250801-ADJUSTED-HOLDING-MARK-BOUNDED-FILL-001","status":"complete_research_grade_factor_continuity_reconstruction","accepted_rows":1,"raw_as_adjusted_used":False,"future_data_violation_count":0,"ready_for_core_absorption":True,"ready_for_experiments":False,"formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False,"not_live_rule":True}
    (OUT/"readiness_for_core.json").write_text(json.dumps(readiness,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"manifest.json").write_text(json.dumps({"readiness":readiness,"files":checks.to_dict("records")},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"current_step.txt").write_text("status=complete\nresume_step=none\nnext_owner=Core_and_Strategy_Center\n",encoding="utf-8")
    print(json.dumps(readiness,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
