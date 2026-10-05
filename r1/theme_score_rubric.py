from __future__ import annotations

import json
from pathlib import Path

from r1.theme_policy import LEADER_WEIGHTS, PRIORITY_WEIGHTS


def load_and_validate(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != "r1-theme-score-rubric-v0.1":
        raise ValueError("R1 score rubric version mismatch")
    principles = payload.get("principles", {})
    if principles.get("missing_value") != "NA_NO_ZERO_NO_REWEIGHT":
        raise ValueError("R1 missing values must remain NA")
    if principles.get("future_data_forbidden") is not True:
        raise ValueError("R1 rubric must forbid future data")
    if principles.get("automatic_trade_enabled") is not False:
        raise ValueError("R1 v0.3 cannot enable automatic trading")
    _validate_section(payload.get("quarterly", {}), LEADER_WEIGHTS, "quarterly")
    _validate_section(payload.get("daily", {}), PRIORITY_WEIGHTS, "daily")
    levels = payload["quarterly"]["bottleneck_directness"].get("levels", {})
    if set(levels) != {"0", "25", "50", "75", "100"}:
        raise ValueError("R1 bottleneck evidence ladder must use fixed 0/25/50/75/100 levels")
    return payload


def _validate_section(section: dict, expected_weights: dict[str, float], label: str) -> None:
    if set(section) != set(expected_weights):
        raise ValueError(f"R1 {label} rubric fields do not match canonical score fields")
    weights = {field: float(row.get("weight")) for field, row in section.items()}
    if any(abs(weights[field] - expected_weights[field]) > 1e-9 for field in expected_weights):
        raise ValueError(f"R1 {label} rubric weights do not match canonical weights")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"R1 {label} rubric weights must sum to 1")
    for field, row in section.items():
        subweights = row.get("subweights")
        if subweights and abs(sum(float(value) for value in subweights.values()) - 1.0) > 1e-9:
            raise ValueError(f"R1 {label} {field} subweights must sum to 1")
