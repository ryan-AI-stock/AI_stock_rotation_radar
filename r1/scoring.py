from __future__ import annotations

from dataclasses import dataclass


COMPONENTS = ("eps_revision", "forward_valuation", "bottleneck", "catalyst", "price_chip")


@dataclass(frozen=True)
class ScoreResult:
    total_score: float | None
    action_allowed: bool
    missing_components: tuple[str, ...]
    reason: str


def score(*, components: dict[str, float | None], weights: dict[str, float], consensus_allowed: bool) -> ScoreResult:
    missing = tuple(name for name in COMPONENTS if components.get(name) is None)
    if missing:
        return ScoreResult(None, False, missing, "DATA_MISSING")
    if not consensus_allowed:
        return ScoreResult(None, False, (), "CONSENSUS_NOT_ACTIONABLE")
    total = sum(float(components[name]) * float(weights[name]) for name in COMPONENTS)
    return ScoreResult(round(total, 6), True, (), "READY")


def action(
    *, total_score: float | None, core_lock: bool, consensus_allowed: bool,
    eps_revision: float | None, base_upside: float | None, overheat_high: bool,
    thesis_broken: bool, rotation_advantage: float | None, policy_approved: bool = False,
) -> tuple[str, str]:
    if core_lock:
        return "CORE", "CORE_LOCK"
    if not consensus_allowed or total_score is None:
        return "DATA_MISSING", "CONSENSUS_OR_SCORE_NOT_READY"
    if not policy_approved:
        return "WATCH", "ACTION_THRESHOLDS_NOT_APPROVED"
    if thesis_broken or (eps_revision is not None and eps_revision < 0):
        return "EXIT", "THESIS_BROKEN_OR_EPS_REVISION_NEGATIVE"
    if overheat_high:
        return "TRIM", "OVERHEAT_HIGH_NO_NEW_ADD"
    if rotation_advantage is not None and rotation_advantage < 0:
        return "TRIM", "BETTER_ALTERNATIVE"
    if total_score >= 75 and base_upside is not None and base_upside > 0.20:
        return "ADD", "REVISION_VALUATION_AND_UPSIDE_PASS"
    return "KEEP", "NO_MATERIAL_CHANGE"
