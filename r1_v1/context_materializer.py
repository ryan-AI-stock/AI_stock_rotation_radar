from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from statistics import median

from .context_engine import (attribute_context, build_company_context, build_flow_context,
    build_market_context, build_theme_context, build_valuation_context)
from .context_monitor import build_context_monitor
from .context_store import ContextHistoryStore


def _load(path: str | Path, default=None):
    p=Path(path); return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})


def materialize(*, market_path="data/r1/daily_market_latest.json",
                theme_path="config/r1_v02_themes.json",
                transition_path="data/r1/transition/latest.json",
                event_context_path="data/r1/context_event_latest.json",
                valuation_path="data/r1/valuation_history/2026-10-22.json",
                daily_source_path="data/r1/daily_sources/2026-10-22.json",
                evidence_root="data/r1_v1", history_path="data/r1_v1/context_history.jsonl",
                monitor_path="data/r1_v1/context_monitor/latest.json") -> dict:
    market_raw=_load(market_path); config=_load(theme_path); transition=_load(transition_path)
    event_raw=_load(event_context_path); valuation_raw=_load(valuation_path); daily=_load(daily_source_path)
    date=market_raw.get("date"); rows=market_raw.get("rows",[])
    by_ticker={str(r["ticker"]).zfill(4):r for r in rows}
    up=sum((r.get("daily_return") or 0)>0 for r in rows); down=sum((r.get("daily_return") or 0)<0 for r in rows)
    breadth=up/len(rows) if rows else None
    market=build_market_context({"return_1d":transition.get("taiex_return"),
        "return_5d":None,"return_20d":None,"breadth":breadth,"up_count":up,"down_count":down,
        "turnover":sum(r.get("turnover_value") or 0 for r in rows) if rows else None,
        "turnover_ratio_20d":median([(r.get("turnover_value") or 0)/r["avg_turnover_20d"] for r in rows if r.get("avg_turnover_20d")]),
        "foreign_flow":None,"tw50_return_1d":None,"vix":None,"us_market_return_1d":None,
        "usd_twd_return_1d":None}, f"{date}T13:30:00+08:00")
    theme_members={t["id"]:[str(m[0]).zfill(4) for m in t["members"]] for t in config.get("themes",[])}
    theme_by_ticker={ticker:tid for tid,members in theme_members.items() for ticker in members}
    theme_contexts={}
    for tid,members in theme_members.items():
        theme_rows=[]
        for ticker in members:
            r=by_ticker.get(ticker)
            if r: theme_rows.append({"return_1d":r.get("daily_return"),"return_5d":r.get("return_1w"),
                "return_20d":r.get("return_1m"),"turnover_ratio_20d":(r.get("turnover_value") or 0)/r["avg_turnover_20d"] if r.get("avg_turnover_20d") else None})
        theme_contexts[tid]=build_theme_context(tid,theme_rows,market)
    events={str(r["ticker"]).zfill(4):r for r in event_raw.get("rows",[])}
    vals={str(r["ticker"]).zfill(4):r for r in valuation_raw.get("rows",[])}
    chips={str(r["ticker"]).zfill(4):r for r in daily.get("chip_rows",[]) if r.get("family")=="institutional"}
    evidence_events=_load(Path(evidence_root)/"evidence_monitor/latest.json")
    history=ContextHistoryStore(history_path); produced=[]
    for ticker,row in by_ticker.items():
        tid=theme_by_ticker.get(ticker)
        if not tid: continue
        theme=theme_contexts[tid]; evt=events.get(ticker,{})
        company=build_company_context(ticker,{"return_1d":row.get("daily_return"),
            "return_5d":row.get("return_1w"),"return_20d":row.get("return_1m")},market,theme,
            {"positive":evt.get("positive_event_count",0),"negative":evt.get("negative_event_count",0),
             "latest_claim":(evt.get("evidence_urls") or [None])[0]})
        val=vals.get(ticker,{})
        valuation=build_valuation_context(ticker,{"forward_pe":val.get("forward_pe"),
            "historical_percentile":val.get("forward_pe_percentile_5y"),
            "eps_revision":None,"pb":None,"ev_ebitda":None,"valuation_change_1w":None,
            "valuation_change_4w":None,"valuation_change_12w":None})
        chip=chips.get(ticker,{})
        def number(v):
            try:return float(v)
            except (TypeError,ValueError):return None
        close=number(row.get("raw_close"))
        foreign_shares=number(chip.get("foreign_net")); trust_shares=number(chip.get("trust_net")); dealer_shares=number(chip.get("dealer_net"))
        flow=build_flow_context(ticker,{"foreign_flow":foreign_shares*close if foreign_shares is not None and close is not None else None,
            "investment_trust_flow":trust_shares*close if trust_shares is not None and close is not None else None,
            "dealer_flow":dealer_shares*close if dealer_shares is not None and close is not None else None,
            "margin_change":number(chip.get("margin_change")),"short_interest_change":number(chip.get("short_change")),
            "turnover":row.get("turnover_value"),"turnover_ratio_20d":(row.get("turnover_value") or 0)/row["avg_turnover_20d"] if row.get("avg_turnover_20d") else None,
            "large_holder_change":None})
        snap=attribute_context(date=date,evaluation_time=f"{date}T13:30:00+08:00",ticker=ticker,
            theme_id=tid,market=market,theme=theme,company=company,valuation=valuation,flow=flow,
            supporting_evidence=evt.get("evidence_urls") or [],contradicting_evidence=[])
        history.append(snap); produced.append(asdict(snap))
    monitor=build_context_monitor(history.rows(),monitor_path)
    return {"date":date,"snapshot_count":len(produced),"market_state":market.market_state,
        "theme_count":len(theme_contexts),"phase1_evidence_counts":evidence_events.get("counts",{}),
        "monitor_status":monitor["status"],"formal_model_changed":False,
        "trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--valuation",default="data/r1/valuation_history/2026-10-22.json")
    parser.add_argument("--daily-source",default="data/r1/daily_sources/2026-10-22.json")
    args=parser.parse_args(); print(json.dumps(materialize(valuation_path=args.valuation,daily_source_path=args.daily_source),ensure_ascii=False))


if __name__=="__main__": main()
