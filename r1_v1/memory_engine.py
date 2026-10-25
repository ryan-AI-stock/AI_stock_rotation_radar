from __future__ import annotations
from datetime import date
from .ids import stable_id
from .memory_schema import BenchmarkSnapshot,DecisionSnapshot,OutcomeReview

def decision_snapshot(date_,reasoning,state,expected_horizon="MEDIUM"):
    return DecisionSnapshot(stable_id("decision",date_,reasoning["stock_id"],reasoning["reasoning_id"],state["state_id"]),date_,
      reasoning["stock_id"],reasoning["context_snapshot_id"],reasoning["thesis_version"],reasoning.get("leading_hypothesis"),
      reasoning.get("alternative_hypotheses",[]),state["state"],state.get("challenger_stock_id"),state.get("candidate_state","WAIT_FOR_EVIDENCE"),
      reasoning.get("supporting_evidence",[]),reasoning.get("counter_evidence",[]),reasoning.get("unknowns",[]),reasoning.get("confidence","LOW"),
      reasoning.get("falsification_conditions",[]),reasoning.get("next_observation",[]),expected_horizon)

def scheduled_reviews(snapshot:DecisionSnapshot,trading_dates:list[str]):
    later=[d for d in sorted(set(trading_dates)) if d>snapshot.date]
    out=[]
    for horizon in (5,20,60):
        due=later[horizon-1] if len(later)>=horizon else None
        review=OutcomeReview(stable_id("outcome",snapshot.decision_id,horizon),snapshot.decision_id,snapshot.stock_id,horizon,due,None,
          "UNRESOLVED" if due else "DATA_INSUFFICIENT","UNRESOLVED","UNRESOLVED",None,None,[],[],
          [] if due else [f"{horizon}TD_future_observation"])
        review.validate();out.append(review)
    return out

def evaluate_review(review:OutcomeReview,reviewed_at:str,thesis_supported:bool|None,timing_correct:bool|None,
                    price_return:float|None,benchmark_return:float|None,evidence_ids:list[str],data_complete=True):
    if not review.due_date or reviewed_at<review.due_date:raise ValueError("review_before_due")
    if not data_complete or thesis_supported is None:
        result="DATA_INSUFFICIENT";errors=["DATA_GAP"]
    elif thesis_supported and timing_correct is True:result="THESIS_CORRECT_TIMING_CORRECT";errors=[]
    elif thesis_supported:result="THESIS_CORRECT_TIMING_WRONG";errors=["TIMING_ERROR"]
    else:result="THESIS_WRONG";errors=["THESIS_ERROR"]
    out=OutcomeReview(review.review_id,review.decision_id,review.stock_id,review.horizon_td,review.due_date,reviewed_at,result,
      "SUPPORTED" if thesis_supported is True else "REJECTED" if thesis_supported is False else "UNKNOWN",
      "CORRECT" if timing_correct is True else "WRONG" if timing_correct is False else "UNKNOWN",price_return,benchmark_return,errors,evidence_ids,
      [] if data_complete else ["review_evidence"])
    out.validate();return out

def benchmark_registry(date_,values:dict):
    kinds={"0050":"BENCHMARK","00631L":"BENCHMARK","CASH":"BENCHMARK","CANDIDATE_EQUAL_WEIGHT":"BENCHMARK",
           "R1_RESEARCH_PORTFOLIO":"RESEARCH","RYAN_ACTUAL_PORTFOLIO":"ACTUAL"}
    rows=[]
    for key,kind in kinds.items():
        value=values.get(key);row=BenchmarkSnapshot(stable_id("benchmark",date_,key),date_,key,
          value.get("nav") if value else None,value.get("return_since_start") if value else None,kind,
          value.get("source_ids",[]) if value else [],[] if value else ["benchmark_value"])
        row.validate();rows.append(row)
    return rows

