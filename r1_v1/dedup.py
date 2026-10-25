from __future__ import annotations

from datetime import date
import re
from typing import Any

from .ids import normalize_text, stable_id


def event_fingerprint(*, entity: str, event_type: str, event_date: str,
                      product: str | None, customer: str | None,
                      numbers: list[str] | None) -> str:
    return stable_id(
        "efp", normalize_text(entity), normalize_text(event_type), event_date,
        normalize_text(product), normalize_text(customer), sorted(numbers or []),
    )


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"\s+", normalize_text(value)) if len(token) >= 2}


def compare_events(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, auditable candidate matching; semantic similarity alone cannot merge."""
    reasons: list[str] = []
    hard_conflict = False
    if normalize_text(left.get("primary_entity")) == normalize_text(right.get("primary_entity")):
        reasons.append("SAME_ENTITY")
    else:
        hard_conflict = True
    if left.get("event_type") == right.get("event_type"):
        reasons.append("SAME_EVENT_TYPE")
    else:
        hard_conflict = True
    distance = abs((date.fromisoformat(left["event_date"]) - date.fromisoformat(right["event_date"])).days)
    if distance <= 3:
        reasons.append("DATE_WITHIN_3D")
    else:
        hard_conflict = True
    left_numbers, right_numbers = set(left.get("numbers") or []), set(right.get("numbers") or [])
    if left_numbers and right_numbers:
        if left_numbers & right_numbers:
            reasons.append("NUMBER_OVERLAP")
        else:
            hard_conflict = True
    for field, label in (("product", "SAME_PRODUCT"), ("customer", "SAME_CUSTOMER")):
        lv, rv = normalize_text(left.get(field)), normalize_text(right.get(field))
        if lv and rv and lv == rv:
            reasons.append(label)
    if left.get("primary_lineage_id") and left.get("primary_lineage_id") == right.get("primary_lineage_id"):
        reasons.append("SAME_PRIMARY_LINEAGE")
    lt, rt = _tokens(left.get("normalized_summary", "")), _tokens(right.get("normalized_summary", ""))
    similarity = len(lt & rt) / len(lt | rt) if lt | rt else 0.0
    if similarity >= 0.65:
        reasons.append("TEXT_SIMILARITY_GE_065")
    rule_points = len([r for r in reasons if r != "TEXT_SIMILARITY_GE_065"])
    if not hard_conflict and rule_points >= 4:
        decision = "MERGE"
    elif not hard_conflict and rule_points >= 2:
        decision = "POSSIBLE_DUPLICATE"
    else:
        decision = "DISTINCT"
    return {"decision": decision, "reasons": reasons, "date_distance_days": distance,
            "text_similarity": round(similarity, 6), "hard_conflict": hard_conflict}
