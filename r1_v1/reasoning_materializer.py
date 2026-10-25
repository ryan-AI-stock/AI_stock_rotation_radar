from __future__ import annotations

import json
from pathlib import Path

from .reasoning_engine import (build_causal_chain,disconfirmation_pass,expectation_analysis,
    generate_competing_hypotheses,initial_thesis,reasoning_snapshot)
from .reasoning_monitor import build_reasoning_monitor
from .reasoning_store import ReasoningStore


def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def materialize(context_path="data/r1_v1/context_history.jsonl",theme_path="config/r1_v02_themes.json",
                evidence_root="data/r1_v1",output_root="data/r1_v1/reasoning",
                monitor_path="data/r1_v1/reasoning_monitor/latest.json"):
    contexts=[json.loads(x) for x in Path(context_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    themes=load_json(theme_path)["themes"]; theme_map={t["id"]:t for t in themes}
    events=[json.loads(x) for x in Path(evidence_root,"events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    claims=[json.loads(x) for x in Path(evidence_root,"claims.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    sources=[json.loads(x) for x in Path(evidence_root,"sources.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    source_id_by_url={s["source_url"]:s["source_id"] for s in sources}
    claims_by_event={}
    for c in claims:claims_by_event.setdefault(c["event_id"],[]).append(c["claim_id"])
    events_by_stock={}
    for e in events:events_by_stock.setdefault(e["primary_entity"],[]).append(e)
    store=ReasoningStore(output_root)
    for context in contexts:
        context=dict(context)
        context["supporting_evidence"]=[source_id_by_url[url] for url in context.get("supporting_evidence",[]) if url in source_id_by_url]
        context["contradicting_evidence"]=[source_id_by_url[url] for url in context.get("contradicting_evidence",[]) if url in source_id_by_url]
        stock=context["ticker"]; theme=theme_map[context["theme_id"]]; related=events_by_stock.get(stock,[])
        evidence_ids=list(dict.fromkeys([e["event_id"] for e in related]+sum((claims_by_event.get(e["event_id"],[]) for e in related),[])))
        thesis=initial_thesis(stock,theme["name"],theme["bottleneck_thesis"],context["date"],evidence_ids,
            ["company_specific_ai_revenue_share","20D_60D_context_history","independent_customer_confirmation"])
        store.append("theses",thesis)
        nodes,edges=build_causal_chain(thesis,theme["name"],context["date"])
        for x in nodes:store.append("causal_nodes",x)
        for x in edges:store.append("causal_edges",x)
        hypotheses=generate_competing_hypotheses(context)
        for h in hypotheses:store.append("hypotheses",h)
        expectation=expectation_analysis(stock,related[-1]["event_id"] if related else None,
            None,None,evidence_ids,context["evaluation_time"])
        store.append("expectations",expectation)
        disconfirm=disconfirmation_pass(hypotheses[0],context) if hypotheses else None
        if disconfirm:store.append("disconfirmation",disconfirm)
        snap=reasoning_snapshot(context["date"],stock,context,thesis,hypotheses,disconfirm)
        store.append("reasoning_history",snap)
    monitor=build_reasoning_monitor(store,monitor_path)
    return {"stock_count":monitor["stock_count"],"theses":len(store.rows("theses")),
        "hypotheses":len(store.rows("hypotheses")),"expectations":len(store.rows("expectations")),
        "reasoning_snapshots":len(store.rows("reasoning_history")),
        "formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False}


if __name__=="__main__":print(json.dumps(materialize(),ensure_ascii=False))
