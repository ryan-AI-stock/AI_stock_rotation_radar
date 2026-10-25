from __future__ import annotations

from dataclasses import replace
from typing import Any

from .ids import stable_id
from .reasoning_schema import (CausalEdge,CausalNode,DisconfirmationPass,
    ExpectationAnalysis,HypothesisRecord,ReasoningSnapshot,ThesisRecord)
from .store import now_iso


def initial_thesis(stock_id:str,theme_name:str,bottleneck_thesis:str,date:str,
                   evidence_ids:list[str],unknowns:list[str]) -> ThesisRecord:
    thesis=ThesisRecord(stable_id("thesis",stock_id,"STRUCTURAL",1),stock_id,date,None,1,
        "STRUCTURAL_THESIS",f"{theme_name}：{bottleneck_thesis}","STRUCTURAL","UNKNOWN",date,
        [bottleneck_thesis],["需求不及預期","競爭或供給擴張","公司執行落後"],
        ["公司官方指引轉弱","關鍵需求或售價反轉","多個獨立來源確認供需結構改變"],
        evidence_ids,[],unknowns,[],"LEGACY_PARTIAL")
    thesis.validate(); return thesis


def build_causal_chain(thesis:ThesisRecord,theme_name:str,date:str):
    statements=["AI基礎設施需求維持",f"{theme_name}形成供應鏈瓶頸或關鍵載體",
                f"{thesis.stock_id}可把題材需求轉化為營收或毛利", "獲利修正反映營運兌現", "估值與價格反映新資訊"]
    statuses=["INFERENCE","INFERENCE","UNKNOWN","UNKNOWN","UNKNOWN"]
    nodes=[CausalNode(stable_id("node",thesis.thesis_id,i),thesis.thesis_id,i,s,statuses[i],
                      thesis.supporting_evidence_ids if i<2 else [],date,"LOW") for i,s in enumerate(statements)]
    edges=[CausalEdge(stable_id("edge",thesis.thesis_id,i),thesis.thesis_id,nodes[i].node_id,
            nodes[i+1].node_id,"INFERENCE" if i==0 else "UNKNOWN",[],date,"LOW") for i in range(4)]
    return nodes,edges


def assess_thesis_update(current:ThesisRecord,evidence:list[dict[str,Any]],date:str)->ThesisRecord:
    relevant=[e for e in evidence if e.get("kind")!="PRICE_ONLY"]
    supports={e.get("lineage") for e in relevant if e.get("stance")=="SUPPORTS" and e.get("lineage")}
    counters={e.get("lineage") for e in relevant if e.get("stance")=="CONTRADICTS" and e.get("lineage")}
    critical=any(e.get("critical") and e.get("stance")=="CONTRADICTS" for e in relevant)
    status="BROKEN" if critical else "WEAKENED" if len(counters)>=2 else "STRENGTHENED" if len(supports)>=2 else "UNCHANGED"
    if status=="UNCHANGED": return replace(current,status="UNCHANGED",last_reviewed_at=date)
    ids=[e["evidence_id"] for e in relevant]
    updated=replace(current,thesis_id=stable_id("thesis",current.stock_id,current.thesis_type,current.thesis_version+1),
        thesis_version=current.thesis_version+1,effective_from=date,status=status,last_reviewed_at=date,
        supporting_evidence_ids=current.supporting_evidence_ids+[e["evidence_id"] for e in relevant if e.get("stance")=="SUPPORTS"],
        contradicting_evidence_ids=current.contradicting_evidence_ids+[e["evidence_id"] for e in relevant if e.get("stance")=="CONTRADICTS"],
        changed_by_evidence_ids=ids)
    updated.validate(); return updated


def _hyp(stock,context,kind,statement,support,missing,falsification,horizon="SHORT"):
    created=context["evaluation_time"]
    record=HypothesisRecord(stable_id("hypothesis",stock,context["snapshot_id"],kind),stock,None,
        context["snapshot_id"],kind,statement,"UNRESOLVED","LOW",horizon,created,created,
        list(dict.fromkeys(support)),[],missing,falsification,"5TD" if horizon=="SHORT" else "1-3M",[])
    record.validate(); return record


