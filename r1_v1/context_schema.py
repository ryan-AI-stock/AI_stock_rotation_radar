from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MARKET_STATES = {"RISK_ON", "NEUTRAL", "RISK_OFF", "PANIC", "RECOVERY", "UNKNOWN"}
THEME_STATES = {"ACCELERATING", "STABLE", "COOLING", "SELL_OFF", "RECOVERING", "UNKNOWN"}
COMPANY_STATES = {"OUTPERFORMING", "IN_LINE", "UNDERPERFORMING",
                  "IDIOSYNCRATIC_STRESS", "IDIOSYNCRATIC_STRENGTH", "UNKNOWN"}
VALUATION_STATES = {"DEPRESSED", "BELOW_NORMAL", "NORMAL", "ABOVE_NORMAL", "EXTREME", "UNKNOWN"}
FLOW_STATES = {"ACCUMULATING", "NEUTRAL", "DISTRIBUTING", "CROWDED", "CAPITULATION", "UNKNOWN"}
ATTRIBUTIONS = {"MARKET", "THEME", "COMPANY", "VALUATION", "FLOW", "MIXED", "UNKNOWN"}


@dataclass(frozen=True)
class MarketContext:
    evaluation_time: str
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    breadth: float | None
    up_count: int | None
    down_count: int | None
    limit_up_count: int | None
    limit_down_count: int | None
    turnover: float | None
    turnover_ratio_20d: float | None
    foreign_flow: float | None
    tw50_return_1d: float | None
    vix: float | None
    us_market_return_1d: float | None
    usd_twd_return_1d: float | None
    major_macro_event_links: list[str]
    market_state: str
    confidence: str
    unknowns: list[str]


@dataclass(frozen=True)
class ThemeContext:
    theme_id: str
    theme_return_1d: float | None
    theme_return_5d: float | None
    theme_return_20d: float | None
    theme_breadth: float | None
    median_return_1d: float | None
    equal_weight_return_1d: float | None
    market_relative_return_1d: float | None
    number_of_positive_names: int | None
    number_of_negative_names: int | None
    volume_state: str
    theme_event_state: str
    theme_context_state: str
    confidence: str
    unknowns: list[str]


@dataclass(frozen=True)
class CompanyContext:
    ticker: str
    stock_return_1d: float | None
    stock_return_5d: float | None
    stock_return_20d: float | None
    relative_to_market: float | None
    relative_to_theme: float | None
    relative_to_peers: float | None
    company_event_count: int
    company_negative_event_count: int
    company_positive_event_count: int
    latest_company_fact: str | None
    latest_company_claim: str | None
    company_context_state: str
    anomaly_zscore: float | None
    confidence: str
    unknowns: list[str]


@dataclass(frozen=True)
class ValuationContext:
    ticker: str
    forward_pe: float | None
    pb: float | None
    ev_ebitda: float | None
    historical_percentile: float | None
    eps_revision: float | None
    valuation_change_1w: float | None
    valuation_change_4w: float | None
    valuation_change_12w: float | None
    valuation_state: str
    confidence: str
    unknowns: list[str]


@dataclass(frozen=True)
class FlowContext:
    ticker: str
    foreign_flow: float | None
    investment_trust_flow: float | None
    dealer_flow: float | None
    margin_change: float | None
    short_interest_change: float | None
    turnover_ratio_20d: float | None
    large_holder_change: float | None
    flow_state: str
    confidence: str
    unknowns: list[str]


@dataclass(frozen=True)
class ContextSnapshot:
    snapshot_id: str
    date: str
    evaluation_time: str
    ticker: str
    theme_id: str
    market_context: dict[str, Any]
    theme_context: dict[str, Any]
    company_context: dict[str, Any]
    valuation_context: dict[str, Any]
    flow_context: dict[str, Any]
    primary_context: str
    secondary_context: str | None
    anomaly_type: str
    possible_mispricing_candidate: bool
    confidence: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    formal_model_changed: bool = False
    trade_decision_changed: bool = False
    active_in_trade_decision: bool = False

    def validate(self) -> None:
        if self.primary_context not in ATTRIBUTIONS:
            raise ValueError("invalid_primary_context")
        if self.secondary_context and self.secondary_context not in ATTRIBUTIONS:
            raise ValueError("invalid_secondary_context")
        forbidden = {"BUY", "SELL", "ADD", "TRIM"}
        if forbidden & set(str(asdict(self)).upper().replace("'", " ").replace('"', " ").split()):
            raise ValueError("trade_instruction_forbidden")
