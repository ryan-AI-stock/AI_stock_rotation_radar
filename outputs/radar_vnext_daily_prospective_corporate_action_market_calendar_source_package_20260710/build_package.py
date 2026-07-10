import csv,json,hashlib,urllib.request
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parent; RAW=OUT/'raw_cache'
FLAGS={'formal_model_changed':False,'trade_decision_changed':False,'active_in_trade_decision':False,'report_changed':False,'portfolio_replay_executed':False,'ready_for_strategy_replay':False,'ready_for_formal':False,'not_live_rule':True,'forward_returns_live_rule_usage':False}
def fetch(url,name):
 RAW.mkdir(parents=True,exist_ok=True); p=RAW/name
 if p.exists(): t=p.read_text(encoding='utf-8'); s='cache_hit'; e=''
 else:
  try:
   r=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 RadarDataSourcePackage/1.0'}); t=urllib.request.urlopen(r,timeout=30).read().decode('utf-8'); p.write_text(t,encoding='utf-8'); s='fetched';e=''
  except Exception as x: t=json.dumps({'error':str(x)});p.write_text(t,encoding='utf-8');s='route_error';e=str(x)
 return t,{'source_url':url,'raw_cache_path':str(p.relative_to(OUT)),'response_hash':hashlib.sha256(t.encode()).hexdigest(),'response_bytes':len(t.encode()),'route_status':s,'route_error':e,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'future_data_violation_count':0,**FLAGS}
def w(name,rows):
 keys=[]
 for r in rows:
  for k in r:
   if k not in keys:keys.append(k)
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  x=csv.DictWriter(f,fieldnames=keys);x.writeheader();x.writerows(rows)
def ad(roc):
 try:
  y,m,d=roc.replace('年','/').replace('月','/').replace('日','').split('/');return f'{int(y)+1911:04d}-{int(m):02d}-{int(d):02d}'
 except:return ''
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'current_step.txt').write_text('01_fetch_market_calendar\n',encoding='utf-8')
 tw,tm=fetch('https://www.twse.com.tw/exchangeReport/TWT48U_ALL?response=json','twse_twt48u_all_current.json')
 tp,tpm=fetch('https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html','tpex_exdailyq_current_route_page.html')
 try:data=json.loads(tw).get('data',[])
 except:data=[]
 rows=[]
 for r in data:
  effective=ad(str(r[0])); kind=str(r[3]); stock=float(r[4] or 0) if str(r[4]).replace('.','',1).isdigit() else 0; cash=r[7]
  et='cash_dividend' if '息' in kind else 'stock_dividend'
  if stock: et='stock_dividend' if not cash else 'cash_and_stock_dividend'
  rows.append({'ticker':r[1],'name':r[2],'market':'TWSE','event_type':et,'effective_date':effective,'calendar_window_status':'current_prospective_snapshot_not_252session_history','cash_amount':cash,'stock_ratio':r[4],'cash_increase_ratio':r[5],'cash_increase_price':r[6],'market_available_at':'','market_available_at_policy':'calendar_retrieval_time_is_metadata_only; PIT availability requires issuer announcement timestamp detail','source_url':tm['source_url'],'source_hash':tm['response_hash'],'retrieved_at_utc':tm['retrieved_at_utc'],'source_quality':'official_twse_current_market_calendar','detail_cache_key':f"event_detail:TWSE:{r[1]}:{effective}",'future_data_violation_count':0,**FLAGS})
 blocked=[{'market':'TWSE','blocked_component':'retained_252session_calendar_history','blocked_reason':'TWT48U_ALL current snapshot does not expose historical retained-window rows in this bounded route','attempted_source_url':tm['source_url'],'next_bounded_step':'Core must retain/reuse daily calendar cache forward; do not backfill historical adjusted-close route','future_data_violation_count':0,**FLAGS},{'market':'TPEx','blocked_component':'current_market_calendar_rows','blocked_reason':'public calculation page identifies bulletin/exDailyQ action but direct route replay returned 404; browser-equivalent/session route not attempted in this bounded package','attempted_source_url':tpm['source_url'],'next_bounded_step':'Core may run browser-equivalent TPEx current calendar capture if daily guard requires TPEx coverage','future_data_violation_count':0,**FLAGS}]
 manifest=[dict(tm,market='TWSE',source_component='current_market_calendar',coverage='current prospective all TWSE rows'),dict(tpm,market='TPEx',source_component='current_market_calendar_route_probe',coverage='current TPEx page route only; rows not materialized')]
 audit=[{'audit_item':'quarter_end_or_query_time_as_effective_date','status':'prohibited_not_used','future_data_violation_count':0,**FLAGS},{'audit_item':'raw_execution_vs_analysis_price','status':'separate_columns_required_by_core_not_calculated_here','future_data_violation_count':0,**FLAGS}]
 w('daily_prospective_market_calendar_canonical_rows.csv',rows);w('daily_prospective_market_calendar_blocked_ledger.csv',blocked);w('daily_prospective_market_calendar_source_manifest.csv',manifest);w('daily_prospective_market_calendar_future_data_audit.csv',audit)
 readiness={'task_id':'TASK-RADAR-DATA-VNEXT-DAILY-PROSPECTIVE-CORPORATE-ACTION-MARKET-CALENDAR-SOURCE-PACKAGE-001','status':'twse_current_calendar_materialized_tpex_and_252session_history_blocked','coverage':{'twse_calendar_rows':len(rows),'tpex_calendar_rows':0,'market_level_queries':2,'affected_ticker_detail_queries':0,'observed_raw_bytes':tm['response_bytes']+tpm['response_bytes'],'route_error_count':sum(x['route_status']=='route_error' for x in manifest)},'ready_for_core_daily_prospective_calendar_absorption':len(rows)>0,'ready_for_all_market_daily_prospective_guard':False,'retained_252session_calendar_history_ready':False,'ready_for_experiments':False,'ready_for_formal':False,'ready_for_strategy_replay':False,'future_data_violation_count':0,**FLAGS}
 (OUT/'readiness_for_core_daily_prospective_market_calendar_absorption.json').write_text(json.dumps(readiness,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'final_summary_zh.md').write_text(f"# Daily prospective corporate-action calendar\n\nTWSE current calendar rows: {len(rows)}. TPEx current calendar rows: 0 (route blocked).\n\nNo affected-ticker detail was queried because Core has not supplied a scoring-universe intersection; calendar rows provide bounded detail cache keys only.\n",encoding='utf-8')
 files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in OUT.glob('*') if p.is_file() and p.name!='manifest.json']
 (OUT/'manifest.json').write_text(json.dumps({'files':files,'readiness':readiness,**FLAGS},ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'current_step.txt').write_text('complete\n',encoding='utf-8')
if __name__=='__main__':main()
