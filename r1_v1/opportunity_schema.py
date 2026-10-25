from __future__ import annotations

from dataclasses import dataclass, field


DIMENSION_STATES={"HOLDING_ADVANTAGE","CHALLENGER_ADVANTAGE","TIE","UNKNOWN"}
OPPORTUNITY_STATES={"NO_ADVANTAGE","WATCH","MODERATE_ADVANTAGE","STRONG_ADVANTAGE","DATA_INSUFFICIENT"}
PORTFOLIO_STATES={"HOLD","WATCH","ADD_REVIEW","TRIM_REVIEW","ROTATION_REVIEW","POSSIBLE_MISPRICING","WAIT_FOR_EVIDENCE"}


@dataclass(frozen=True)
class DimensionAssessment:
    dimension:str; state:str; holding_value:str|float|None; challenger_value:str|float|None
    evidence_ids:list[str]=field(default_factory=list); unknowns:list[str]=field(default_factory=list)
    def validate(self):
        if self.state not in DIMENSION_STATES: raise ValueError("invalid_dimension_state")


@dataclass(frozen=True)
class RelativeOpportunity:
    comparison_id:str; date:str; holding_stock_id:str; challenger_stock_id:str
    dimensions:list[dict]; opportunity_state:str; confidence:str
    challenger_advantages:list[str]; holding_advantages:list[str]
    supporting_evidence_ids:list[str]; counter_evidence_ids:list[str]; unknowns:list[str]
    formal_model_changed:bool=False; trade_decision_changed:bool=False; active_in_trade_decision:bool=False
    def validate(self):
        if self.opportunity_state not in OPPORTUNITY_STATES: raise ValueError("invalid_opportunity_state")
        if self.holding_stock_id==self.challenger_stock_id: raise ValueError("self_comparison")


@dataclass(frozen=True)
class PortfolioResearchState:
    state_id:str; date:str; portfolio_id:str; stock_id:str; state:str; prior_state:str|None
    candidate_state:str; persistence_count:int; hysteresis_required:int; challenger_stock_id:str|None
    comparison_id:str|None; rationale:list[str]; evidence_ids:list[str]; unknowns:list[str]
    formal_model_changed:bool=False; trade_decision_changed:bool=False; active_in_trade_decision:bool=False
    def validate(self):
        if self.state not in PORTFOLIO_STATES or self.candidate_state not in PORTFOLIO_STATES:
            raise ValueError("invalid_portfolio_research_state")
        if self.portfolio_id not in {"R1_RESEARCH_PORTFOLIO","RYAN_ACTUAL_PORTFOLIO_VIEW"}:
            raise ValueError("invalid_portfolio_id")

