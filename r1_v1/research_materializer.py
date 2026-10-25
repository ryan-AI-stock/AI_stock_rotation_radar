from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path

from .learning_engine import build_change_proposals
from .memory_engine import benchmark_registry,decision_snapshot,scheduled_reviews
from .opportunity_engine import compare_holding_to_challenger,research_state
from .research_store import ResearchStore

def rows(path):return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def materialize(date="2026-10-22",root="data/r1_v1/research",monitor_path="data/r1_v1/final_monitor/latest.json"):
    contexts={x["ticker"]:x for x in rows("data/r1_v1/context_history.jsonl") if x["date"]==date}
    reasonings={x["stock_id"]:x for x in rows("data/r1_v1/reasoning/reasoning_history.jsonl") if x["date"]==date}
    theses={x["stock_id"]:x for x in rows("data/r1_v1/reasoning/theses.jsonl") if x["effective_from"]<=date}
    cfg=load("config/r1.json");holdings=[x["ticker"] for x in cfg["securities"] if x.get("shares",0)>0 and x["ticker"] in contexts]
    store=ResearchStore(root);history=store.rows("portfolio_states")
    bundles={t:{"ticker":t,"context":contexts[t],"reasoning":reasonings[t],
      "structural_evidence_count":len(theses[t].get("supporting_evidence_ids",[])),
      "earnings_visibility":None} for t in contexts if t in reasonings and t in theses}
    priorities={"STRONG_ADVANTAGE":4,"MODERATE_ADVANTAGE":3,"WATCH":2,"NO_ADVANTAGE":1,"DATA_INSUFFICIENT":0}
    selected=[]
    for holding in holdings:
        comparisons=[compare_holding_to_challenger(date,bundles[holding],b) for t,b in bundles.items() if t!=holding]
        comparisons.sort(key=lambda x:(priorities[x.opportunity_state],len(x.supporting_evidence_ids),-len(x.unknowns),x.challenger_stock_id),reverse=True)
        best=comparisons[0] if comparisons else None
        if best:store.append("opportunities",best)
        state=research_state(date,"R1_RESEARCH_PORTFOLIO",holding,best,history)
        store.append("portfolio_states",state);history.append(asdict(state));selected.append((holding,best,state))
        snap=decision_snapshot(date,reasonings[holding],asdict(state))
        store.append("decision_snapshots",snap)
        for review in scheduled_reviews(snap,[date]):store.append("outcome_reviews",review)
    for row in benchmark_registry(date,{}):store.append("benchmark_snapshots",row)
    for proposal in build_change_proposals(store.rows("outcome_reviews"),date):store.append("model_change_proposals",proposal)
    themes={x["theme_id"]:x["theme_context"] for x in contexts.values()}
    monitor={"as_of_date":date,"market_regime":next(iter(contexts.values()))["market_context"] if contexts else {},
      "theme_map":themes,"current_portfolio_research_state":[asdict(s) for _,_,s in selected],
      "top_challengers":[{"holding":h,"challenger":c.challenger_stock_id if c else None,"relative_opportunity":c.opportunity_state if c else "DATA_INSUFFICIENT"} for h,c,_ in selected],
      "possible_mispricing_candidates":[t for t,c in contexts.items() if c.get("possible_mispricing_candidate")],
      "thesis_changes":[{"stock_id":t,"state":reasonings[t]["thesis_state"]} for t in holdings],
      "high_confidence_counter_evidence":[],"unknown_data_gaps":sorted(set(u for _,c,_ in selected for u in (c.unknowns if c else []))),
      "benchmark_comparison":store.rows("benchmark_snapshots"),
      "portfolio_separation":{"r1_research_portfolio":"research judgments only","ryan_actual_portfolio":"observation only; never used as R1 performance"},
      "decision_support_only":True,"formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False}
    p=Path(monitor_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(monitor,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"holdings":len(holdings),"comparisons":len(store.rows("opportunities")),"decisions":len(store.rows("decision_snapshots")),
      "reviews":len(store.rows("outcome_reviews")),"proposals":len(store.rows("model_change_proposals")),"monitor":str(p),
      "formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False}

if __name__=="__main__":print(json.dumps(materialize(),ensure_ascii=False))

