"""Exact-date C6 macro evaluation; unknown inputs never become False."""
from __future__ import annotations
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.request import urlopen
import pandas as pd
from .base_cycle_daily_report import ReportDataNotReady
from .schedule_gate import fetch_twse_calendar, is_trading_day

CBC_URL = 'https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day'

def evaluate(target, adjusted, fx, sessions, settlement):
    target, settlement = pd.Timestamp(target), pd.Timestamp(settlement)
    sessions = pd.DatetimeIndex(sorted(set(pd.Timestamp(d) for d in sessions)))
    distance = len(sessions[(sessions > target) & (sessions <= settlement)])
    if target > settlement or distance > 3:
        return {'macro_triple': False, 'settlement_distance_td': distance}
    dates = sessions[sessions <= target][-79:]
    market = adjusted.loc[adjusted.ticker.eq('0050')].copy()
    market['date'] = pd.to_datetime(market.date)
    close = market.set_index('date').adjusted_analysis_close.reindex(dates)
    if len(dates) != 79 or close.isna().any():
        raise ReportDataNotReady('macro_0050_exact_79_session_window_missing')
    bias = close / close.rolling(60,min_periods=60).mean() - 1
    market_high = bool(bias.iloc[-1] >= bias.iloc[-20:].quantile(.8))
    result = {'settlement_distance_td': distance, 'market_bias_high20': market_high}
    if not market_high:
        return dict(result, macro_triple=False, usd_high20=None)
    frame = fx.copy(); frame['date'] = pd.to_datetime(frame.date)
    values = frame.set_index('date').ntd_per_usd.reindex(dates[-20:])
    if values.isna().any() or (values <= 0).any():
        raise ReportDataNotReady('macro_CBC_exact_20_session_window_missing')
    high = bool(values.iloc[-1] >= values.quantile(.8))
    return dict(result, usd_high20=high, macro_triple=high)

def load_cbc(cache, target, offline=False):
    path = Path(cache) / f'cbc-{target:%Y%m%d}.json'
    if not path.exists():
        if offline: raise ReportDataNotReady('macro_CBC_cache_missing')
        for attempt in range(3):
            try:
                with urlopen(CBC_URL,timeout=30) as response: raw=response.read()
                data=json.loads(raw)
                if not isinstance(data,list): raise ValueError('CBC schema')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                break
            except (OSError,ValueError) as exc:
                if attempt==2: raise ReportDataNotReady(f'macro_CBC_fetch_failed:{exc}') from exc
                time.sleep(2)
    raw=path.read_bytes(); rows=[]
    for item in json.loads(raw):
        dates=[str(v) for k,v in item.items() if k!='NTD_USD' and re.fullmatch(r'\d{8}',str(v))]
        if len(dates)!=1: raise ReportDataNotReady('macro_CBC_date_schema')
        rows.append({'date':pd.to_datetime(dates[0]),'ntd_per_usd':float(item['NTD_USD'])})
    frame=pd.DataFrame(rows)
    if frame.date.duplicated().any(): raise ReportDataNotReady('macro_CBC_duplicate_date')
    return frame,hashlib.sha256(raw).hexdigest()

def resolve(target, adjusted, cache, offline=False):
    opened,closed=fetch_twse_calendar()
    if closed is None: raise ReportDataNotReady('macro_calendar_unavailable')
    settlement=target.replace(day=1)+pd.offsets.WeekOfMonth(week=2,weekday=2)
    # Exceptional settlement changes require explicit authority, not inference.
    if not is_trading_day(settlement.date(),opened,closed):
        raise ReportDataNotReady('macro_exceptional_settlement_authority_required')
    sessions=[d for d in pd.date_range(target-pd.Timedelta(days=180),max(target,settlement)) if is_trading_day(d.date(),opened,closed)]
    empty=pd.DataFrame(columns=['date','ntd_per_usd'])
    try:
        return evaluate(target,adjusted,empty,sessions,settlement)
    except ReportDataNotReady as exc:
        if str(exc)!='macro_CBC_exact_20_session_window_missing': raise
    fx,digest=load_cbc(cache,target,offline)
    return dict(evaluate(target,adjusted,fx,sessions,settlement),cbc_source_url=CBC_URL,cbc_source_hash=digest)
