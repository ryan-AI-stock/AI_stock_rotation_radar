from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ids import stable_id


TABLE_KEYS = {
    "sources": "source_id", "facts": "fact_id", "events": "event_id",
    "claims": "claim_id", "event_claim_links": "link_id",
    "claim_evidence_links": "link_id", "dedup_decisions": "decision_id",
    "rejections": "rejection_id", "audit_log": "audit_id",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceStore:
    """Small append-only JSONL evidence ledger. Existing records are never overwritten."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._row_cache: dict[str, list[dict[str, Any]]] = {}
        self._id_cache: dict[str, set[Any]] = {}

    def path(self, table: str) -> Path:
        if table not in TABLE_KEYS:
            raise KeyError(table)
        return self.root / f"{table}.jsonl"

    def rows(self, table: str) -> list[dict[str, Any]]:
        if table in self._row_cache:
            return list(self._row_cache[table])
        path = self.path(table)
        if not path.exists():
            self._row_cache[table] = []
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self._row_cache[table] = rows
        return list(rows)

    def append(self, table: str, record: Any) -> bool:
        row = asdict(record) if is_dataclass(record) else dict(record)
        key = TABLE_KEYS[table]
        if key not in row:
            if table.endswith("links"):
                row[key] = stable_id(table, row)
            else:
                raise ValueError(f"{key}_missing")
        if table not in self._id_cache:
            self._id_cache[table] = {existing.get(key) for existing in self.rows(table)}
        if row[key] in self._id_cache[table]:
            return False
        with self.path(table).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._id_cache[table].add(row[key])
        self._row_cache.setdefault(table, []).append(row)
        return True

    def audit(self, *, action: str, entity_type: str, entity_id: str,
              actor: str, reason: str, source_reference: str | None,
              old_value: Any = None, new_value: Any = None,
              occurred_at: str | None = None) -> str:
        occurred_at = occurred_at or now_iso()
        audit_id = stable_id("audit", action, entity_type, entity_id, actor, reason,
                             source_reference, old_value, new_value, occurred_at)
        self.append("audit_log", {"audit_id": audit_id, "action": action,
                    "entity_type": entity_type, "entity_id": entity_id,
                    "actor": actor, "reason": reason,
                    "source_reference": source_reference, "old_value": old_value,
                    "new_value": new_value, "occurred_at": occurred_at})
        return audit_id

    def reject(self, *, reason: str, payload: dict[str, Any], actor: str,
               source_reference: str | None = None) -> str:
        rejection_id = stable_id("reject", reason, payload, source_reference)
        created_at = now_iso()
        self.append("rejections", {"rejection_id": rejection_id, "reason": reason,
                    "payload": payload, "actor": actor,
                    "source_reference": source_reference, "created_at": created_at})
        self.audit(action="REJECT", entity_type="REJECTION", entity_id=rejection_id,
                   actor=actor, reason=reason, source_reference=source_reference,
                   new_value=payload, occurred_at=created_at)
        return rejection_id

    def independent_evidence_count(self, claim_id: str, stance: str | None = None) -> int:
        rows = [r for r in self.rows("claim_evidence_links") if r["claim_id"] == claim_id]
        if stance:
            rows = [r for r in rows if r["stance"] == stance]
        return len({r["primary_lineage_id"] for r in rows})

    def counts(self) -> dict[str, int]:
        return {table: len(self.rows(table)) for table in TABLE_KEYS}

    def canonical_events(self) -> set[str]:
        return {row["canonical_event_id"] for row in self.rows("events")}

