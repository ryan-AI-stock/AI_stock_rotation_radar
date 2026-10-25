from __future__ import annotations

from dataclasses import asdict
from statistics import median, pstdev
from typing import Any

from .context_schema import (CompanyContext, ContextSnapshot, FlowContext,
                             MarketContext, ThemeContext, ValuationContext)
from .ids import stable_id


def _confidence(known: int, total: int) -> str:
    ratio = known / total if total else 0
    return "HIGH" if ratio >= .8 else "MEDIUM" if ratio >= .5 else "LOW"


def build_market_context(data: dict[str, Any], evaluation_time: str) -> MarketContext:
    required = ["return_1d", "return_5d", "return_20d", "breadth", "turnover_ratio_20d"]
    unknowns = [key for key in required if data.get(key) is None]
    r1, r5, r20, breadth = (data.get(k) for k in required[:4])
    if r1 is not None and breadth is not None and r1 <= -.04 and breadth <= .20:
        state = "PANIC"
    elif (r5 is not None and r5 <= -.03) or (r1 is not None and breadth is not None and r1 <= -.015 and breadth < .40):
        state = "RISK_OFF"
    elif r1 is not None and breadth is not None and r1 >= .015 and breadth >= .60 and data.get("prior_state") in {"RISK_OFF", "PANIC"}:
        state = "RECOVERY"
    elif r20 is not None and breadth is not None and r20 > 0 and breadth >= .55:
        state = "RISK_ON"
    elif len(unknowns) >= 3:
        state = "UNKNOWN"
    else:
        state = "NEUTRAL"
    optional = ["tw50_return_1d", "foreign_flow", "vix", "us_market_return_1d", "usd_twd_return_1d"]
    unknowns += [key for key in optional if data.get(key) is None]
    return MarketContext(evaluation_time, r1, r5, r20, breadth, data.get("up_count"),
        data.get("down_count"), data.get("limit_up_count"), data.get("limit_down_count"),
        data.get("turnover"), data.get("turnover_ratio_20d"), data.get("foreign_flow"),
        data.get("tw50_return_1d"), data.get("vix"), data.get("us_market_return_1d"),
        data.get("usd_twd_return_1d"), list(data.get("major_macro_event_links") or []),
        state, _confidence(5-len([x for x in unknowns if x in required]), 5), sorted(set(unknowns)))


def build_theme_context(theme_id: str, rows: list[dict[str, Any]], market: MarketContext,
                        theme_event_state: str = "UNKNOWN") -> ThemeContext:
    valid = [r for r in rows if r.get("return_1d") is not None]
    if not valid:
        return ThemeContext(theme_id, None, None, None, None, None, None, None, None, None,
                            "UNKNOWN", theme_event_state, "UNKNOWN", "LOW", ["theme_returns"])
    r1s = [r["return_1d"] for r in valid]
    r5s = [r["return_5d"] for r in valid if r.get("return_5d") is not None]
    r20s = [r["return_20d"] for r in valid if r.get("return_20d") is not None]
    eq1, med1 = sum(r1s)/len(r1s), median(r1s)
    breadth = sum(x > 0 for x in r1s)/len(r1s)
    relative = eq1-market.return_1d if market.return_1d is not None else None
    turnover_ratios = [r["turnover_ratio_20d"] for r in valid if r.get("turnover_ratio_20d") is not None]
    volume_state = "UNKNOWN" if not turnover_ratios else ("EXPANDING" if median(turnover_ratios)>=1.25 else "CONTRACTING" if median(turnover_ratios)<=.75 else "NORMAL")
    if relative is None:
        state = "UNKNOWN"
    elif relative <= -.02 and breadth <= .35:
        state = "SELL_OFF"
    elif relative >= .02 and breadth >= .65:
        state = "ACCELERATING"
    elif eq1 > 0 and breadth >= .55 and market.market_state in {"RISK_OFF", "PANIC"}:
        state = "RECOVERING"
    elif relative < -.005 or (r5s and sum(r5s)/len(r5s) < 0):
        state = "COOLING"
    else:
        state = "STABLE"
    unknowns = [name for name, values in (("return_5d", r5s), ("return_20d", r20s)) if not values]
    return ThemeContext(theme_id, eq1, sum(r5s)/len(r5s) if r5s else None,
        sum(r20s)/len(r20s) if r20s else None, breadth, med1, eq1, relative,
        sum(x>0 for x in r1s), sum(x<0 for x in r1s), volume_state,
        theme_event_state, state, _confidence(len(valid), len(rows)), unknowns)


def build_company_context(ticker: str, row: dict[str, Any], market: MarketContext,
                          theme: ThemeContext, event_summary: dict[str, Any] | None = None,
                          own_return_history: list[float] | None = None) -> CompanyContext:
    event_summary = event_summary or {}
    r1 = row.get("return_1d")
    rel_market = r1-market.return_1d if r1 is not None and market.return_1d is not None else None
    rel_theme = r1-theme.equal_weight_return_1d if r1 is not None and theme.equal_weight_return_1d is not None else None
    history = [x for x in (own_return_history or []) if x is not None]
    sigma = pstdev(history) if len(history)>=10 else None
    z = (r1-(sum(history)/len(history)))/sigma if r1 is not None and sigma and sigma>0 else None
    neg, pos = int(event_summary.get("negative", 0)), int(event_summary.get("positive", 0))
    if r1 is None or rel_theme is None:
        state = "UNKNOWN"
    elif rel_theme <= -.04 and neg > 0:
        state = "IDIOSYNCRATIC_STRESS"
    elif rel_theme >= .04 and pos > 0:
        state = "IDIOSYNCRATIC_STRENGTH"
    elif rel_theme >= .02:
        state = "OUTPERFORMING"
    elif rel_theme <= -.02:
        state = "UNDERPERFORMING"
    else:
        state = "IN_LINE"
    unknowns = [k for k in ("return_1d", "return_5d", "return_20d") if row.get(k) is None]
    if sigma is None: unknowns.append("own_volatility_history")
    return CompanyContext(ticker, r1, row.get("return_5d"), row.get("return_20d"),
        rel_market, rel_theme, rel_theme, pos+neg, neg, pos,
        event_summary.get("latest_fact"), event_summary.get("latest_claim"), state, z,
        _confidence(3-len([x for x in unknowns if x.startswith("return_")]), 3), unknowns)


