from __future__ import annotations

import json
from pathlib import Path


def build_reasoning_monitor(store,output):
    theses=store.rows("theses"); hypotheses=store.rows("hypotheses"); snaps=store.rows("reasoning_history")
    latest_by_stock={}
    for row in snaps: latest_by_stock[row["stock_id"]]=row
    hyp_by_id={h["hypothesis_id"]:h for h in hypotheses}; thesis_by_stock={}
    for t in theses:
        if t["stock_id"] not in thesis_by_stock or t["thesis_version"]>thesis_by_stock[t["stock_id"]]["thesis_version"]: thesis_by_stock[t["stock_id"]]=t
    rows=[]
    for stock,snap in sorted(latest_by_stock.items()):
        lead=hyp_by_id.get(snap.get("leading_hypothesis"))
        rows.append({"stock_id":stock,"thesis_state":thesis_by_stock.get(stock,{}).get("status","UNKNOWN"),
            "leading_hypothesis":lead.get("hypothesis_type") if lead else "UNKNOWN",
            "alternative_hypotheses":[hyp_by_id[x]["hypothesis_type"] for x in snap["alternative_hypotheses"] if x in hyp_by_id],
            "confidence":snap["confidence"],"supporting_evidence":snap["supporting_evidence"],
            "counter_evidence":snap["counter_evidence"],"unknowns":snap["unknowns"],
            "falsification_conditions":snap["falsification_conditions"],"next_observation":snap["next_observation"]})
    payload={"status":"RESEARCH_DEBUG_ONLY","stock_count":len(rows),"rows":rows,
        "formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False}
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return payload
