from __future__ import annotations

import json
from pathlib import Path

from r1.config import R1Config
from r1.evidence import VALID_STAGES


def load_bottleneck_map(path: str | Path, config_path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    config = R1Config.load(config_path)
    expected = {row.ticker for row in config.securities}
    actual = {str(row.get("ticker", "")).zfill(4) for row in payload.get("rows", [])}
    if expected != actual:
        raise ValueError(f"bottleneck coverage mismatch missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    for row in payload["rows"]:
        if row.get("stage") not in VALID_STAGES:
            raise ValueError(f"invalid bottleneck stage for {row.get('ticker')}")
        if not row.get("categories"):
            raise ValueError(f"missing bottleneck category for {row.get('ticker')}")
        if row.get("evidence_status") != "VERIFIED":
            row["bottleneck_score"] = None
    return payload
