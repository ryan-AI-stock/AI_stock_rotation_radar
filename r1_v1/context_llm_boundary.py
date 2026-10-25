from __future__ import annotations

from typing import Any


FORBIDDEN = {"buy", "sell", "add", "trim", "target_weight", "position", "thesis",
             "market_state_override", "numeric_override"}


def validate_context_narrative(payload: dict[str, Any]) -> dict[str, Any]:
    overlap = FORBIDDEN & {str(k).lower() for k in payload}
    if overlap: raise ValueError(f"context_llm_forbidden:{','.join(sorted(overlap))}")
    allowed = {"primary_reason", "secondary_reason", "supporting_evidence",
               "contradicting_evidence", "unknowns", "traceable_evidence_ids"}
    extra = set(payload)-allowed
    if extra: raise ValueError(f"context_llm_unknown_fields:{','.join(sorted(extra))}")
    if not payload.get("traceable_evidence_ids"):
        raise ValueError("context_llm_trace_missing")
    return dict(payload)
