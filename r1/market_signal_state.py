from __future__ import annotations

from dataclasses import dataclass


def eps_state(revision_4w: float | None) -> str:
    if revision_4w is None:
        return "DATA_MISSING"
    if revision_4w > 0:
        return "REVISING_UP"
    if revision_4w < 0:
        return "REVISING_DOWN"
    return "STABLE"


def flow_state(flow_5d: float | None, flow_20d: float | None) -> str:
    if flow_5d is None or flow_20d is None:
        return "DATA_MISSING"
    if flow_5d > 0 and flow_20d > 0:
        return "ACCUMULATING"
    if flow_5d < 0 and flow_20d < 0:
        return "DISTRIBUTING"
    return "NEUTRAL"


def valuation_state(
    *, forward_pe_change: float | None, base_upside_change: float | None,
) -> str:
    if forward_pe_change is None or base_upside_change is None:
        return "DATA_MISSING"
    if forward_pe_change < 0 and base_upside_change > 0:
        return "CHEAPENING"
    if forward_pe_change > 0 and base_upside_change < 0:
        return "EXPANDING"
    return "FAIR"


@dataclass(frozen=True)
class TrendConfirmation:
    stage: str
    confidence: str
    consecutive_weeks: int


def confirm_eps_trend(states: list[str]) -> TrendConfirmation:
    usable = [state for state in states if state != "DATA_MISSING"]
    if not usable:
        return TrendConfirmation("WAIT", "LOW", 0)
    latest = usable[-1]
    consecutive = 0
    for state in reversed(usable):
        if state != latest:
            break
        consecutive += 1
    if latest == "REVISING_DOWN":
        confidence = "HIGH" if consecutive >= 4 else "MEDIUM" if consecutive >= 2 else "LOW"
        return TrendConfirmation("DETERIORATING", confidence, consecutive)
    if latest == "STABLE":
        return TrendConfirmation("WAIT", "LOW", consecutive)
    if consecutive >= 4:
        return TrendConfirmation("CONFIRMED", "HIGH", consecutive)
    if consecutive >= 2:
        return TrendConfirmation("CONFIRMING", "MEDIUM", consecutive)
    return TrendConfirmation("EARLY_SIGNAL", "LOW", 1)
