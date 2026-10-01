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
    weights: dict[str, float]
    max_weekly_rotation: float
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
            weights={key: float(value) for key, value in payload["weights"].items()},
            max_weekly_rotation=float(payload["rotation"]["max_weekly_rotation"]),
            securities=securities,
        )


def validate_payload(payload: dict[str, Any]) -> None:
    weights = payload.get("weights", {})
    if set(weights) != REQUIRED_WEIGHTS:
        raise ValueError(f"R1 weights must be exactly {sorted(REQUIRED_WEIGHTS)}")
    if abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-9:
        raise ValueError("R1 weights must sum to 1.0")
    max_rotation = float(payload.get("rotation", {}).get("max_weekly_rotation", -1))
    if not 0 <= max_rotation <= 1:
        raise ValueError("max_weekly_rotation must be between 0 and 1")
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