def generate_competing_hypotheses(context:dict)->list[HypothesisRecord]:
    stock=context["ticker"]; market=context["market_context"]; theme=context["theme_context"]
    company=context["company_context"]; valuation=context["valuation_context"]
    evidence=context.get("supporting_evidence",[]); results=[]
    if market["market_state"] in {"RISK_OFF","PANIC","RECOVERY"}:
        results.append(_hyp(stock,context,"SYSTEMIC_SELL_OFF","價格異常主要由整體市場風險偏好驅動",evidence,
            ["TAIEX_5D_20D","external_market_context"],["市場恢復但個股持續顯著落後"],"SHORT"))
    if theme["theme_context_state"] in {"SELL_OFF","COOLING"}:
        results.append(_hyp(stock,context,"THEME_DERATING","題材整體評價或資金偏好下降",evidence,
            ["theme_event_confirmation"],["題材breadth與相對報酬持續回升"],"MEDIUM"))
    if company["company_negative_event_count"]>0 or company["company_context_state"]=="IDIOSYNCRATIC_STRESS":
        results.append(_hyp(stock,context,"COMPANY_THESIS_DAMAGE","公司特有資訊可能削弱原有營運假設",evidence,
            ["independent_company_confirmation"],["公司官方資料否定負面推論"],"MEDIUM"))
    if context.get("possible_mispricing_candidate"):
        results.append(_hyp(stock,context,"FUNDAMENTAL_MISPRICING","價格跌幅可能大於已確認基本面變化",evidence,
            ["fresh_company_facts","expectation_gap"],["新增官方負面Fact或指引下修"],"MEDIUM"))
    if valuation["valuation_state"] in {"EXTREME","ABOVE_NORMAL"}:
        results.append(_hyp(stock,context,"VALUATION_COMPRESSION","估值位階可能放大價格修正",evidence,
            ["valuation_change_history"],["估值回到正常但價格仍異常"],"MEDIUM"))
    if len(results)<2:
        results.append(_hyp(stock,context,"TEMPORARY_EXECUTION_DELAY","短期執行或資訊時差可能造成價格偏離",evidence,
            ["company_delivery_data"],["延遲跨越預期窗口或公司下修指引"],"SHORT"))
    return results[:4]


def apply_counter_evidence(hyp:HypothesisRecord,counter_ids:list[str],critical=False)->HypothesisRecord:
    status="REJECTED" if critical else "WEAKENING" if counter_ids else hyp.status
    confidence="LOW" if counter_ids else hyp.confidence
    return replace(hyp,status=status,confidence=confidence,
                   contradicting_evidence_ids=list(dict.fromkeys(hyp.contradicting_evidence_ids+counter_ids)),last_updated=now_iso())


def expectation_analysis(stock,event_id,expected,actual,source_ids,evaluation_time):
    if expected is None or actual is None: diff="UNKNOWN"; unknowns=["expected_state" if expected is None else "actual_state"]
    elif actual>expected: diff="BETTER_THAN_EXPECTED"; unknowns=[]
    elif actual<expected: diff="WORSE_THAN_EXPECTED"; unknowns=[]
    else: diff="IN_LINE"; unknowns=[]
    return ExpectationAnalysis(stable_id("expectation",stock,event_id,evaluation_time),stock,event_id,
        None if expected is None else str(expected),None if actual is None else str(actual),diff,source_ids,
        "LOW" if unknowns else "MEDIUM",evaluation_time,unknowns)


def disconfirmation_pass(leading:HypothesisRecord,context:dict)->DisconfirmationPass:
    evidence=context.get("contradicting_evidence",[])
    return DisconfirmationPass(stable_id("disconfirm",leading.hypothesis_id),leading.hypothesis_id,evidence,
        "市場或題材共同波動可能是更簡單解釋","已分離Market與Company Context，但歷史仍短",
        "Event與價格同時發生不等於因果","缺少完整預期差資料，可能已被市場反映",
        "把短期Context誤當結構性變化",list(dict.fromkeys(evidence+context.get("supporting_evidence",[]))),now_iso())


def reasoning_snapshot(date,stock,context,thesis,hypotheses,disconfirm):
    leading=hypotheses[0] if hypotheses else None
    unknowns=list(dict.fromkeys(thesis.unknowns+context.get("unknowns",[])+sum((h.missing_evidence for h in hypotheses),[])))
    snap=ReasoningSnapshot(stable_id("reasoning",date,stock,context["snapshot_id"],thesis.thesis_version),
        date,stock,context["snapshot_id"],thesis.thesis_version,thesis.status,
        [h.hypothesis_id for h in hypotheses],leading.hypothesis_id if leading else None,
        [h.hypothesis_id for h in hypotheses[1:]],list(dict.fromkeys(sum((h.supporting_evidence_ids for h in hypotheses),[]))),
        list(dict.fromkeys(sum((h.contradicting_evidence_ids for h in hypotheses),[]))),unknowns,"LOW",
        list(dict.fromkeys(sum((h.falsification_conditions for h in hypotheses),[]))),
        list(dict.fromkeys(sum((h.missing_evidence for h in hypotheses),[]))),"UNCHANGED",disconfirm.pass_id if disconfirm else None)
    snap.validate(); return snap
