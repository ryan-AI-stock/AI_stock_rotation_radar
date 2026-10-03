from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_WEIGHTS = {"eps_revision", "forward_valuation", "bottleneck", "catalyst", "price_chip"}
VALID_ROLES = {"PORTFOLIO", "UNIVERSE", "DISCOVERY_CANDIDATE"}


@dataclass(frozen=True)
class Security:
    ticker: str
    company: str
    shares: int
    core_lock: bool
    roles: tuple[str, ...]
    market: str


@dataclass(frozen=True)
class R1Config:
    version: str
    timezone: str
    action_policy_approved: bool
    weights: dict[str, float]
    score_policy: dict[str, Any]
    max_weekly_rotation: float
    rotation_policy: dict[str, Any]
    securities: tuple[Security, ...]

    @classmethod
    def load(cls, path: str | Path) -> "R1Config":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_payload(payload)
        securities = tuple(
            Security(
                ticker=str(row["ticker"]).zfill(4),
                company=str(row["company"]),
                shares=int(row.get("shares", 0)),
                core_lock=bool(row.get("core_lock", False)),
                roles=tuple(row["roles"]),
                market=str(row["market"]),
            )
            for row in payload["securities"]
        )
        return cls(
            version=str(payload["version"]),
            timezone=str(payload["timezone"]),
            action_policy_approved=bool(payload["action_policy_approved"]),
            weights={key: float(value) for key, value in payload["weights"].items()},
            score_policy=payload["score_policy"],
            max_weekly_rotation=float(payload["rotation"]["max_weekly_rotation"]),
            rotation_policy=payload["rotation"],
            securities=securities,
        )


def validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("action_policy_approved"), bool):
        raise ValueError("action_policy_approved must be a boolean")
    weights = payload.get("weights", {})
    if set(weights) != REQUIRED_WEIGHTS:
        raise ValueError(f"R1 weights must be exactly {sorted(REQUIRED_WEIGHTS)}")
    if abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-9:
        raise ValueError("R1 weights must sum to 1.0")
    policy = payload.get("score_policy", {})
    if policy.get("version") != "r1-score-v0.1-research":
        raise ValueError("R1 score_policy version mismatch")
    expected_subweights = {
        "eps_revision": {"1w", "4w", "12w"},
        "forward_valuation": {"own_forward_pe", "base_upside", "next_year_eps_growth"},
        "bottleneck": {"stage", "tightness", "financial_proof"},
        "price_chip": {"earnings_vs_price", "overheat_safety", "institutional", "leverage_structure"},
    }
    for component, expected in expected_subweights.items():
        subweights = policy.get(component, {}).get("weights", {})
        if set(subweights) != expected or abs(sum(float(value) for value in subweights.values()) - 1.0) > 1e-9:
            raise ValueError(f"R1 {component} subweights must be exactly {sorted(expected)} and sum to 1.0")
    max_rotation = float(payload.get("rotation", {}).get("max_weekly_rotation", -1))
    if not 0 <= max_rotation <= 1:
        raise ValueError("max_weekly_rotation must be between 0 and 1")
    rotation = payload.get("rotation", {})
    if rotation.get("shadow_policy_approved") is not True:
        raise ValueError("R1 shadow rotation policy must be explicitly approved")
    if not 0 < float(rotation.get("overheat_percentile", 0)) < 1:
        raise ValueError("R1 overheat_percentile must be between 0 and 1")
    if float(rotation.get("minimum_score_advantage", -1)) < 0:
        raise ValueError("R1 minimum_score_advantage must be nonnegative")
    if not 0 < float(rotation.get("staged_transfer_fraction", 0)) <= 1:
        raise ValueError("R1 staged_transfer_fraction must be in (0,1]")
    if int(rotation.get("max_holdings", 0)) != 5:
        raise ValueError("R1 max_holdings must be 5")
    seen: set[str] = set()
    for row in payload.get("securities", []):
        ticker = str(row.get("ticker", "")).zfill(4)
        if ticker in seen:
            raise ValueError(f"duplicate R1 ticker: {ticker}")
        seen.add(ticker)
        roles = set(row.get("roles", []))
        if not roles or not roles <= VALID_ROLES:
            raise ValueError(f"invalid R1 roles for {ticker}: {sorted(roles)}")
        if bool(row.get("core_lock")) and ticker != "2330":
            raise ValueError("initial R1 contract permits CORE_LOCK only for 2330")
        if row.get("market") not in {"TWSE", "TPEx"}:
            raise ValueError(f"invalid market for {ticker}: {row.get('market')}")
    core = [row for row in payload.get("securities", []) if row.get("core_lock")]
    if len(core) != 1 or str(core[0].get("ticker", "")).zfill(4) != "2330":
        raise ValueError("R1 requires 2330 as the single CORE_LOCK security")
