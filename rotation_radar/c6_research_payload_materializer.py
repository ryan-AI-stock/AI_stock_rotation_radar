"""Build a source-labelled, partial C6 dashboard payload from existing PIT ranks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


DEFAULT_MODEL_VERSION = "c6-research-score0-pit-v1"
DATA_STATUS = "partial_rankings_only_no_whole_share_replay"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_rows(
    frame: pd.DataFrame,
    *,
    source_hash: str,
    source_label: str,
    model_version: str,
) -> list[dict]:
    rows: list[dict] = []
    for row in frame.itertuples(index=False):
        signal_date = pd.Timestamp(row.signal_date).date().isoformat()
        rows.append({
            "model_version": model_version,
            "snapshot_as_of": signal_date,
            "data_status": DATA_STATUS,
            "signal_date": signal_date,
            "rank": int(row.rank),
            "ticker": str(row.ticker).zfill(4),
            "name": str(row.name),
            "market": "unresolved_in_source_snapshot",
            "candidate_status": source_label,
            "source_manifest_hash": source_hash,
        })
    return rows


def build_payload(
    *,
    score_ranking: Path,
    recent_top3: Path,
    output: Path,
    model_version: str = DEFAULT_MODEL_VERSION,
    recent_source_label: str = "official_close_snapshot_20260826_20260828",
) -> dict:
    score = pd.read_csv(score_ranking, dtype={"ticker": str})
    score["signal_date"] = pd.to_datetime(score["signal_date"])
    historical = score.loc[
        score["signal_date"].between("2026-08-05", "2026-08-12") & score["rank"].le(3),
        ["signal_date", "rank", "ticker", "name"],
    ].copy()
    recent = pd.read_csv(recent_top3, dtype={"ticker": str})
    recent["signal_date"] = pd.to_datetime(recent["signal_date"])
    recent = recent.loc[:, ["signal_date", "rank", "ticker", "name"]]
    source_hash = hashlib.sha256(f"{_sha256(score_ranking)}:{_sha256(recent_top3)}".encode()).hexdigest()
    rows = _snapshot_rows(
        historical,
        source_hash=source_hash,
        source_label="existing_c6_score0_pit_ranking",
        model_version=model_version,
    )
    rows.extend(
        _snapshot_rows(
            recent,
            source_hash=source_hash,
            source_label=recent_source_label,
            model_version=model_version,
        )
    )
    rows.sort(key=lambda row: (row["signal_date"], row["rank"]))
    covered_dates = sorted({row["signal_date"] for row in rows})
    requested_dates = [str(day.date()) for day in pd.bdate_range("2026-08-05", "2026-08-28")]
    missing_dates = [day for day in requested_dates if day not in covered_dates]
    payload = {
        "model_version": model_version,
        "snapshot_as_of": "2026-08-28",
        "data_status": DATA_STATUS,
        "source_manifest_hash": source_hash,
        "snapshot_rows": rows,
        "ledger_rows": [],
        "slots": [],
        "cash": 0.0,
        "notes": (
            f"現有PIT Top1~3覆蓋 {covered_dates[0]}~{covered_dates[-1]} 的 {len(covered_dates)} 日、"
            f"{len(rows)} 筆；缺 {','.join(missing_dates)}。"
            "8/13後排名只重用已持久化候選/市場快取；Layer1沿用2026-07-22 accepted allow-list，"
            "不是current-fresh PIT。0050 raw-as-adjusted僅研究診斷，仍待公司行動稽核。"
            "C6 2026-08-05起三槽整股交易、每日holding marks與提領流水尚未由權威replay materialize，未寫入帳本。"
        ),
        "coverage": {
            "requested_start": "2026-08-05",
            "requested_end": "2026-08-28",
            "covered_signal_dates": covered_dates,
            "missing_signal_dates": missing_dates,
            "snapshot_rows": len(rows),
            "ledger_rows": 0,
            "layer1_basis": "accepted_2026-07-22_allow_list_not_current_fresh_PIT",
            "adjusted_price_basis": "0050_raw_as_adjusted_research_diagnostic_pending_corporate_action_audit",
            "future_data_violation_count": 0,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize a partial C6 append-only dashboard payload from PIT snapshots.")
    parser.add_argument("--score-ranking", required=True, type=Path)
    parser.add_argument("--recent-top3", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--recent-source-label", default="official_close_snapshot_20260826_20260828")
    args = parser.parse_args()
    payload = build_payload(
        score_ranking=args.score_ranking,
        recent_top3=args.recent_top3,
        output=args.output,
        model_version=args.model_version,
        recent_source_label=args.recent_source_label,
    )
    print(json.dumps(payload["coverage"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
