from __future__ import annotations
from dataclasses import dataclass,field

OUTCOMES={"THESIS_CORRECT_TIMING_CORRECT","THESIS_CORRECT_TIMING_WRONG","THESIS_WRONG","DATA_INSUFFICIENT","UNRESOLVED"}
ERRORS={"SOURCE_ERROR","EVENT_CLASSIFICATION_ERROR","CAUSAL_CHAIN_ERROR","EXPECTATION_ERROR","VALUATION_ERROR","TIMING_ERROR","THESIS_ERROR","DATA_GAP","MARKET_REGIME_ERROR"}

@dataclass(frozen=True)
class DecisionSnapshot:
    decision_id:str; date:str; stock_id:str; context_snapshot_id:str; thesis_version:int
    leading_hypothesis:str|None; alternative_hypotheses:list[str]; portfolio_research_state:str
    challenger_stock_id:str|None; rotation_state:str; supporting_evidence:list[str]
    counter_evidence:list[str]; unknowns:list[str]; confidence:str; invalidation:list[str]
    next_observation:list[str]; expected_horizon:str; portfolio_id:str="R1_RESEARCH_PORTFOLIO"
    formal_model_changed:bool=False; trade_decision_changed:bool=False; active_in_trade_decision:bool=False

@dataclass(frozen=True)
class OutcomeReview:
    review_id:str; decision_id:str; stock_id:str; horizon_td:int; due_date:str|None
    reviewed_at:str|None; result:str; thesis_evidence_result:str; timing_result:str
    price_return:float|None; benchmark_return:float|None; error_taxonomy:list[str]
    evidence_ids:list[str]; unknowns:list[str]
    def validate(self):
        if self.result not in OUTCOMES:raise ValueError("invalid_outcome")
        if set(self.error_taxonomy)-ERRORS:raise ValueError("invalid_error_taxonomy")

@dataclass(frozen=True)
class BenchmarkSnapshot:
    benchmark_snapshot_id:str; date:str; benchmark_id:str; nav:float|None; return_since_start:float|None
    portfolio_kind:str; source_ids:list[str]; unknowns:list[str]=field(default_factory=list)
    def validate(self):
        allowed={"0050","00631L","CASH","CANDIDATE_EQUAL_WEIGHT","R1_RESEARCH_PORTFOLIO","RYAN_ACTUAL_PORTFOLIO"}
        if self.benchmark_id not in allowed:raise ValueError("invalid_benchmark")
        if self.portfolio_kind not in {"BENCHMARK","RESEARCH","ACTUAL"}:raise ValueError("invalid_portfolio_kind")