def build_valuation_context(ticker: str, data: dict[str, Any] | None) -> ValuationContext:
    data = data or {}; pct = data.get("historical_percentile")
    if pct is None: state = "UNKNOWN"
    elif pct <= .10: state = "DEPRESSED"
    elif pct <= .35: state = "BELOW_NORMAL"
    elif pct < .70: state = "NORMAL"
    elif pct < .90: state = "ABOVE_NORMAL"
    else: state = "EXTREME"
    fields = ["forward_pe", "pb", "ev_ebitda", "historical_percentile", "eps_revision",
              "valuation_change_1w", "valuation_change_4w", "valuation_change_12w"]
    unknowns = [f for f in fields if data.get(f) is None]
    return ValuationContext(ticker, *(data.get(f) for f in fields), state,
                            _confidence(len(fields)-len(unknowns), len(fields)), unknowns)


def build_flow_context(ticker: str, data: dict[str, Any] | None) -> FlowContext:
    data = data or {}; flow = data.get("foreign_flow"); turnover = data.get("turnover")
    ratio = flow/turnover if flow is not None and turnover not in (None, 0) else None
    volume_ratio = data.get("turnover_ratio_20d")
    if ratio is None: state = "UNKNOWN"
    elif ratio <= -.15 and volume_ratio is not None and volume_ratio >= 1.5: state = "CAPITULATION"
    elif ratio >= .10 and volume_ratio is not None and volume_ratio >= 1.5: state = "CROWDED"
    elif ratio <= -.03: state = "DISTRIBUTING"
    elif ratio >= .03: state = "ACCUMULATING"
    else: state = "NEUTRAL"
    fields = ["foreign_flow", "investment_trust_flow", "dealer_flow", "margin_change",
              "short_interest_change", "turnover_ratio_20d", "large_holder_change"]
    unknowns = [f for f in fields if data.get(f) is None]
    return FlowContext(ticker, data.get("foreign_flow"), data.get("investment_trust_flow"),
        data.get("dealer_flow"), data.get("margin_change"), data.get("short_interest_change"),
        volume_ratio, data.get("large_holder_change"), state,
        _confidence(len(fields)-len(unknowns), len(fields)), unknowns)


def attribute_context(*, date: str, evaluation_time: str, ticker: str, theme_id: str,
                      market: MarketContext, theme: ThemeContext, company: CompanyContext,
                      valuation: ValuationContext, flow: FlowContext,
                      supporting_evidence: list[str] | None = None,
                      contradicting_evidence: list[str] | None = None) -> ContextSnapshot:
    primary, secondary, anomaly = "UNKNOWN", None, "UNKNOWN"
    if company.company_context_state in {"IDIOSYNCRATIC_STRESS", "IDIOSYNCRATIC_STRENGTH"}:
        primary, anomaly = "COMPANY", "COMPANY_SPECIFIC_MOVE"
    elif theme.theme_context_state in {"SELL_OFF", "ACCELERATING", "RECOVERING"} and market.market_state not in {"RISK_OFF", "PANIC"}:
        primary, anomaly = "THEME", "THEME_DRIVEN_MOVE"
    elif market.market_state in {"RISK_OFF", "PANIC", "RECOVERY"} and company.company_context_state in {"IN_LINE", "UNDERPERFORMING", "OUTPERFORMING"}:
        primary, anomaly = "MARKET", "MARKET_DRIVEN_MOVE"
        if theme.theme_context_state in {"SELL_OFF", "COOLING", "RECOVERING"}: secondary = "THEME"
    elif flow.flow_state not in {"UNKNOWN", "NEUTRAL"}:
        primary, anomaly = "FLOW", "FLOW_POSITIONING_MOVE"
    elif valuation.valuation_state in {"DEPRESSED", "EXTREME"}:
        primary, anomaly = "VALUATION", "VALUATION_COMPRESSION_OR_EXPANSION"
    if primary != "UNKNOWN" and secondary:
        combined = "MIXED"
    else:
        combined = primary
    mispricing = bool(market.market_state in {"RISK_OFF", "PANIC"} and
        theme.theme_context_state == "SELL_OFF" and company.stock_return_1d is not None and
        company.stock_return_1d < (theme.equal_weight_return_1d or 0)-.02 and
        company.company_negative_event_count == 0)
    unknowns = sorted(set(market.unknowns+theme.unknowns+company.unknowns+valuation.unknowns+flow.unknowns))
    confidence = "LOW" if primary == "UNKNOWN" or len(unknowns)>8 else "MEDIUM" if unknowns else "HIGH"
    snapshot = ContextSnapshot(stable_id("context", date, ticker, evaluation_time), date,
        evaluation_time, ticker, theme_id, asdict(market), asdict(theme), asdict(company),
        asdict(valuation), asdict(flow), combined, secondary, anomaly, mispricing, confidence,
        supporting_evidence or [], contradicting_evidence or [], unknowns)
    snapshot.validate(); return snapshot
