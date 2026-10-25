from __future__ import annotations


FORBIDDEN={"fact","source","buy","sell","add","trim","weight","position","numeric_override","formal_thesis_update"}


def validate_reasoning_llm_payload(payload:dict)->dict:
    overlap=FORBIDDEN&{str(k).lower() for k in payload}
    if overlap: raise ValueError(f"reasoning_llm_forbidden:{','.join(sorted(overlap))}")
    if not payload.get("traceable_evidence_ids"): raise ValueError("reasoning_llm_trace_missing")
    allowed={"candidate_hypotheses","causal_chain_draft","supporting_evidence_ids",
             "counter_evidence_ids","missing_evidence","thesis_comparison","expectation_gap",
             "disconfirmation_pass","traceable_evidence_ids"}
    extra=set(payload)-allowed
    if extra: raise ValueError(f"reasoning_llm_unknown_fields:{','.join(sorted(extra))}")
    return dict(payload)
