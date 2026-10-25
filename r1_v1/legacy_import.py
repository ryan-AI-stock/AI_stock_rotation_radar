from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .ids import stable_id
from .monitor import build_monitor
from .pipeline import EvidencePipeline
from .schema import EvidenceSource, Fact
from .store import EvidenceStore, now_iso


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _source(*, url: str, family: str, available: str, retrieved: str,
            published: str | None = None) -> EvidenceSource:
    family_lower = family.lower()
    if "mops" in family_lower or "twse" in family_lower:
        klass = "EXCHANGE_MOPS"
    elif family_lower.endswith("_ir") or "official" in family_lower:
        klass = "OFFICIAL"
    elif any(x in family_lower for x in ("trendforce", "research", "consensus", "toalpha")):
        klass = "INDUSTRY_RESEARCH"
    else:
        klass = "GENERAL_MEDIA"
    source_id = stable_id("source", url, available, family)
    return EvidenceSource(source_id, family, family, url, published or available,
                          available, retrieved, klass, True,
                          primary_source_id=stable_id("lineage", url.split("?")[0]))


def import_legacy(repo: str | Path, output: str | Path, evaluation_time: str) -> dict[str, int]:
    repo, output = Path(repo), Path(output)
    store = EvidenceStore(output)
    pipe = EvidencePipeline(store, evaluation_time, actor="r1_v1_legacy_shadow_import")
    created_at = now_iso()

    monthly = repo / "data/r1/monthly_revenue/latest.json"
    if monthly.exists():
        payload = json.loads(monthly.read_text(encoding="utf-8"))
        for company in payload.get("rows", []):
            for obs in company.get("observations", []):
                available = obs["available_date"]
                source = _source(url=obs["source_url"], family=obs.get("source_type", "mops"),
                                 available=available, retrieved=payload.get("date", available))
                pipe.add_source(source)
                revision_id = stable_id("revision", obs["ticker"], "monthly_revenue_twd",
                                        obs["revenue_year_month"], available, obs["revenue_twd"])
                fact = Fact(fact_id=stable_id("fact", revision_id), entity_type="COMPANY",
                    entity_id=obs["ticker"], metric="monthly_revenue_twd",
                    value=obs["revenue_twd"], unit="TWD", period=obs["revenue_year_month"],
                    source_id=source.source_id, source_url=source.source_url,
                    source_date=available, published_at=source.published_at,
                    available_at=available, retrieved_at=source.retrieved_at,
                    revision_id=revision_id, previous_revision_id=None,
                    pit_valid=True, created_at=created_at, fact_kind="ACTUAL",
                    migration_status="LEGACY_PARTIAL")
                pipe.add_fact(fact)

    consensus_previous: dict[tuple[str, str, str], str] = {}
    for row in _rows(repo / "data/r1/consensus/consensus.csv"):
        if row.get("status") != "READY" or not row.get("mean_eps"):
            continue
        url = f"legacy://r1/consensus/{row['source'].replace(' ', '_')}"
        source = _source(url=url, family=row["source"], available=row["available_at"],
                         retrieved=row["retrieved_at"], published=row["published_at"])
        pipe.add_source(source)
        revision_id = stable_id("revision", row["ticker"], "eps_consensus_mean",
                                row["fiscal_year"], row["available_at"], row["mean_eps"])
        logical_key = (row["ticker"], row["fiscal_year"], row["source"])
        fact = Fact(fact_id=stable_id("fact", revision_id), entity_type="COMPANY",
            entity_id=row["ticker"], metric="eps_consensus_mean", value=float(row["mean_eps"]),
            unit="TWD_PER_SHARE", period=row["fiscal_year"], source_id=source.source_id,
            source_url=source.source_url, source_date=row["published_at"],
            published_at=row["published_at"], available_at=row["available_at"],
            retrieved_at=row["retrieved_at"], revision_id=revision_id, pit_valid=True,
            created_at=created_at, fact_kind="CONSENSUS", migration_status="LEGACY_PARTIAL")
        fact = Fact(**{**fact.__dict__, "previous_revision_id": consensus_previous.get(logical_key)})
        pipe.add_fact(fact)
        consensus_previous[logical_key] = revision_id

    for row in _rows(repo / "data/r1/catalyst_events/evidence.csv"):
        source = _source(url=row["source_url"], family=row["source_family"],
                         available=row["available_at"], retrieved=row["retrieved_at"],
                         published=row.get("published_at"))
        direction = {"UP": "POSITIVE", "DOWN": "NEGATIVE"}.get(row.get("impact_direction"), "UNKNOWN")
        pipe.add_event_claim(source=source, migration_status="LEGACY_PARTIAL",
            event_input={"event_type": row["event_type"], "primary_entity": row["ticker"],
                "related_entities": [], "event_date": row["event_date"],
                "normalized_summary": row["description"], "numbers": []},
            claim_input={"claim_text": row["description"], "claim_type": "FACTUAL_CLAIM",
                "direction": direction, "scope": "COMPANY", "time_horizon": "MEDIUM",
                "confidence": "HIGH" if row.get("source_tier") == "1" else "MEDIUM"})

    build_monitor(store, output / "evidence_monitor/latest.json")
    return store.counts()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", default="data/r1_v1")
    parser.add_argument("--evaluation-time", required=True)
    args = parser.parse_args()
    print(json.dumps(import_legacy(args.repo, args.output, args.evaluation_time), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
