from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


LEADER_FIELDS = (
    "bottleneck_moat", "competitive_position", "ai_revenue_realization",
    "earnings_quality", "financial_strength", "supply_visibility",
)
LEADER_WEIGHTS = {
    "bottleneck_moat": 0.25,
    "competitive_position": 0.20,
    "ai_revenue_realization": 0.20,
    "earnings_quality": 0.15,
    "financial_strength": 0.10,
    "supply_visibility": 0.10,
}
DISCLOSURE_ANCHORS = ((4, 1), (5, 16), (8, 15), (11, 15))
MEMBERSHIP_ANCHORS = ((4, 1), (8, 15))


@dataclass(frozen=True)
class ThemeMember:
    ticker: str
    company: str
    market: str


@dataclass(frozen=True)
class Theme:
    theme_id: str
    name: str
    thesis: str
    members: tuple[ThemeMember, ...]


def load_themes(path: str | Path) -> tuple[Theme, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != "r1-theme-universe-v0.2":
        raise ValueError("R1 theme universe version mismatch")
    themes = []
    seen_tickers: set[str] = set()
    for row in payload.get("themes", []):
        members = tuple(
            ThemeMember(str(item[0]).zfill(4), str(item[1]), str(item[2]))
            for item in row.get("members", [])
        )
        if not 3 <= len(members) <= 6:
            raise ValueError(f"R1 theme {row.get('id')} must contain 3 to 6 members")
        for member in members:
            if member.ticker in seen_tickers:
                raise ValueError(f"duplicate primary R1 theme ticker: {member.ticker}")
            if member.market not in {"TWSE", "TPEx"}:
                raise ValueError(f"invalid R1 theme market: {member.ticker}")
            seen_tickers.add(member.ticker)
        themes.append(Theme(str(row["id"]), str(row["name"]), str(row["bottleneck_thesis"]), members))
    if not 7 <= len(themes) <= 12:
        raise ValueError("R1 structural theme count must stay between 7 and 12")
    return tuple(themes)


def leader_score(row: dict) -> float | None:
    if any(row.get(field) is None for field in LEADER_FIELDS):
        return None
    values = {field: float(row[field]) for field in LEADER_FIELDS}
    if any(not 0 <= value <= 100 for value in values.values()):
        raise ValueError("R1 leader component scores must be within 0..100")
    return round(sum(values[field] * LEADER_WEIGHTS[field] for field in LEADER_FIELDS), 6)


def rank_theme(theme: Theme, rows: list[dict]) -> dict:
    allowed = {member.ticker for member in theme.members}
    ranked = []
    missing = []
    for row in rows:
        ticker = str(row.get("ticker", "")).zfill(4)
        if ticker not in allowed:
            continue
        score = leader_score(row)
        if score is None:
            missing.append({"ticker": ticker, "missing_fields": [field for field in LEADER_FIELDS if row.get(field) is None]})
        else:
            ranked.append({**row, "ticker": ticker, "leader_score": score})
    observed = {str(row.get("ticker", "")).zfill(4) for row in rows}
    for member in theme.members:
        if member.ticker not in observed:
            missing.append({"ticker": member.ticker, "missing_fields": list(LEADER_FIELDS)})
    ranked.sort(key=lambda row: (-row["leader_score"], row["ticker"]))
    return {
        "theme_id": theme.theme_id,
        "theme_name": theme.name,
        "status": "READY" if not missing and ranked else "DATA_MISSING",
        "top1": ranked[0] if not missing and ranked else None,
        "ranked": ranked if not missing else [],
        "data_gaps": missing,
    }


def latest_due_anchor(as_of: date, anchors: tuple[tuple[int, int], ...]) -> date:
    candidates = [date(year, month, day) for year in (as_of.year - 1, as_of.year)
                  for month, day in anchors if date(year, month, day) <= as_of]
    return max(candidates)


def cadence(*, as_of: date, last_quarterly_review: date | None,
            last_membership_review: date | None) -> dict[str, bool | str]:
    quarterly_anchor = latest_due_anchor(as_of, DISCLOSURE_ANCHORS)
    membership_anchor = latest_due_anchor(as_of, MEMBERSHIP_ANCHORS)
    return {
        "daily_accumulation": True,
        "weekly_risk_and_replacement_review": True,
        "quarterly_leader_review_due": last_quarterly_review is None or last_quarterly_review < quarterly_anchor,
        "quarterly_anchor": quarterly_anchor.isoformat(),
        "semiannual_membership_review_due": last_membership_review is None or last_membership_review < membership_anchor,
        "membership_anchor": membership_anchor.isoformat(),
    }


def rotation_decision(*, emergency_thesis_break: bool, holding_risk_high: bool,
                      theme_weak_confirmed: bool, replacement_ready: bool,
                      replacement_advantage: float | None, confirmation_weeks: int,
                      minimum_advantage: float = 10.0) -> str:
    if emergency_thesis_break:
        return "EMERGENCY_EXIT_TO_CASH"
    if not holding_risk_high or not theme_weak_confirmed:
        return "LONG_HOLD"
    if not replacement_ready or replacement_advantage is None:
        return "WATCH_NO_REPLACEMENT"
    if confirmation_weeks < 2 or replacement_advantage < minimum_advantage:
        return "WATCH_UNCONFIRMED_ADVANTAGE"
    return "ROTATE_NEXT_TRADING_DAY"
