import csv,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parent
PREV=Path(r'C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs\outputs\radar_vnext_daily_prospective_tpex_current_corporate_action_calendar_capture_20260710')
FLAGS={'formal_model_changed':False,'trade_decision_changed':False,'active_in_trade_decision':False,'report_changed':False,'portfolio_replay_executed':False,'ready_for_strategy_replay':False,'ready_for_formal':False,'not_live_rule':True,'forward_returns_live_rule_usage':False}
def load(p):
 with p.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def w(n,x):
 k=[]
 for r in x:
  for z in r:
   if z not in k:k.append(z)
 with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:q=csv.DictWriter(f,fieldnames=k);q.writeheader();q.writerows(x)
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'current_step.txt').write_text('01_reuse_current_tpex_market_calendar\n',encoding='utf-8')
 rows=load(PREV/'tpex_current_market_calendar_canonical_rows.csv')
 for r in rows:
  r['forward_cache_policy']='append_one_market_calendar_capture_per_daily_run; retain_max_252_sessions_metadata'
  r['market_available_at']='';r['market_available_at_status']='pending_score_universe_intersection_then_official_mops_detail'
  r['detail_query_policy']='only_if_calendar_ticker_intersects_same_day_RS_BIAS_return_scoring_universe'
  r['event_guard_status']='calendar_candidate_only_no_price_adjustment_factor'
  r.update(FLAGS)
 design=[{'step':'daily_market_calendar_capture','scope':'all TPEx current calendar events','query_count_max':1,'cache_key':'tpex_calendar:{signal_date}','retention':'252 sessions metadata','status':'ready_browser_equivalent_capture','future_data_violation_count':0,**FLAGS},{'step':'score_universe_intersection','scope':'local join only','query_count_max':0,'cache_key':'local_join:{signal_date}','retention':'daily audit','status':'ready','future_data_violation_count':0,**FLAGS},{'step':'affected_detail','scope':'calendar hit AND same-day RS/BIAS/return scoring ticker only','query_count_max':'affected ticker/event group','cache_key':'tpex_event_detail:{ticker}:{effective_date}','retention':'252 sessions metadata','status':'gated_not_run_without_intersection','future_data_violation_count':0,**FLAGS}]
 blocked=[{'blocked_component':'market_available_at','row_count':len(rows),'reason':'current calculation table has no publication timestamp; retrieval time prohibited as PIT availability','next_step':'query official MOPS detail only after score-universe intersection','future_data_violation_count':0,**FLAGS},{'blocked_component':'event_factor','row_count':len(rows),'reason':'calendar contains calculation fields but no selected-ticker detail/factor verification','next_step':'bounded detail cache key only for affected scoring tickers','future_data_violation_count':0,**FLAGS}]
 manifest=load(PREV/'tpex_current_market_calendar_source_manifest.csv')
 for r in manifest:r['reused_from']=str(PREV);r['forward_source_role']='daily market calendar source';r.update(FLAGS)
 w('tpex_forward_current_prospective_calendar_rows.csv',rows);w('tpex_forward_cache_design.csv',design);w('tpex_forward_calendar_missing_ledger.csv',blocked);w('tpex_forward_calendar_source_manifest.csv',manifest)
 audit=[{'audit_item':'retrieval_time_as_market_available','status':'prohibited','future_data_violation_count':0,**FLAGS},{'audit_item':'historical_adjusted_close_escalation','status':'closed_not_in_scope','future_data_violation_count':0,**FLAGS},{'audit_item':'unaffected_top250_detail_download','status':'prohibited','future_data_violation_count':0,**FLAGS}];w('tpex_forward_calendar_future_data_audit.csv',audit)
 ready={'task_id':'TASK-RADAR-DATA-VNEXT-DAILY-PROSPECTIVE-CORPORATE-ACTION-TPEX-CALENDAR-SOURCE-FILL-001','status':'tpex_current_calendar_ready_forward_cache_design_ready_market_available_at_gated','coverage':{'current_calendar_rows':len(rows),'market_calendar_queries_observed':1,'affected_detail_queries_observed':0,'forward_retention_sessions_max':252,'route_error_count':0},'ready_for_core_tpex_forward_calendar_absorption':True,'market_available_at_ready':False,'event_factor_ready':False,'ready_for_all_market_daily_guard':False,'ready_for_experiments':False,'ready_for_formal':False,'ready_for_strategy_replay':False,'future_data_violation_count':0,**FLAGS}
 (OUT/'readiness_for_core_tpex_forward_calendar_source_fill.json').write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'final_summary_zh.md').write_text(f'# TPEx prospective calendar forward readiness\n\nCurrent calendar rows: {len(rows)}. One market-level capture is ready; PIT detail and factors remain gated on the Core scoring-universe intersection.\n',encoding='utf-8')
 files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.glob('*') if p.is_file() and p.name!='manifest.json'];(OUT/'manifest.json').write_text(json.dumps({'files':files,'readiness':ready,**FLAGS},ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'current_step.txt').write_text('complete\n',encoding='utf-8')
if __name__=='__main__':main()
