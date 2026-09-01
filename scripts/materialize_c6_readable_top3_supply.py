"""Materialize a source-labelled, readable C6 Top1-3 supply table without new downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


STRATEGY_ROOT = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\strategy-center-core-experiments-research-materials")
CORE_PREFLIGHT = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-core-production-grade-contract\work\c6_forward_replay_preflight_20260830")
RANKING = STRATEGY_ROOT / "outputs" / "ai_pool_c6_c8_same_rules_comparison_20260828" / "C6" / "C6_SCORE_0_ranking.csv.gz"
RECENT_TOP3 = Path("data/c6_source_materialized_20260830/c_top3_20260813_20260828.csv")
RECENT_MARKET = STRATEGY_ROOT / "outputs" / "ai_pool_c_snapshot_20260826_20260828" / "official_market_rows.csv.gz"
LOCAL_MARKET = Path("data/current_base_cycle_source_cache/official_recent_full_market.csv.gz")
CURRENT_PAYLOAD = Path("data/c6_current_snapshot.json")
CURRENT_TOP3 = [
    Path("outputs/c6_20260831_bounded_research/c6_top3_20260831.csv"),
    Path("outputs/c6_20260901_bounded_research/c6_top3_20260901.csv"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_market() -> pd.DataFrame:
    frames = []
    for path in (LOCAL_MARKET, RECENT_MARKET):
        frame = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
        if "source_url" not in frame.columns:
            frame["source_url"] = "upstream_snapshot_manifest_only"
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(4)
        frame["signal_date"] = pd.to_datetime(frame["date"])
        frames.append(frame[["signal_date", "ticker", "close", "market", "source_url"]])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["signal_date", "ticker"], keep="last")


def next_known_session(date: pd.Timestamp, sessions: list[pd.Timestamp]) -> str:
    later = [session for session in sessions if session > date]
    return later[0].date().isoformat() if later else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(CURRENT_PAYLOAD.read_text(encoding="utf-8"))
    if not str(payload["model_version"]).startswith("c6-research-score0-pit-v2"):
        raise SystemExit("current payload is not the sole v2 authority")

    historical = pd.read_csv(RANKING, dtype={"ticker": str}, low_memory=False)
    historical["signal_date"] = pd.to_datetime(historical["signal_date"])
    historical = historical.loc[
        historical["signal_date"].between("2026-08-06", "2026-08-12") & historical["rank"].le(3),
        ["signal_date", "rank", "ticker", "name", "selection_score"],
    ]
    historical["source_label"] = "frozen_C6_SCORE_0_ranking"

    recent = pd.read_csv(RECENT_TOP3, dtype={"ticker": str}, low_memory=False)
    recent["signal_date"] = pd.to_datetime(recent["signal_date"])
    recent = recent.loc[:, ["signal_date", "rank", "ticker", "name", "selection_score"]]
    recent["source_label"] = "persisted_C6_snapshot_re_rank"

    current = pd.concat([pd.read_csv(path, dtype={"ticker": str}) for path in CURRENT_TOP3], ignore_index=True)
    current["signal_date"] = pd.to_datetime(current["signal_date"])
    current = current.loc[:, ["signal_date", "rank", "ticker", "name", "selection_score"]]
    current["source_label"] = "bounded_current_C6_official_close_recompute"
    ranked = pd.concat([historical, recent, current], ignore_index=True)
    ranked["ticker"] = ranked["ticker"].astype(str).str.zfill(4)
    ranked = ranked.drop_duplicates(["signal_date", "rank"], keep="last")
    if ranked.duplicated(["signal_date", "ticker"]).any():
        raise SystemExit("duplicate v2 ticker/date rows")

    payload_rows = pd.DataFrame(payload["snapshot_rows"])
    payload_rows["signal_date"] = pd.to_datetime(payload_rows["signal_date"])
    expected = payload_rows.loc[:, ["signal_date", "rank", "ticker"]].copy()
    expected = expected.loc[expected["rank"].isin([1, 2, 3])]
    expected["ticker"] = expected["ticker"].astype(str).str.zfill(4)
    actual = ranked.loc[:, ["signal_date", "rank", "ticker"]]
    if not expected.merge(actual, on=["signal_date", "rank", "ticker"], how="left", indicator=True)["_merge"].eq("both").all():
        raise SystemExit("readable supply does not match current v2 snapshot keys")

    market = load_market()
    sessions = sorted(market["signal_date"].drop_duplicates().tolist())
    ranked = ranked.merge(market, on=["signal_date", "ticker"], how="left")
    if ranked["close"].isna().any():
        missing = ranked.loc[ranked["close"].isna(), ["signal_date", "ticker"]]
        raise SystemExit(f"missing local official close for v2 rows: {missing.to_dict('records')}")
    ranked["eligibility_reason"] = "frozen_C6_eligibility_passed_and_ranked"
    ranked["planned_execution_date"] = ranked["signal_date"].map(lambda date: next_known_session(date, sessions))
    ranked["planned_execution_status"] = ranked["planned_execution_date"].map(
        lambda date: "next_known_official_market_session" if date else "next_session_not_materialized_in_local_cache"
    )
    ranked["source_readiness"] = "accepted_research_ranking_with_official_raw_display_close"
    ranked["close_basis"] = "official_raw_display_close"

    no_eligible = pd.DataFrame([{
        "signal_date": pd.Timestamp("2026-08-05"), "rank": pd.NA, "ticker": "", "name": "",
        "selection_score": pd.NA, "close": pd.NA, "market": "", "source_url": "",
        "source_label": "Core_frozen_engine_recomputed_ranking_20260804_20260812",
        "eligibility_reason": "frozen_engine_explicit_no_eligible_candidate",
        "planned_execution_date": "", "planned_execution_status": "not_applicable_no_eligible_candidate",
        "source_readiness": "accepted_explicit_no_eligible_candidate", "close_basis": "not_applicable",
    }])
    result = pd.concat([no_eligible, ranked], ignore_index=True, sort=False)
    result["signal_date"] = pd.to_datetime(result["signal_date"]).dt.date.astype(str)
    result = result.sort_values(["signal_date", "rank"], na_position="first")

    args.output.mkdir(parents=True, exist_ok=True)
    supply = args.output / "c6_top3_readable_current_v2_supply.csv"
    result.to_csv(supply, index=False, encoding="utf-8-sig")
    coverage = {
        "task": "C6_current_top3_readable_source_supply",
        "model_version": payload["model_version"],
        "current_v2_unique_rank_rows": int(len(ranked)),
        "explicit_no_eligible_dates": ["2026-08-05"],
        "current_official_close_top3_dates": ["2026-08-31", "2026-09-01"],
        "official_display_close_ready_rank_rows": int(ranked["close"].notna().sum()),
        "network_calls": 0,
        "future_data_violation_count": 0,
        "ready_for_core_forward_replay": False,
        "blocker": "ranking coverage does not authorize post-2026-08-12 whole-share actions or withdrawals",
    }
    (args.output / "readiness_for_core_c6_top3_readable_supply.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    inputs = [CURRENT_PAYLOAD, RANKING, RECENT_TOP3, LOCAL_MARKET, RECENT_MARKET]
    manifest = {"inputs": [{"path": str(path), "sha256": sha256(path)} for path in inputs], **coverage}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "current_step.txt").write_text("complete_local_only_readable_C6_v2_supply\n", encoding="utf-8")
    print(json.dumps(coverage, ensure_ascii=False))


if __name__ == "__main__":
    main()

