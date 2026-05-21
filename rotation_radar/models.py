from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class Bucket(str, Enum):
    ACTIONABLE = "可操作名單"
    WATCH = "觀察名單"
    EXCLUDED = "排除名單"


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    parts: dict[str, float]
    notes: list[str]


@dataclass(frozen=True)
class SectorMetrics:
    name: str
    theme: str
    capital_inflow_rank: float
    turnover_share_change: float
    momentum_20d: float
    strong_stock_ratio: float
    industry_trend: float
    overseas_signal: float
    pe_percentile: float
    risk_heat: float
    catalysts: Sequence[str]
    risks: Sequence[str]
    capital_share: float = 0.0
    capital_share_prev: float = 0.0
    turnover_value: float = 0.0
    turnover_value_prev: float = 0.0


@dataclass(frozen=True)
class StockMetrics:
    symbol: str
    name: str
    sector: str
    close: float
    pullback_quality: float
    chip_cleanliness: float
    foreign_5d: float
    trust_5d: float
    margin_change_5d: float
    pe: float
    sector_pe_low: float
    sector_pe_avg: float
    sector_pe_high: float
    revenue_yoy: float
    revenue_mom: float
    technical_setup: float
    liquidity: float
    risk_heat: float
    thesis: str
    risk_reason: str
    fair_value_low: float = 0.0
    fair_value_avg: float = 0.0
    fair_value_high: float = 0.0


@dataclass(frozen=True)
class SectorResult:
    metrics: SectorMetrics
    score: ScoreBreakdown


@dataclass(frozen=True)
class StockResult:
    metrics: StockMetrics
    score: ScoreBreakdown
    bucket: Bucket


@dataclass(frozen=True)
class Report:
    title: str
    generated_at: str
    market_view: str
    sector_results: list[SectorResult]
    stock_results: list[StockResult]
    price_history: dict[str, list[dict[str, float | str]]] = field(default_factory=dict)
    sector_themes: dict[str, list[dict[str, float | str]]] = field(default_factory=dict)
    stock_themes: dict[str, list[str]] = field(default_factory=dict)
    theme_trends: dict[str, dict[str, float | str]] = field(default_factory=dict)
    quote_date: str = ""
    quote_time: str = ""
