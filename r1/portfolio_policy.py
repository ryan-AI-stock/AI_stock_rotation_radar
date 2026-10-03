from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvergenceDecision:
    action: str
    reason: str


def natural_convergence(
    *, holding_count: int, max_holdings: int, core_lock: bool,
    source_deteriorating: bool, replacement_confirmed: bool,
    rotation_advantage: float | None, minimum_advantage: float | None,
) -> ConvergenceDecision:
    """Never force-sell merely because the portfolio is above its final holding limit."""
    if core_lock:
        return ConvergenceDecision("KEEP", "CORE_LOCK")
    if holding_count <= max_holdings:
        return ConvergenceDecision("KEEP", "WITHIN_FINAL_LIMIT")
    if minimum_advantage is None:
        return ConvergenceDecision("WAIT", "ROTATION_THRESHOLD_NOT_APPROVED")
    if rotation_advantage is None:
        return ConvergenceDecision("DATA_MISSING", "ROTATION_ADVANTAGE_MISSING")
    if not source_deteriorating:
        return ConvergenceDecision("KEEP", "SOURCE_NOT_DETERIORATING")
    if not replacement_confirmed:
        return ConvergenceDecision("KEEP", "REPLACEMENT_NOT_CONFIRMED")
    if rotation_advantage < minimum_advantage:
        return ConvergenceDecision("KEEP", "REPLACEMENT_ADVANTAGE_INSUFFICIENT")
    return ConvergenceDecision("TRIM_1", "NATURAL_CONVERGENCE_CONFIRMED")
