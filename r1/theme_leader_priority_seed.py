from __future__ import annotations

import csv
import json
from pathlib import Path


# First bounded evidence batch: Ryan's five six-month target holdings.
# Scores follow config/r1_v03_score_rubric.json and are deliberately explicit;
# the script only reuses already VERIFIED evidence and never infers a score for
# another ticker or field.
REVIEWED_SCORES = {
    "2330": {"bottleneck_directness": 100, "industry_technology_position": 100,
             "ai_revenue_realization": 100},
    "2327": {"bottleneck_directness": 100, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "2344": {"bottleneck_directness": 75, "industry_technology_position": 50,
             "ai_revenue_realization": 75},
    "2376": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "2454": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "2492": {"bottleneck_directness": 75, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
    "3357": {"bottleneck_directness": 50, "industry_technology_position": 50,
             "ai_revenue_realization": 25},
    "2408": {"bottleneck_directness": 75, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
    "3081": {"bottleneck_directness": 75, "industry_technology_position": 50,
             "ai_revenue_realization": 75},
    "2308": {"bottleneck_directness": 100, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "3037": {"bottleneck_directness": 75, "industry_technology_position": 50,
             "ai_revenue_realization": 75},
    "6488": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "2303": {"bottleneck_directness": 50, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
    "3661": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 100},
    "3443": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "3035": {"bottleneck_directness": 50, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
    "2337": {"bottleneck_directness": 50, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
    "8299": {"bottleneck_directness": 75, "industry_technology_position": 75,
             "ai_revenue_realization": 75},
    "3260": {"bottleneck_directness": 50, "industry_technology_position": 50,
             "ai_revenue_realization": 50},
}

STAGE_BASELINE = {
    "THESIS": (25, 25),
    "QUALIFICATION": (50, 50),
    "SMALL_VOLUME": (50, 50),
    "MASS_PRODUCTION": (75, 75),
    "FINANCIAL_PROOF": (75, 75),
}


def _baseline_scores(evidence_rows: list[dict]) -> dict[str, int]:
    levels = [STAGE_BASELINE[row["stage"]] for row in evidence_rows if row.get("stage") in STAGE_BASELINE]
    if not levels:
        raise ValueError("verified evidence has no supported stage")
    bottleneck, realization = max(levels)
    return {
        "bottleneck_directness": bottleneck,
        # 50 means verified delivery capability, not proven industry leadership.
        "industry_technology_position": 50,
        "ai_revenue_realization": realization,
    }


def materialize(*, evidence_path: str | Path, source_path: str | Path) -> dict:
    by_ticker: dict[str, list[dict]] = {}
    with Path(evidence_path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("ticker", "")).zfill(4)
            status = row.get("evidence_status") or row.get("status")
            if status != "VERIFIED":
                continue
            by_ticker.setdefault(ticker, []).append(row)

    output = Path(source_path)
    payload = json.loads(output.read_text(encoding="utf-8"))
    rows = {str(row["ticker"]).zfill(4): row for row in payload.get("rows", [])}
    scored_tickers = sorted(by_ticker)
    for ticker in scored_tickers:
        scores = REVIEWED_SCORES.get(ticker) or _baseline_scores(by_ticker[ticker])
        evidence_rows = by_ticker.get(ticker, [])
        families = {row["source_family"] for row in evidence_rows}
        minimum_families = 2 if any(score >= 75 for score in scores.values()) else 1
        if len(evidence_rows) < minimum_families or len(families) < minimum_families:
            raise ValueError(f"{ticker} needs {minimum_families} VERIFIED independent evidence families")
        row = rows.setdefault(ticker, {"ticker": ticker, "evidence": {}})
        row.setdefault("evidence", {})
        sources = [{
            "source_url": item["source_url"],
            "source_date": item.get("published_at") or item["source_date"],
            "available_at": item["available_at"],
            "source_family": item["source_family"],
            "evidence_note": item.get("thesis") or item["claim"],
        } for item in evidence_rows[:2]]
        for field, score in scores.items():
            row[field] = score
            row["evidence"][field] = {"sources": sources}

    payload["as_of_date"] = "2026-10-16"
    payload["rows"] = sorted(rows.values(), key=lambda row: str(row["ticker"]).zfill(4))
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"updated_tickers": scored_tickers, "row_count": len(payload["rows"])}


if __name__ == "__main__":
    print(json.dumps(materialize(
        evidence_path="data/r1/bottleneck_evidence.csv",
        source_path="data/r1/theme_leader_inputs/source.json",
    ), ensure_ascii=False))
