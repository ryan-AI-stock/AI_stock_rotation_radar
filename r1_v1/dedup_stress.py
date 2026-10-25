from __future__ import annotations

import json
from pathlib import Path

from .ids import stable_id
from .pipeline import EvidencePipeline
from .schema import EvidenceSource
from .store import EvidenceStore


def run_stress(cases_path: str | Path, output_root: str | Path) -> dict:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))["cases"]
    store = EvidenceStore(output_root)
    pipe = EvidencePipeline(store, "2026-10-25T23:59:59", actor="dedup_real_world_stress")
    results=[]
    for case in cases:
        primary_id=stable_id("stress-source", case["primary"]["url"])
        sources=[case["primary"], *case["secondary"]]
        event_ids=[]; claim_ids=[]
        for index, raw in enumerate(sources):
            sid=stable_id("stress-source", raw["url"])
            source=EvidenceSource(sid, raw["family"], raw["family"], raw["url"],
                case["event_date"], case["event_date"], "2026-10-25",
                "OFFICIAL" if index==0 else "TIER1_NEWS", True,
                primary_source_id=primary_id)
            event_id, claim_id, _=pipe.add_event_claim(source=source,
                event_input={"event_type":case["event_type"], "primary_entity":case["ticker"],
                    "related_entities":[], "event_date":case["event_date"],
                    "numbers":case["numbers"], "normalized_summary":case["summary"]},
                claim_input={"claim_text":case["summary"]+("" if index==0 else f"（{raw['family']}轉述）"),
                    "claim_type":"FACTUAL_CLAIM", "direction":"POSITIVE", "scope":"COMPANY",
                    "time_horizon":"MEDIUM", "confidence":"HIGH" if index==0 else "MEDIUM"})
            event_ids.append(event_id); claim_ids.append(claim_id)
        event_rows=[e for e in store.rows("events") if e["event_id"] in event_ids]
        canonical={e["canonical_event_id"] for e in event_rows}
        independent={store.independent_evidence_count(cid) for cid in claim_ids}
        results.append({"case_id":case["case_id"], "source_count":len(sources),
            "canonical_event_count":len(canonical), "claim_count":len(claim_ids),
            "independent_evidence_counts":sorted(independent),
            "passed":len(canonical)==1 and independent=={1}})
    payload={"status":"PASS" if all(r["passed"] for r in results) else "FAIL", "cases":results,
             "formal_model_changed":False,"trade_decision_changed":False,
             "active_in_trade_decision":False,"report_changed":False}
    Path(output_root,"stress_summary.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_stress("data/r1_v1/dedup_stress_cases.json",
                                "data/r1_v1/dedup_stress"), ensure_ascii=False))
