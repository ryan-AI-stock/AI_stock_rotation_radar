from __future__ import annotations
import json
from dataclasses import asdict,is_dataclass
from pathlib import Path

KEYS={"opportunities":"comparison_id","portfolio_states":"state_id","decision_snapshots":"decision_id",
      "outcome_reviews":"review_id","model_change_proposals":"proposal_id","benchmark_snapshots":"benchmark_snapshot_id"}

class ResearchStore:
    def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
    def path(self,table):return self.root/f"{table}.jsonl"
    def rows(self,table):
        p=self.path(table);return [] if not p.exists() else [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    def append(self,table,record):
        row=asdict(record) if is_dataclass(record) else dict(record);key=KEYS[table]
        if any(x[key]==row[key] for x in self.rows(table)):return False
        with self.path(table).open("a",encoding="utf-8",newline="\n") as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
        return True
