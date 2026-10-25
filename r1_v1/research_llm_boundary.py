from __future__ import annotations

ALLOWED={"claim_extraction","causal_chain","competing_hypotheses","counter_evidence","unknowns","thesis_comparison","reasoning_summary"}
FORBIDDEN={"fact_without_source","guess_numeric","fill_missing","modify_pit","modify_formal_model","place_order","invent_source","inference_as_fact"}

def validate_research_llm_payload(payload:dict):
    action=payload.get("action")
    if action not in ALLOWED:raise ValueError("llm_action_forbidden")
    if payload.get("source_ids") is None:raise ValueError("trace_missing")
    if payload.get("writes_fact") or payload.get("trade_instruction") or payload.get("auto_apply"):
        raise ValueError("llm_boundary_violation")
    if payload.get("classification") in {"INFERENCE","HYPOTHESIS","JUDGMENT"} and payload.get("as_fact"):
        raise ValueError("inference_as_fact")
    return True

