from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from r1.theme_policy import cadence, load_themes


def build_membership_review(*, as_of_date: str, theme_path: str | Path,
                            evidence_path: str | Path, discovery_path: str | Path,
                            state_path: str | Path) -> dict:
    themes = load_themes(theme_path)
    state_file = Path(state_path)
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    due = cadence(
        as_of=date.fromisoformat(as_of_date),
        last_quarterly_review=date.fromisoformat(state["last_quarterly_review"])
        if state.get("last_quarterly_review") else None,
        last_membership_review=date.fromisoformat(state["last_membership_review"])
        if state.get("last_membership_review") else None,
    )
    evidence_file = Path(evidence_path)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8")) if evidence_file.exists() else {"rows": []}
    evidence_tickers = {str(row.get("ticker", "")).zfill(4) for row in evidence.get("rows", [])}
    universe = {
        member.ticker: {"company": member.company, "theme_id": theme.theme_id, "theme_name": theme.name}
        for theme in themes for member in theme.members
    }
    discovery_file = Path(discovery_path)
    discovery = json.loads(discovery_file.read_text(encoding="utf-8")) if discovery_file.exists() else {"candidates": []}
    additions = [
        row for row in discovery.get("candidates", [])
        if row.get("status") == "ELIGIBLE_FOR_RYAN_REVIEW"
        and str(row.get("ticker", "")).zfill(4) not in universe
    ]
    return {
        "model": "R1",
        "version": "r1-membership-review-v0.1",
        "as_of_date": as_of_date,
        "status": "REVIEW_DUE" if due["semiannual_membership_review_due"] else "NOT_DUE",
        "membership_anchor": due["membership_anchor"],
        "last_membership_review": state.get("last_membership_review"),
        "theme_count": len(themes),
        "member_count": len(universe),
        "current_members_without_dedicated_evidence_row": [
            {"ticker": ticker, **meta} for ticker, meta in sorted(universe.items())
            if ticker not in evidence_tickers
        ],
        "addition_candidates_for_ryan_review": additions,
        "automatic_changes_applied": False,
        "policy": "每週累積證據；每半年提出增刪建議。Ryan核准前不修改候選池。",
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the evidence-gated R1 semiannual membership review.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--evidence", default="data/r1/theme_membership_evidence.json")
    parser.add_argument("--discovery", default="data/r1/discovery_pool.json")
    parser.add_argument("--state", default="data/r1/theme_reviews/state.json")
    parser.add_argument("--output", default="data/r1/membership_review/latest.json")
    args = parser.parse_args()
    payload = build_membership_review(
        as_of_date=args.date, theme_path=args.themes, evidence_path=args.evidence,
        discovery_path=args.discovery, state_path=args.state,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "member_count": payload["member_count"],
                      "addition_candidate_count": len(payload["addition_candidates_for_ryan_review"]),
                      "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
