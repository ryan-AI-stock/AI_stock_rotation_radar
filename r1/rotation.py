from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RotationOrder:
    ticker: str
    current_value: float
    target_value: float
    uncapped_transfer: float
    suggested_transfer: float


@dataclass(frozen=True)
class RotationComparison:
    source_ticker: str
    target_ticker: str
    score_advantage: float | None
    eps_revision_4w_advantage: float | None
    base_upside_advantage: float | None
    price_eps_gap_4w_advantage: float | None
    decision: str
    reason: str


def compare_rotation_pair(
    *, source: dict, target: dict, minimum_score_advantage: float | None = None,
) -> RotationComparison:
    fields = ("total_score", "eps_revision_4w", "base_upside", "price_eps_gap_4w")
    if any(source.get(field) is None or target.get(field) is None for field in fields):
        return RotationComparison(
            str(source.get("ticker", "")), str(target.get("ticker", "")),
            None, None, None, None, "DATA_MISSING", "PAIRWISE_INPUT_MISSING",
        )
    comparison = RotationComparison(
        str(source["ticker"]), str(target["ticker"]),
        float(target["total_score"]) - float(source["total_score"]),
        float(target["eps_revision_4w"]) - float(source["eps_revision_4w"]),
        float(target["base_upside"]) - float(source["base_upside"]),
        float(target["price_eps_gap_4w"]) - float(source["price_eps_gap_4w"]),
        "WAIT", "ROTATION_THRESHOLD_NOT_APPROVED",
    )
    if minimum_score_advantage is None:
        return comparison
    if comparison.score_advantage >= minimum_score_advantage:
        return RotationComparison(
            **{**comparison.__dict__, "decision": "ROTATION_CANDIDATE", "reason": "TARGET_ADVANTAGE_PASSES"}
        )
    return RotationComparison(
        **{**comparison.__dict__, "decision": "KEEP_SOURCE", "reason": "TARGET_ADVANTAGE_INSUFFICIENT"}
    )


def build_rotation_orders(
    *, current_values: dict[str, float], target_weights: dict[str, float],
    managed_value: float, max_weekly_rotation: float, core_locked: set[str],
) -> list[RotationOrder]:
    if abs(sum(target_weights.values()) - 1.0) > 1e-9:
        raise ValueError("target weights must sum to 1.0")
    if any(ticker in target_weights for ticker in core_locked):
        raise ValueError("CORE_LOCK ticker cannot participate in managed target weights")
    limit = managed_value * max_weekly_rotation
    raw = {}
    for ticker in set(current_values) | set(target_weights):
        if ticker in core_locked:
            continue
        current = float(current_values.get(ticker, 0.0))
        target = managed_value * float(target_weights.get(ticker, 0.0))
        raw[ticker] = target - current
    gross_buys = sum(max(0.0, value) for value in raw.values())
    gross_sells = sum(max(0.0, -value) for value in raw.values())
    scale = min(1.0, limit / max(gross_buys, gross_sells)) if max(gross_buys, gross_sells) else 1.0
    return [
        RotationOrder(
            ticker=ticker,
            current_value=float(current_values.get(ticker, 0.0)),
            target_value=managed_value * float(target_weights.get(ticker, 0.0)),
            uncapped_transfer=gap,
            suggested_transfer=gap * scale,
        )
        for ticker, gap in sorted(raw.items())
    ]
