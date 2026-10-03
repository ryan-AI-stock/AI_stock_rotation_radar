from __future__ import annotations

from r1.portfolio_policy import natural_convergence
from r1.rotation import compare_rotation_pair


def evaluate_shadow_rotation(*, source: dict, target: dict, policy: dict,
                             holding_count: int) -> dict:
    comparison = compare_rotation_pair(
        source=source, target=target,
        minimum_score_advantage=float(policy["minimum_score_advantage"]),
    )
    if comparison.decision == "DATA_MISSING":
        return {"status": "DATA_MISSING", "reason": comparison.reason,
                "source": comparison.source_ticker, "target": comparison.target_ticker}
    convergence = natural_convergence(
        holding_count=holding_count, max_holdings=int(policy["max_holdings"]),
        core_lock=bool(source.get("core_lock")),
        source_deteriorating=source.get("signal_stage") == policy["source_signal_stage"],
        replacement_confirmed=target.get("signal_stage") == policy["target_signal_stage"],
        rotation_advantage=comparison.score_advantage,
        minimum_advantage=float(policy["minimum_score_advantage"]),
    )
    return {
        "status": convergence.action,
        "reason": convergence.reason,
        "source": comparison.source_ticker,
        "target": comparison.target_ticker,
        "score_advantage": comparison.score_advantage,
        "staged_transfer_fraction": float(policy["staged_transfer_fraction"]),
        "weekly_rotation_cap": float(policy["max_weekly_rotation"]),
        "shadow_only": True,
    }
