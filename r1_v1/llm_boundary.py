from __future__ import annotations

from typing import Any


FORBIDDEN_KEYS = {"fact", "facts", "fact_id", "trade", "buy", "sell", "position",
                  "target_weight", "recommendation"}


def validate_llm_claim_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM may extract/phrase a claim, but may not create Facts or trading actions."""
    overlap = FORBIDDEN_KEYS & set(payload)
    if overlap:
        raise ValueError(f"llm_boundary_forbidden_keys:{','.join(sorted(overlap))}")
    required = {"claim_text", "claim_type", "direction", "scope", "time_horizon",
                "confidence", "traceable_source_id"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"llm_claim_fields_missing:{','.join(sorted(missing))}")
    if not payload.get("traceable_source_id"):
        raise ValueError("llm_claim_source_missing")
    return dict(payload)

