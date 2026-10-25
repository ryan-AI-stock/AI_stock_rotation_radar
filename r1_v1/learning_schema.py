from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelChangeProposal:
    proposal_id:str; version:int; created_at:str; status:str; component:str; observed_pattern:str
    proposed_change:str; supporting_review_ids:list[str]; sample_size:int; distinct_dates:int
    historical_validation:str; out_of_sample_validation:str; stability_check:str
    auto_apply:bool=False; formal_model_changed:bool=False; trade_decision_changed:bool=False; active_in_trade_decision:bool=False
    def validate(self):
        if self.status not in {"PROPOSED","DATA_INSUFFICIENT","REJECTED","VALIDATED_NOT_APPLIED"}:raise ValueError("invalid_proposal_status")
        if self.auto_apply:raise ValueError("auto_apply_forbidden")
        if self.status=="PROPOSED" and (self.sample_size<20 or self.distinct_dates<5):raise ValueError("insufficient_learning_sample")

