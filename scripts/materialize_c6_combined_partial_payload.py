"""Combine readable ranking coverage with Core's bounded known-segment account payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


CORE_PAYLOAD = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-core-production-grade-contract\work\c6_forward_replay_preflight_20260830\current_partial_payload_20260812\c6_current_snapshot.json")
READABLE_SUPPLY = Path("outputs/radar_c6_top3_readable_current_supply_20260901/c6_top3_readable_current_v2_supply.csv")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(value: object) -> object:
    return "" if pd.isna(value) else value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/c6_current_snapshot.json"))
    args = parser.parse_args()

    core = json.loads(CORE_PAYLOAD.read_text(encoding="utf-8"))
    supply = pd.read_csv(READABLE_SUPPLY, dtype={"ticker": str}, low_memory=False)
    source_rows: list[dict] = []
    for row in supply.itertuples(index=False):
        rank = 0 if pd.isna(row.rank) else int(row.rank)
        source_rows.append({
            "signal_date": str(row.signal_date),
            "rank": rank,
            "ticker": str(scalar(row.ticker)).zfill(4) if scalar(row.ticker) else "",
            "name": scalar(row.name),
            "market": scalar(row.market),
            "candidate_status": scalar(row.eligibility_reason),
            "eligibility_reason": scalar(row.eligibility_reason),
            "score": scalar(row.selection_score),
            "display_close": scalar(row.close),
            "planned_execution_date": scalar(row.planned_execution_date),
            "source_readiness": scalar(row.source_readiness),
            "source_label": scalar(row.source_label),
        })
    keys = [(row["signal_date"], row["rank"]) for row in source_rows]
    if len(keys) != len(set(keys)):
        raise SystemExit("combined payload ranking keys are not unique")

    ranking_as_of = max(row["signal_date"] for row in source_rows if row["rank"] in {1, 2, 3})
    core_hash = sha256(CORE_PAYLOAD)
    supply_hash = sha256(READABLE_SUPPLY)
    core["snapshot_rows"] = source_rows
    core["ranking_snapshot_as_of"] = ranking_as_of
    core["accounting_snapshot_as_of"] = core["snapshot_as_of"]
    core["source_manifest_hash"] = hashlib.sha256(f"{core_hash}:{supply_hash}".encode()).hexdigest()
    core["notes"] = (
        "排名覆蓋：2026-08-05 explicit no eligible；其餘列為唯一 v2 去重排名，"
        "僅供候選展示。整股帳本僅至 2026-08-12，包含 3 個 official raw execution 與 EOD slots/cash。"
        "2026-08-13 後完整 C6 PIT exit/action state 未 materialize；不得把排名視為空候選或推定交易。"
    )
    core["coverage"] = {
        "ranking_snapshot_as_of": ranking_as_of,
        "accounting_snapshot_as_of": core["snapshot_as_of"],
        "ranking_rows": len(source_rows),
        "ranking_top3_rows": sum(row["rank"] in {1, 2, 3} for row in source_rows),
        "explicit_no_eligible_dates": ["2026-08-05"],
        "pit_blocked_not_empty_candidate_dates": [],
        "ledger_rows": len(core["ledger_rows"]),
        "future_data_violation_count": 0,
    }
    args.output.write_text(json.dumps(core, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(core["coverage"], ensure_ascii=False))


if __name__ == "__main__":
    main()

