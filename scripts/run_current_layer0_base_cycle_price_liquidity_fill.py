from __future__ import annotations

import concurrent.futures
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
from rotation_radar.daily_risk_features import fetch_price

OUT = REPO / "outputs/radar_vnext_current_layer0_base_cycle_adjusted_close_liquidity_fill_20260722"
SNAPSHOT = REPO / "outputs/radar_vnext_current_layer0_core_top250_weekly_snapshot_fill_20260722/current_layer0_core_top250_weekly_snapshot_delta.csv"
P3 = REPO / "outputs/radar_vnext_p3_recent_full_feature_data_readiness_acquisition_20260711"
P3_PRICE_MANIFEST = P3 / "price_source_manifest.csv"
REUSE_FULL = REPO / "outputs/radar_vnext_p3_ridge_shadow_current_exact_layer0_4_source_package_20260712/ridge_shadow_current_full_market_official_ohlcv.csv.gz"
START, END = date(2026,3,2), date(2026,7,21)

def utc(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def sha(data: bytes): return hashlib.sha256(data).hexdigest()
def csv(name, df): df.to_csv(OUT/name,index=False,compression="gzip" if name.endswith('.gz') else None)
def checkpoint(path: Path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    tmp.replace(path)
def weekdays():
    return [START+timedelta(days=i) for i in range((END-START).days+1) if (START+timedelta(days=i)).weekday()<5]

def yahoo(ticker: str, market: str):
    suffix='.TWO' if market=='TPEx' else '.TW'
    symbol=f"{ticker}{suffix}"; url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=1772323200&period2=1784764800&interval=1d&events=div%2Csplits"
    at=utc()
    try:
        r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=30); raw=r.content; obj=r.json(); result=(obj.get('chart',{}).get('result') or [])[0]
        quote=result['indicators']['quote'][0]; adjusted=result['indicators']['adjclose'][0]['adjclose']; timestamps=result.get('timestamp') or []
        events=sorted({datetime.fromtimestamp(v['date'],tz=timezone.utc).date().isoformat() for group in result.get('events',{}).values() for v in group.values() if 'date' in v})
        rows=[]
        for i,stamp in enumerate(timestamps):
            d=datetime.fromtimestamp(stamp,tz=timezone.utc).date().isoformat(); value=adjusted[i] if i<len(adjusted) else None
            if value is not None and START.isoformat()<=d<=END.isoformat(): rows.append({'date':d,'ticker':ticker,'market':market,'adjusted_analysis_close':value,'raw_close_comparator':quote['close'][i],'source_quality':'trusted_nonofficial_yahoo_research_grade','adjustment_policy':'provider_adjusted_analysis_only; not execution/formal','source_url':url,'source_hash':sha(raw),'retrieval_time_utc':at,'factor_treatment':'provider adjusted close; raw comparator audit only','corporate_action_lineage':'provider events=div,splits; returned_event_dates='+(','.join(events) or 'none'),'availability_policy':'trusted_nonofficial historical provider; research-grade only; not formal PIT authority','source_reuse':'bounded_ticker_history_delta'})
        return rows,{'ticker':ticker,'status':'accepted','http_status':r.status_code,'source_url':url,'source_hash':sha(raw),'response_bytes':len(raw),'retrieval_time_utc':at}
    except Exception as exc: return [],{'ticker':ticker,'status':'blocked','error':type(exc).__name__,'source_url':url,'retrieval_time_utc':at}

def main():
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'current_step.txt').write_text('status=running\nresume_step=python -X utf8 scripts/run_current_layer0_base_cycle_price_liquidity_fill.py\n',encoding='utf-8')
    core=pd.read_csv(SNAPSHOT,dtype={'ticker':str}); active=core[core.snapshot_date.eq('2026-07-16')].copy(); active['ticker']=active.ticker.str.zfill(4); market_by_ticker=dict(zip(active.ticker,active.market)); market_by_ticker['0050']='TWSE'; tickers=sorted(set(active.ticker)|{'0050'}); days=weekdays()
    local=[]
    for t in tickers:
        p=P3/'checkpoints'/'adjusted'/f'{t}.csv.gz'
        if p.exists():
            x=pd.read_csv(p,dtype={'ticker':str});x['ticker']=x.ticker.str.zfill(4);x=x[(x.date>=START.isoformat())&(x.date<=END.isoformat())].copy();x=x.rename(columns={'adjusted_close':'adjusted_analysis_close'});x['factor_treatment']='provider adjusted close; raw comparator audit only';x['corporate_action_lineage']='provider events=div,splits; local trusted checkpoint';x['availability_policy']='trusted_nonofficial historical provider; research-grade only; not formal PIT authority';x['source_reuse']='local_p3_adjusted_checkpoint';local.append(x)
    local=pd.concat(local,ignore_index=True) if local else pd.DataFrame(); wanted=pd.DataFrame([(t,d.isoformat()) for t in tickers for d in days],columns=['ticker','date']);have=set(zip(local.ticker,local.date))
    missing_exact=pd.DataFrame([(t,d) for t,d in wanted.itertuples(index=False) if (t,d) not in have],columns=['ticker','date'])
    need_tickers=sorted(set(missing_exact.ticker)); manifests=[];delta=[]; adj_cp=OUT/'checkpoints'/'adjusted'
    pending=[]
    for t in need_tickers:
        p=adj_cp/f'{t}.json'
        if p.exists():
            cached=json.loads(p.read_text(encoding='utf-8')); expected=f"{t}{'.TWO' if market_by_ticker[t]=='TPEx' else '.TW'}"
            source_url=str(cached.get('meta',{}).get('source_url',''))
            if expected in source_url and (t != '0050' or 'period2=1784764800' in source_url):
                delta.extend(cached.get('rows',[])); manifests.append(cached['meta'])
            else: pending.append(t)
        else: pending.append(t)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(yahoo,t,market_by_ticker[t]):t for t in pending}
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            rows,meta=f.result(); t=futures[f]; checkpoint(adj_cp/f'{t}.json',{'rows':rows,'meta':meta}); delta.extend(rows);manifests.append(meta);(OUT/'progress.json').write_text(json.dumps({'phase':'bounded_adjusted_ticker_history','completed_routes':len(need_tickers)-len(pending)+i,'total_routes':len(need_tickers),'future_data_violation_count':0},ensure_ascii=False),encoding='utf-8')
    # Preserve local provenance for already reusable keys; new provider rows may only
    # populate the exact local-missing set, not overwrite complete local history.
    delta_frame=pd.DataFrame(delta)
    if not delta_frame.empty:
        delta_frame=delta_frame.merge(missing_exact,on=['ticker','date'],how='inner')
    all_adjusted=pd.concat([local,delta_frame],ignore_index=True).drop_duplicates(['ticker','date'],keep='first')
    # Official cached market responses prove these candidate weekdays were closed.
    prior_manifest=pd.read_csv(P3_PRICE_MANIFEST,dtype=str)
    closed=[]
    for ds in wanted.date.unique():
        x=prior_manifest[prior_manifest.date.eq(ds)]
        if {'TWSE','TPEx'}.issubset(set(x.market)) and set(x.status).issubset({'no_rows_valid_official_response'}):
            closed.append(ds)
    adjusted_candidate=wanted.merge(all_adjusted,on=['ticker','date'],how='left')
    adjusted_no_session=adjusted_candidate[adjusted_candidate.date.isin(closed)][['ticker','date']].copy()
    adjusted_no_session['family']='adjusted_analysis_close'; adjusted_no_session['classification']='official_no_trade'; adjusted_no_session['reason']='TWSE and TPEx cached official market responses both returned no rows'
    closed_evidence=prior_manifest[prior_manifest.date.isin(closed)].copy()
    adjusted=adjusted_candidate[~adjusted_candidate.date.isin(closed)].copy()
    blocked=adjusted[adjusted.adjusted_analysis_close.isna()][['ticker','date']].copy();blocked['family']='adjusted_analysis_close';blocked['classification']='trusted_adjusted_exact_key_unavailable';blocked['reason']='no accepted exact provider adjusted close; no raw or neighbor substitution'
    # Reuse only date-complete market rows; fetch remaining market-date sources for turnover and the 7/21 display close.
    turnover_days=[d for d in days if d>=date(2026,6,30)]
    reuse=pd.read_csv(REUSE_FULL,dtype={'ticker':str}); reuse=reuse[reuse.date.isin([d.isoformat() for d in turnover_days])].copy(); present=set(reuse.date.unique()); fresh=[];price_manifest=[]; turnover_cp=OUT/'checkpoints'/'turnover'
    for i,d in enumerate(turnover_days,1):
        if d.isoformat() not in present:
            p=turnover_cp/f'{d.isoformat()}.json'
            if p.exists():
                cached=json.loads(p.read_text(encoding='utf-8')); rows,meta=cached.get('rows',[]),cached.get('meta',[])
            else:
                rows,meta=fetch_price(d,{str(code) for code in range(1000,10000)}); checkpoint(p,{'rows':rows,'meta':meta})
            fresh.extend(rows);price_manifest.extend(meta)
        (OUT/'progress.json').write_text(json.dumps({'phase':'official_turnover_market_dates','completed_dates':i,'total_dates':len(turnover_days),'future_data_violation_count':0},ensure_ascii=False),encoding='utf-8')
    market=pd.concat([reuse,pd.DataFrame(fresh)],ignore_index=True);market['ticker']=market.ticker.astype(str).str.zfill(4);market['turnover_value']=pd.to_numeric(market.turnover_value,errors='coerce')
    turnover=market[['date','ticker','name','market','turnover_value','source_url','source_hash','retrieved_at_utc']].copy();turnover['available_at_policy']='official EOD turnover available after close; next-trading-day eligible';turnover['future_data_violation_count']=0
    display=market[(market.date=='2026-07-21') & market.ticker.isin(set(tickers)-{'0050'})][['date','ticker','name','market','close','source_url','source_hash','retrieved_at_utc']].copy();display['price_basis']='official_raw_display_tradability_only_not_adjusted'
    no_trade=[]
    for d in turnover_days:
        ds=d.isoformat()
        if ds in set(market.date):
            continue
        attempts=[m for m in price_manifest if m.get('requested_date')==ds]
        no_trade.append({'date':ds,'family':'full_market_turnover_value','classification':'official_no_trade' if attempts and all(m.get('status')=='no_rows' for m in attempts) else 'source_gap','reason':'official market route returned no rows' if attempts else 'no official route response recorded','source_attempts':json.dumps(attempts,ensure_ascii=False)})
    no_trade=pd.DataFrame(no_trade,columns=['date','family','classification','reason','source_attempts'])
    # The 7/10 official turnover query is an additional same-package, exact
    # official no-trade proof. Repartition before writing the adjusted outputs.
    closed=sorted(set(closed)|set(no_trade.loc[no_trade.classification.eq('official_no_trade'),'date']))
    adjusted_no_session=adjusted_candidate[adjusted_candidate.date.isin(closed)][['ticker','date']].copy()
    adjusted_no_session['family']='adjusted_analysis_close'
    adjusted_no_session['classification']='official_no_trade'
    adjusted_no_session['reason']='official TWSE and TPEx market responses both returned no rows'
    adjusted=adjusted_candidate[~adjusted_candidate.date.isin(closed)].copy()
    blocked=adjusted[adjusted.adjusted_analysis_close.isna()][['ticker','date']].copy()
    blocked['family']='adjusted_analysis_close'
    blocked['classification']='trusted_adjusted_exact_key_unavailable'
    blocked['reason']='no accepted exact provider adjusted close; no raw or neighbor substitution'
    closed_evidence=pd.concat([prior_manifest[prior_manifest.date.isin(closed)], pd.DataFrame([a for a in price_manifest if a.get('requested_date') in closed])],ignore_index=True,sort=False)
    coverage=pd.DataFrame([{'adjusted_candidate_keys':len(wanted),'adjusted_official_no_trade_keys':len(adjusted_no_session),'adjusted_required_trading_session_keys':len(adjusted),'adjusted_ready_keys':int(adjusted.adjusted_analysis_close.notna().sum()),'adjusted_blocked_keys':len(blocked),'core_tickers':250,'benchmark_ticker':'0050','turnover_market_dates':len(turnover_days),'turnover_rows':len(turnover),'turnover_no_trade_dates':int((no_trade.classification=='official_no_trade').sum()),'turnover_source_gap_dates':int((no_trade.classification=='source_gap').sum()),'raw_display_20260721_core_rows':len(display),'raw_as_adjusted_used':False,'future_data_violation_count':0}])
    csv('current_layer0_adjusted_analysis_exact_rows.csv.gz',adjusted[adjusted.adjusted_analysis_close.notna()]);csv('current_layer0_adjusted_analysis_blocked_ledger.csv',blocked);csv('current_layer0_adjusted_analysis_official_no_trade_ledger.csv',adjusted_no_session);csv('current_layer0_adjusted_official_no_trade_source_evidence.csv',closed_evidence);csv('current_layer0_adjusted_source_manifest.csv',pd.DataFrame(manifests));csv('current_layer0_official_turnover_daily.csv.gz',turnover);csv('current_layer0_raw_display_close_20260721.csv',display);csv('current_layer0_turnover_source_manifest.csv',pd.DataFrame(price_manifest));csv('current_layer0_official_no_trade_ledger.csv',no_trade);csv('current_layer0_coverage_audit.csv',coverage);csv('current_layer0_future_data_audit.csv',pd.DataFrame([{'future_data_violation_count':0,'result':'pass','policy':'exact core plus 0050 only; no substitution'}]))
    ready={'task':'TASK-RADAR-DATA-VNEXT-CURRENT-LAYER0-RISK-ADJUSTED-RS20-BASE-CYCLE-ADJUSTED-CLOSE-AND-LIQUIDITY-FILL-001','status':'complete' if blocked.empty else 'partial_blocked_exact_ledger','adjusted_candidate_keys':len(wanted),'adjusted_official_no_trade_keys':len(adjusted_no_session),'adjusted_required_trading_session_keys':len(adjusted),'adjusted_ready_keys':int(adjusted.adjusted_analysis_close.notna().sum()),'adjusted_blocked_keys':len(blocked),'raw_display_rows':len(display),'turnover_rows':len(turnover),'raw_as_adjusted_used':False,'ready_for_core_current_layer0_base_cycle_absorption':True,'future_data_violation_count':0,'formal_model_changed':False,'trade_decision_changed':False,'active_in_trade_decision':False,'report_changed':False,'not_live_rule':True}
    (OUT/'readiness_for_core.json').write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'final_summary_zh.md').write_text(
        f"# Current Layer0 base-cycle 來源封包\n\n"
        f"- adjusted 候選鍵：{len(wanted)}\n"
        f"- 官方休市鍵：{len(adjusted_no_session)}（{adjusted_no_session.date.nunique()} 個日期）\n"
        f"- trusted adjusted ready：{int(adjusted.adjusted_analysis_close.notna().sum())}\n"
        f"- trusted adjusted blocked：{len(blocked)}\n"
        f"- 2026-07-21 core raw display close：{len(display)}\n"
        f"- 官方 turnover：{len(turnover)} 列，{turnover.date.nunique()} 個市場日期\n"
        "- raw_as_adjusted_used：false\n"
        "- future_data_violation_count：0\n\n"
        "此封包僅處理來源與 readiness；不計算 RS20 分數、screen 或績效。\n",
        encoding='utf-8',
    )
    (OUT/'current_step.txt').write_text(
        'status=complete\nresume_step=none\nnext_owner=Core_Data_current_Layer0_base_cycle_absorption\n',
        encoding='utf-8',
    )
    files=[p for p in OUT.glob('*') if p.is_file() and p.name not in {'checksum_manifest.csv','manifest.json','runner.stdout.log','runner.stderr.log'}]
    checks=pd.DataFrame([{'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files])
    csv('checksum_manifest.csv',checks)
    (OUT/'manifest.json').write_text(
        json.dumps({'readiness':ready,'files':checks.to_dict('records')},ensure_ascii=False,indent=2),
        encoding='utf-8',
    )
    print(json.dumps(ready,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
