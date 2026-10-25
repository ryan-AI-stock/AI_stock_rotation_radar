from __future__ import annotations
import json
from pathlib import Path

def _rows(path):
    p=Path(path);return [] if not p.exists() else [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def audit(root="data/r1_v1"):
    root=Path(root);source_rows=_rows(root/"sources.jsonl");sources={x["source_id"] for x in source_rows}
    contexts=_rows(root/"context_history.jsonl");reasoning=_rows(root/"reasoning/reasoning_history.jsonl")
    decisions=_rows(root/"research/decision_snapshots.jsonl");reviews=_rows(root/"research/outcome_reviews.jsonl")
    proposals=_rows(root/"research/model_change_proposals.jsonl");benchmarks=_rows(root/"research/benchmark_snapshots.jsonl")
    checks={
      "pit_no_future_sources":all(x.get("pit_valid") is True and x.get("available_at","")[:10]<=x.get("retrieved_at","")[:10] and x.get("published_at","")[:10]<=x.get("retrieved_at","")[:10] for x in source_rows),
      "context_has_lineage":all("snapshot_id" in x for x in contexts),
      "reasoning_has_counter_field":all("counter_evidence" in x for x in reasoning),
      "thesis_has_invalidation":all(x.get("falsification_conditions") for x in reasoning),
      "unknown_preserved":all("unknowns" in x for x in contexts+reasoning+decisions),
      "snapshots_unique":len({x["decision_id"] for x in decisions})==len(decisions),
      "reviews_5_20_60":all({x["horizon_td"] for x in reviews if x["decision_id"]==d["decision_id"]}=={5,20,60} for d in decisions),
      "learning_never_auto_applies":all(not x.get("auto_apply") for x in proposals),
      "portfolio_benchmarks_separate":{x["benchmark_id"] for x in benchmarks}=={"0050","00631L","CASH","CANDIDATE_EQUAL_WEIGHT","R1_RESEARCH_PORTFOLIO","RYAN_ACTUAL_PORTFOLIO"},
      "formal_flags_false":all(not x.get("formal_model_changed",False) and not x.get("trade_decision_changed",False) and not x.get("active_in_trade_decision",False) for x in decisions+proposals),
    }
    return {"passed":all(checks.values()),"checks":checks,"counts":{"sources":len(sources),"contexts":len(contexts),"reasoning":len(reasoning),"decisions":len(decisions),"reviews":len(reviews),"proposals":len(proposals)}}

if __name__=="__main__":print(json.dumps(audit(),ensure_ascii=False,indent=2))
