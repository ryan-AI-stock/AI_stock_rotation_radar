from __future__ import annotations

from collections.abc import Sequence


def percentile_score(values: Sequence[float], current: float | None) -> float | None:
    """Mid-rank percentile on the current eligible R1 cross-section, scaled 0..100."""
    if current is None or not values:
        return None
    clean = [float(value) for value in values]
    below = sum(value < current for value in clean)
    equal = sum(value == current for value in clean)
    return round(100.0 * (below + 0.5 * equal) / len(clean), 6)


def eps_revision_composite(*, revision_1w: float | None, revision_4w: float | None,
                           revision_12w: float | None, policy: dict) -> float | None:
    if any(value is None for value in (revision_1w, revision_4w, revision_12w)):
        return None
    weights = policy["weights"]
    return (float(weights["1w"]) * float(revision_1w)
            + float(weights["4w"]) * float(revision_4w)
            + float(weights["12w"]) * float(revision_12w))


def eps_revision_score(*, revision_1w: float | None, revision_4w: float | None,
                       revision_12w: float | None, eligible_composites: Sequence[float], policy: dict) -> float | None:
    composite = eps_revision_composite(
        revision_1w=revision_1w, revision_4w=revision_4w, revision_12w=revision_12w, policy=policy,
    )
    raw = percentile_score(eligible_composites, composite)
    if raw is None:
        return None
    score = raw
    if float(revision_4w) < 0:
        score = min(score, float(policy["negative_4w_cap"]))
    if float(revision_4w) > 0 and float(revision_12w) > 0:
        score = max(score, float(policy["positive_4w_12w_floor"]))
    if float(revision_4w) < 0 and float(revision_12w) < 0:
        score = min(score, float(policy["double_negative_cap"]))
    return round(score, 6)


def forward_valuation_score(*, own_forward_pe_percentile: float | None,
                            base_upside: float | None, next_year_eps_growth: float | None,
                            eligible_base_upside: Sequence[float],
                            eligible_eps_growth: Sequence[float], policy: dict) -> float | None:
    values = (own_forward_pe_percentile, base_upside, next_year_eps_growth)
    if any(value is None for value in values):
        return None
    percentile = float(own_forward_pe_percentile)
    if not 0 <= percentile <= 1:
        raise ValueError("own_forward_pe_percentile must be 0..1")
    upside_score = percentile_score(eligible_base_upside, base_upside)
    growth_score = percentile_score(eligible_eps_growth, next_year_eps_growth)
    if upside_score is None or growth_score is None:
        return None
    weights = policy["weights"]
    score = (float(weights["own_forward_pe"]) * (1.0 - percentile) * 100.0
             + float(weights["base_upside"]) * upside_score
             + float(weights["next_year_eps_growth"]) * growth_score)
    if float(base_upside) <= 0:
        score = min(score, float(policy["nonpositive_base_upside_cap"]))
    return round(score, 6)


def bottleneck_score(*, stage: str, tightness_score: float | None,
                     financial_proof_score: float | None, evidence_verified: bool, policy: dict) -> float | None:
    if not evidence_verified or tightness_score is None or financial_proof_score is None:
        return None
    stage_scores = policy["stage_scores"]
    if stage not in stage_scores:
        raise ValueError(f"unknown bottleneck stage: {stage}")
    _validate_0_100(tightness_score, financial_proof_score)
    weights = policy["weights"]
    return round(float(weights["stage"]) * float(stage_scores[stage])
                 + float(weights["tightness"]) * tightness_score
                 + float(weights["financial_proof"]) * financial_proof_score, 6)


def catalyst_score(*, positive_decayed_scores: Sequence[float], negative_decayed_scores: Sequence[float],
                   evidence_ready: bool, policy: dict) -> float | None:
    if not evidence_ready:
        return None
    score = float(policy["neutral_score"]) + sum(float(value) for value in positive_decayed_scores) \
        - sum(float(value) for value in negative_decayed_scores)
    return round(max(float(policy["minimum_score"]), min(float(policy["maximum_score"]), score)), 6)


def price_chip_score(*, earnings_vs_price_score: float | None, overheat_safety_score: float | None,
                     institutional_score: float | None, leverage_structure_score: float | None,
                     policy: dict) -> float | None:
    values = (earnings_vs_price_score, overheat_safety_score, institutional_score, leverage_structure_score)
    if any(value is None for value in values):
        return None
    _validate_0_100(*values)
    weights = policy["weights"]
    return round(
        float(weights["earnings_vs_price"]) * float(earnings_vs_price_score)
        + float(weights["overheat_safety"]) * float(overheat_safety_score)
        + float(weights["institutional"]) * float(institutional_score)
        + float(weights["leverage_structure"]) * float(leverage_structure_score),
        6,
    )


def _validate_0_100(*values: float) -> None:
    if any(not 0 <= float(value) <= 100 for value in values):
        raise ValueError("component subscore must be 0..100")
