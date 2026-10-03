from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StagedDecision:
    stage: str
    reason: str


def next_staged_action(
    *, prior_stage: str, thesis_broken: bool, deteriorating: bool,
    target_confirmed: bool, add_supported: bool,
) -> StagedDecision:
    if thesis_broken:
        return StagedDecision("EXIT", "THESIS_BROKEN")
    if deteriorating:
        if prior_stage == "TRIM_2":
            return StagedDecision("EXIT", "DETERIORATION_CONTINUES_AFTER_TRIM_2")
        if prior_stage == "TRIM_1":
            return StagedDecision("TRIM_2", "DETERIORATION_CONTINUES_AFTER_TRIM_1")
        return StagedDecision("TRIM_1", "DETERIORATION_FIRST_CONFIRMED")
    if not target_confirmed:
        return StagedDecision("WATCH", "TARGET_TREND_NOT_CONFIRMED")
    if not add_supported:
        return StagedDecision("KEEP", "VALUATION_OR_UPSIDE_NOT_SUPPORTIVE")
    if prior_stage == "ADD_1":
        return StagedDecision("ADD_2", "CONFIRMED_TREND_CONTINUES")
    if prior_stage == "ADD_2":
        return StagedDecision("FULL_POSITION", "CONFIRMED_TREND_AND_VALUATION_CONTINUE")
    return StagedDecision("ADD_1", "FIRST_CONFIRMED_ENTRY")


def dynamic_triggers(*, eps_state: str, valuation_state: str, flow_state: str,
                     bottleneck_state: str, catalyst_state: str) -> dict[str, str]:
    return {
        "next_add_trigger": (
            "EPS維持上修＋估值未擴張＋瓶頸未緩解＋趨勢達CONFIRMING以上"
        ),
        "next_trim_trigger": (
            "EPS停止上修或下修＋估值持續擴張＋籌碼轉為DISTRIBUTING"
        ),
        "next_exit_trigger": (
            "EPS連續下修＋瓶頸BROKEN，或催化事件轉NEGATIVE"
        ),
        "current_trigger_inputs": (
            f"EPS={eps_state};VALUATION={valuation_state};FLOW={flow_state};"
            f"BOTTLENECK={bottleneck_state};CATALYST={catalyst_state}"
        ),
    }
