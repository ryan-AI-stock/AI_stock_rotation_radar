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
