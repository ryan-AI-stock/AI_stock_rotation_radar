from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .context_schema import ContextSnapshot


class ContextHistoryStore:
    """Append-only context history; a snapshot ID can never be overwritten."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)

    def rows(self) -> list[dict]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, snapshot: ContextSnapshot) -> bool:
        snapshot.validate(); existing = {r["snapshot_id"] for r in self.rows()}
        if snapshot.snapshot_id in existing: return False
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True)+"\n")
        return True

    def attribution_counts(self, ticker: str, last_n: int = 20) -> dict[str, int]:
        rows = [r for r in self.rows() if r["ticker"] == ticker][-last_n:]
        return {key: sum(r["primary_context"] == key for r in rows)
                for key in ("MARKET", "THEME", "COMPANY", "VALUATION", "FLOW", "MIXED", "UNKNOWN")}
