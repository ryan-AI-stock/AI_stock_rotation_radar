from __future__ import annotations
from collections import Counter
from .ids import stable_id
from .learning_schema import ModelChangeProposal

def build_change_proposals(reviews:list[dict],created_at:str,min_sample=20,min_dates=5):
    completed=[r for r in reviews if r.get("result") not in {"UNRESOLVED","DATA_INSUFFICIENT"}]
    errors=Counter(e for r in completed for e in r.get("error_taxonomy",[]))
    dates={r.get("reviewed_at") for r in completed if r.get("reviewed_at")}
    if len(completed)<min_sample or len(dates)<min_dates:
        p=ModelChangeProposal(stable_id("proposal",created_at,"readiness"),1,created_at,"DATA_INSUFFICIENT","LEARNING_GATE",
          f"completed_reviews={len(completed)}, distinct_dates={len(dates)}","累積更多跨期Outcome Review後再提出模型變更",[r["review_id"] for r in completed],
          len(completed),len(dates),"PENDING","PENDING","PENDING")
        p.validate();return [p]
    proposals=[]
    for error,count in errors.items():
        if count/max(1,len(completed))<0.30:continue
        p=ModelChangeProposal(stable_id("proposal",created_at,error),1,created_at,"PROPOSED",error,
          f"{error} appears in {count}/{len(completed)} completed reviews",f"研究並驗證降低{error}的challenger規則",
          [r["review_id"] for r in completed if error in r.get("error_taxonomy",[])],len(completed),len(dates),"REQUIRED","REQUIRED","REQUIRED")
        p.validate();proposals.append(p)
    return proposals or [ModelChangeProposal(stable_id("proposal",created_at,"no_pattern"),1,created_at,"DATA_INSUFFICIENT","NO_STABLE_PATTERN",
      "No error category crosses the pre-registered 30% threshold","不變更模型",[r["review_id"] for r in completed],len(completed),len(dates),"PENDING","PENDING","PENDING")]

