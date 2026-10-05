from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from r1.theme_policy import cadence, load_themes, rank_theme


def build_review(*, as_of_date: str, theme_path: str | Path, inputs_path: str | Path,
                 state_path: str | Path) -> dict:
    themes = load_themes(theme_path)
    inputs_file = Path(inputs_path)
    rows = json.loads(inputs_file.read_text(encoding="utf-8")).get("rows", []) if inputs_file.exists() else []
    state_file = Path(state_path)
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    due = cadence(
        as_of=date.fromisoformat(as_of_date),
        last_quarterly_review=date.fromisoformat(state["last_quarterly_review"])
        if state.get("last_quarterly_review") else None,
        last_membership_review=date.fromisoformat(state["last_membership_review"])
        if state.get("last_membership_review") else None,
    )
    reviews = [rank_theme(theme, rows) for theme in themes]
    ready = [row for row in reviews if row["status"] == "READY"]
    return {
        "model": "R1", "version": "r1-theme-leader-v0.2", "date": as_of_date,
        "cadence": due, "theme_count": len(themes), "ready_theme_count": len(ready),
        "status": "READY" if len(ready) == len(themes) else "DATA_MISSING",
        "themes": reviews,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R1 v0.2 theme leader review without fabricating missing scores.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--inputs", default="data/r1/theme_leader_inputs/latest.json")
    parser.add_argument("--state", default="data/r1/theme_reviews/state.json")
    parser.add_argument("--output", default="data/r1/theme_reviews/latest.json")
    args = parser.parse_args()
    payload = build_review(
        as_of_date=args.date, theme_path=args.themes, inputs_path=args.inputs, state_path=args.state,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
