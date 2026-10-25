from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .store import EvidenceStore


def build_monitor(store: EvidenceStore, output: str | Path) -> dict:
    sources, events = store.rows("sources"), store.rows("events")
    claims, links = store.rows("claims"), store.rows("claim_evidence_links")
    rejections = store.rows("rejections")
    payload = {
        "status": "RESEARCH_DEBUG_ONLY",
        "counts": store.counts(),
        "raw_event_observations": len(events),
        "canonical_events": len(store.canonical_events()),
        "source_classes": dict(sorted(Counter(s["reliability_class"] for s in sources).items())),
        "event_statuses": dict(sorted(Counter(e["status"] for e in events).items())),
        "claim_types": dict(sorted(Counter(c["claim_type"] for c in claims).items())),
        "evidence_stances": dict(sorted(Counter(l["stance"] for l in links).items())),
        "future_data_violations": sum(r["reason"] == "FUTURE_DATA_VIOLATION" for r in rejections),
        "data_missing": sum(r["reason"] == "DATA_MISSING" for r in rejections),
        "possible_duplicates": sum(e["status"] == "POSSIBLE_DUPLICATE" for e in events),
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
