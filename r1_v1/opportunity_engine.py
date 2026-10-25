from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .ids import stable_id
from .opportunity_schema import DimensionAssessment,PortfolioResearchState,RelativeOpportunity


FUNDAMENTAL={"structural_bottleneck","thesis_strength","earnings_visibility","eps_revision","catalyst"}


def _cmp(dimension,a,b,evidence,unknowns,lower_is_better=False):
    if a is None or b is None:
        return DimensionAssessment(dimension,"UNKNOWN",a,b,[],unknowns or [dimension])
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        delta=b-a
        if abs(delta)<1e-12: state="TIE"
        elif (delta<0 if lower_is_better else delta>0): state="CHALLENGER_ADVANTAGE"
        else: state="HOLDING_ADVANTAGE"
    else:
        order={"BROKEN":0,"WEAKENED":1,"UNKNOWN":2,"UNCHANGED":3,"STRENGTHENED":4,
               "SELL_OFF":0,"COOLING":1,"UNKNOWN_THEME":2,"STABLE":3,"RECOVERING":4,"ACCELERATING":5,
               "DISTRIBUTING":0,"CROWDED":1,"NEUTRAL":2,"CAPITULATION":2,"ACCUMULATING":3}
        av=order.get(str(a),0);bv=order.get(str(b),0)
        state="TIE" if av==bv else "CHALLENGER_ADVANTAGE" if bv>av else "HOLDING_ADVANTAGE"
    return DimensionAssessment(dimension,state,a,b,list(dict.fromkeys(evidence)),unknowns)


def compare_holding_to_challenger(date:str,holding:dict[str,Any],challenger:dict[str,Any])->RelativeOpportunity:
    hc,hx=holding["context"],challenger["context"]
    hr,cr=holding["reasoning"],challenger["reasoning"]
    def ev(x): return x.get("supporting_evidence",[])+x.get("counter_evidence",[])
    dims=[
      _cmp("structural_bottleneck",holding.get("structural_evidence_count"),challenger.get("structural_evidence_count"),ev(cr),["structural_bottleneck"]),
      _cmp("thesis_strength",hr.get("thesis_state"),cr.get("thesis_state"),ev(hr)+ev(cr),[]),
      _cmp("earnings_visibility",holding.get("earnings_visibility"),challenger.get("earnings_visibility"),ev(cr),["earnings_visibility"]),
      _cmp("eps_revision",hc["valuation_context"].get("eps_revision"),hx["valuation_context"].get("eps_revision"),ev(cr),["eps_revision"]),
      _cmp("valuation_vs_own_history",hc["valuation_context"].get("historical_percentile"),hx["valuation_context"].get("historical_percentile"),ev(cr),["historical_percentile"],True),
      _cmp("price_expectation_catchup",hc["company_context"].get("relative_to_theme"),hx["company_context"].get("relative_to_theme"),ev(cr),["relative_to_theme"]),
      _cmp("catalyst",hc["company_context"].get("company_positive_event_count"),hx["company_context"].get("company_positive_event_count"),ev(cr),[]),
      _cmp("risk",hc["company_context"].get("company_negative_event_count"),hx["company_context"].get("company_negative_event_count"),ev(hr)+ev(cr),[],True),
      _cmp("market_context",hc["market_context"].get("market_state"),hx["market_context"].get("market_state"),[],[]),
      _cmp("theme_context",hc["theme_context"].get("theme_context_state"),hx["theme_context"].get("theme_context_state"),ev(cr),[]),
      _cmp("price_flow_risk",hc["flow_context"].get("flow_state"),hx["flow_context"].get("flow_state"),ev(hr)+ev(cr),[]),
    ]
    for d in dims:d.validate()
    known=[d for d in dims if d.state!="UNKNOWN"]
    ca=[d.dimension for d in known if d.state=="CHALLENGER_ADVANTAGE"]
    ha=[d.dimension for d in known if d.state=="HOLDING_ADVANTAGE"]
    cf=[x for x in ca if x in FUNDAMENTAL]
    evidence=list(dict.fromkeys(sum((d.evidence_ids for d in dims),[])))
    known_fundamental=[d for d in known if d.dimension in FUNDAMENTAL]
    if len(known)<6 or len(known_fundamental)<3 or not evidence: state="DATA_INSUFFICIENT"
    elif len(ca)>=4 and len(cf)>=2 and not ({"thesis_strength","earnings_visibility"}&set(ha)): state="STRONG_ADVANTAGE"
    elif len(ca)>=2 and cf: state="MODERATE_ADVANTAGE"
    elif ca: state="WATCH"
    else: state="NO_ADVANTAGE"
    unknown=list(dict.fromkeys(sum((d.unknowns for d in dims if d.state=="UNKNOWN"),[])))
    out=RelativeOpportunity(stable_id("opportunity",date,holding["ticker"],challenger["ticker"]),date,
        holding["ticker"],challenger["ticker"],[asdict(d) for d in dims],state,
        "LOW" if unknown or not evidence else "MEDIUM",ca,ha,evidence,hr.get("counter_evidence",[])+cr.get("counter_evidence",[]),unknown)
    out.validate();return out


def research_state(date,portfolio_id,stock_id,comparison:RelativeOpportunity|None,history:list[dict],critical_thesis_break=False,hysteresis_required=3):
    prior=next((x for x in reversed(history) if x["portfolio_id"]==portfolio_id and x["stock_id"]==stock_id),None)
    current=prior["state"] if prior else "HOLD"
    if critical_thesis_break: candidate="TRIM_REVIEW"
    elif comparison is None or comparison.opportunity_state=="DATA_INSUFFICIENT": candidate="WAIT_FOR_EVIDENCE"
    elif comparison.opportunity_state=="STRONG_ADVANTAGE": candidate="ROTATION_REVIEW"
    elif comparison.opportunity_state in {"MODERATE_ADVANTAGE","WATCH"}: candidate="WATCH"
    else: candidate="HOLD"
    same=prior and prior.get("candidate_state")==candidate
    count=(prior.get("persistence_count",0)+1) if same else 1
    state=candidate if critical_thesis_break or candidate in {"HOLD","WAIT_FOR_EVIDENCE"} or count>=hysteresis_required else current
    out=PortfolioResearchState(stable_id("portfolio_state",date,portfolio_id,stock_id,comparison.comparison_id if comparison else "none"),date,
      portfolio_id,stock_id,state,prior["state"] if prior else None,candidate,count,hysteresis_required,
      comparison.challenger_stock_id if comparison else None,comparison.comparison_id if comparison else None,
      [f"candidate={candidate}",f"persistence={count}/{hysteresis_required}"]+(comparison.challenger_advantages if comparison else []),
      comparison.supporting_evidence_ids if comparison else [],comparison.unknowns if comparison else ["challenger_comparison"])
    out.validate();return out

