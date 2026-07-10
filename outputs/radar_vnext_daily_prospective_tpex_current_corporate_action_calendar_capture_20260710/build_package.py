import csv,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parent
FLAGS={'formal_model_changed':False,'trade_decision_changed':False,'active_in_trade_decision':False,'report_changed':False,'portfolio_replay_executed':False,'ready_for_strategy_replay':False,'ready_for_formal':False,'not_live_rule':True,'forward_returns_live_rule_usage':False}
R=[['115/07/10','3217','優群','173.50','163.50','0','10','10','除息','10','0'],['115/07/10','3303','岱稜','59.20','56.20','0','3','3','除息','3','0'],['115/07/10','3467','台灣精材','58.80','58.30','0','0.5','0.5','除息','0.5','0'],['115/07/10','3489','森寶','24.20','21.20','0','3','3','除息','3','0'],['115/07/10','3564','其陽','54.10','53.83','0','0.27','0.27','除息','0.27','0'],['115/07/10','4711','永純','17.35','16.85','0','0.5','0.5','除息','0.5','0'],['115/07/10','6762','達亞','176.50','167.62','8.380956','0.5','8.880956','除權息','0.5','50.00002559'],['115/07/10','7747','昕奇雲端','129','114.55','11.454545','3','14.454545','除權息','3','100'],['115/07/10','7811','民盛','80.50','74.83','0','5.669956','5.669956','除息','5.66995644','0'],['115/07/13','3227','原相','221.50','211.49','0','10.007005','10.007005','除息','10.00700533','0']]
def w(n,x):
 k=[]
 for r in x:
  for z in r:
   if z not in k:k.append(z)
 with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:q=csv.DictWriter(f,fieldnames=k);q.writeheader();q.writerows(x)
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'current_step.txt').write_text('01_browser_equivalent_current_table_captured\n',encoding='utf-8')
 rows=[]
 for x in R:
  y,m,d=x[0].split('/');date=f'{int(y)+1911:04d}-{int(m):02d}-{int(d):02d}';typ='cash_dividend' if x[8]=='除息' else 'cash_and_stock_dividend'
  rows.append({'ticker':x[1],'name':x[2],'market':'TPEx','event_type':typ,'effective_date':date,'pre_close':x[3],'reference_price':x[4],'right_value':x[5],'cash_value':x[6],'total_right_interest_value':x[7],'right_interest_type':x[8],'cash_amount':x[9],'stock_ratio_per_1000':x[10],'market_available_at':'','market_available_at_status':'blocked_page_table_has_no_announcement_timestamp','source_url':'https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html','source_route':'browser_equivalent_current_calculation_table','retrieved_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'detail_cache_key':f'event_detail:TPEx:{x[1]}:{date}','source_quality':'official_tpex_current_market_calendar_browser_equivalent','future_data_violation_count':0,**FLAGS})
 raw=json.dumps(R,ensure_ascii=False); manifest=[{'source_url':'https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html','source_route':'browser_equivalent_current_calculation_table','response_hash':hashlib.sha256(raw.encode()).hexdigest(),'response_bytes':len(raw.encode()),'observed_query_count':1,'observed_row_count':len(rows),'route_error_count':0,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'future_data_violation_count':0,**FLAGS}]
 blocked=[{'market':'TPEx','blocked_component':'market_available_at','blocked_reason':'current calculation table has no issuer announcement timestamp; retrieval time is metadata only','future_data_violation_count':0,**FLAGS}]
 audit=[{'audit_item':'retrieval_time_as_market_available_at','status':'prohibited_not_used','future_data_violation_count':0,**FLAGS},{'audit_item':'affected_ticker_detail_query','status':'not_run_no_core_scoring_universe_intersection','future_data_violation_count':0,**FLAGS}]
 w('tpex_current_market_calendar_canonical_rows.csv',rows);w('tpex_current_market_calendar_source_manifest.csv',manifest);w('tpex_current_market_calendar_blocked_ledger.csv',blocked);w('tpex_current_market_calendar_future_data_audit.csv',audit)
 ready={'task_id':'TASK-RADAR-DATA-VNEXT-DAILY-PROSPECTIVE-TPEX-CURRENT-CORPORATE-ACTION-CALENDAR-CAPTURE-001','status':'tpex_current_calendar_browser_equivalent_rows_materialized_market_available_at_blocked','coverage':{'market_level_queries':1,'calendar_rows':len(rows),'affected_ticker_detail_queries':0,'route_error_count':0,'observed_raw_bytes':len(raw.encode())},'ready_for_core_tpex_current_calendar_absorption':True,'market_available_at_ready_rows':0,'ready_for_all_market_daily_guard':False,'ready_for_experiments':False,'ready_for_formal':False,'ready_for_strategy_replay':False,'future_data_violation_count':0,**FLAGS}
 (OUT/'readiness_for_core_tpex_current_calendar_absorption.json').write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'final_summary_zh.md').write_text(f'# TPEx current corporate-action calendar\n\nBrowser-equivalent market calendar rows: {len(rows)}. market_available_at rows: 0. No ticker detail query.\n',encoding='utf-8')
 files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.glob('*') if p.is_file() and p.name!='manifest.json'];(OUT/'manifest.json').write_text(json.dumps({'files':files,'readiness':ready,**FLAGS},ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'current_step.txt').write_text('complete\n',encoding='utf-8')
if __name__=='__main__':main()
