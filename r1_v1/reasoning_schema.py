from __future__ import annotations

from dataclasses import dataclass, field


THESIS_TYPES={"STRUCTURAL_THESIS","EARNINGS_THESIS","VALUATION_THESIS","CATALYST_THESIS","RISK_THESIS"}
THESIS_STATES={"STRENGTHENED","UNCHANGED","WEAKENED","BROKEN","UNKNOWN"}
CHAIN_STATES={"CONFIRMED","INFERENCE","UNKNOWN","CONTRADICTED"}
HYPOTHESIS_STATES={"ACTIVE","STRENGTHENING","WEAKENING","REJECTED","CONFIRMED","UNRESOLVED"}
HORIZONS={"SHORT","MEDIUM","STRUCTURAL"}


@dataclass(frozen=True)
class ThesisRecord:
    thesis_id:str; stock_id:str; effective_from:str; effective_to:str|None
    thesis_version:int; thesis_type:str; thesis_summary:str; expected_horizon:str
    status:str; last_reviewed_at:str; key_drivers:list[str]; key_risks:list[str]
    invalidation_conditions:list[str]; supporting_evidence_ids:list[str]
    contradicting_evidence_ids:list[str]; unknowns:list[str]
    changed_by_evidence_ids:list[str]=field(default_factory=list)
    coverage_status:str="LEGACY_PARTIAL"

    def validate(self):
        if self.thesis_type not in THESIS_TYPES: raise ValueError("invalid_thesis_type")
        if self.status not in THESIS_STATES: raise ValueError("invalid_thesis_state")
        if self.expected_horizon not in HORIZONS: raise ValueError("invalid_thesis_horizon")


@dataclass(frozen=True)
class CausalNode:
    node_id:str; thesis_id:str; sequence:int; statement:str; status:str
    evidence_ids:list[str]; last_updated:str; confidence:str


@dataclass(frozen=True)
class CausalEdge:
    edge_id:str; thesis_id:str; from_node_id:str; to_node_id:str; status:str
    evidence_ids:list[str]; last_updated:str; confidence:str


@dataclass(frozen=True)
class HypothesisRecord:
    hypothesis_id:str; stock_id:str; event_id:str|None; context_snapshot_id:str
    hypothesis_type:str; statement:str; status:str; confidence:str; time_horizon:str
    created_at:str; last_updated:str; supporting_evidence_ids:list[str]
    contradicting_evidence_ids:list[str]; missing_evidence:list[str]
    falsification_conditions:list[str]; expected_resolution_window:str
    evidence_lineages:list[str]=field(default_factory=list)

    def validate(self):
        if self.status not in HYPOTHESIS_STATES: raise ValueError("invalid_hypothesis_state")
        if self.confidence not in {"LOW","MEDIUM","HIGH"}: raise ValueError("invalid_confidence")
        if self.time_horizon not in HORIZONS: raise ValueError("invalid_hypothesis_horizon")


@dataclass(frozen=True)
class ExpectationAnalysis:
    expectation_id:str; stock_id:str; event_id:str|None; expected_state:str|None
    actual_state:str|None; difference:str; source_ids:list[str]; confidence:str
    evaluation_time:str; unknowns:list[str]


@dataclass(frozen=True)
class DisconfirmationPass:
    pass_id:str; hypothesis_id:str; conflicting_evidence:list[str]
    simpler_alternative:str; market_company_confusion_risk:str
    correlation_causation_risk:str; price_in_risk:str; most_likely_failure:str
    traceable_evidence_ids:list[str]; created_at:str


@dataclass(frozen=True)
class ReasoningSnapshot:
    reasoning_id:str; date:str; stock_id:str; context_snapshot_id:str
    thesis_version:int; thesis_state:str; active_hypotheses:list[str]
    leading_hypothesis:str|None; alternative_hypotheses:list[str]
    supporting_evidence:list[str]; counter_evidence:list[str]; unknowns:list[str]
    confidence:str; falsification_conditions:list[str]; next_observation:list[str]
    reasoning_change:str; disconfirmation_pass_id:str|None
    formal_model_changed:bool=False; trade_decision_changed:bool=False
    active_in_trade_decision:bool=False

    def validate(self):
        if self.reasoning_change not in {"UNCHANGED","UPGRADED","DOWNGRADED","REVERSED"}:
            raise ValueError("invalid_reasoning_change")
        text=str(self).upper()
        for token in (" BUY "," SELL "," ADD "," TRIM "):
            if token in f" {text} ": raise ValueError("trade_output_forbidden")
