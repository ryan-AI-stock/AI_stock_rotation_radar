from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverheatAssessment:
    risk: str
    evidence_count: int
    reasons: tuple[str, ...]
    add_blocked: bool


def assess_overheat(*, bias60_percentile: float | None, forward_pe_percentile: float | None,
                    eps_revision_4w: float | None, eps_revision_12w: float | None,
                    high_percentile: float) -> OverheatAssessment:
    """Classify evidence without embedding an unapproved trading threshold."""
    values = (bias60_percentile, forward_pe_percentile, eps_revision_4w, eps_revision_12w)
    if any(value is None for value in values):
        return OverheatAssessment("DATA_MISSING", 0, ("OVERHEAT_INPUT_MISSING",), False)
    if not 0 < high_percentile < 1:
        raise ValueError("high_percentile must be between 0 and 1")
    reasons: list[str] = []
    if bias60_percentile >= high_percentile:
        reasons.append("BIAS60_SELF_PERCENTILE_HIGH")
    if forward_pe_percentile >= high_percentile:
        reasons.append("FORWARD_PE_SELF_PERCENTILE_HIGH")
    if eps_revision_4w <= eps_revision_12w:
        reasons.append("EPS_REVISION_NOT_ACCELERATING")
    count = len(reasons)
    risk = "HIGH" if count == 3 else "MEDIUM" if count == 2 else "LOW"
    return OverheatAssessment(risk, count, tuple(reasons), risk == "HIGH")
