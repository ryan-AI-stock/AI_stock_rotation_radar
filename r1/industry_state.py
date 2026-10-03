from __future__ import annotations


STAGE_ORDER = {
    "THESIS": 1, "QUALIFICATION": 2, "SAMPLE": 3, "TAPE_OUT": 4,
    "SMALL_VOLUME": 5, "MASS_PRODUCTION": 6, "FINANCIAL_PROOF": 7,
}


def bottleneck_state(current_stage: str | None, prior_stage: str | None) -> str:
    if current_stage not in STAGE_ORDER:
        return "DATA_MISSING"
    if prior_stage not in STAGE_ORDER:
        return "STABLE"
    if STAGE_ORDER[current_stage] > STAGE_ORDER[prior_stage]:
        return "STRENGTHENING"
    if STAGE_ORDER[current_stage] < STAGE_ORDER[prior_stage]:
        return "EASING"
    return "STABLE"


def catalyst_state(*, directions: list[str], source_families: set[str]) -> str:
    if not directions:
        return "DATA_MISSING"
    normalized = {value.upper() for value in directions}
    if normalized & {"DOWN", "NEGATIVE"}:
        return "NEGATIVE"
    if len(source_families) >= 2:
        return "CONFIRMING"
    return "NEW"
