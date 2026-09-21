"""Read-only, per-artifact verification. Action success is not publication evidence."""
import io
import json
import re
import time as clock
from datetime import datetime, timedelta, time
from pathlib import Path

import requests
from .schedule_gate import (TAIPEI_TZ, ScheduleGateRules, fetch_twse_calendar,
    evaluate_schedule_gate, is_trading_day, add_recent_emergency_market_closure)
from .sheets_retry import request
from .v4d_dashboard_publish import SheetsClient

SHEETS = {
    'v4d': ('1CXwlB2ywUxOzLH5aAqymJSJJq-V5jTl_zOJAuuGk5Uk', 'V4-D Dashboard', 'V4-D每日訊號資料庫'),
    'c6_simulation': ('1_t5jrM0ZZArrmF67mpgHIqj_tPLFGu3Cpfcko1Qz_vQ', 'C6 Dashboard', 'C6每日訊號資料庫'),
    'c6_actual': ('19Xls-N_835V98_pM2TfLJSLlzKdXc6RztZfhJFEC1Dg', 'C6 Dashboard', 'C6每日訊號資料庫'),
}
PDFS = {
    'daily_pdf': '1qZXv2cB6Rf-7_zKh0DzbGW-ZFebRuD0Z',
    'weekly_pdf': '1Pev4ZIx8ctwoo0fVnSO9mJGWGw9AU9IG',
    'radar_pdf': '1yObd0fTSXKPM4Spi4MDtUti6qffAknvw',
}
DATE = r'(20\d{2}[-/]\d{2}[-/]\d{2})'


def pdf_date(key, text):
    patterns = {
        'daily_pdf': DATE + r'\s*收盤後整理',
        'weekly_pdf': DATE + r'\s*[｜|]\s*第\s*\d+\s*週',
        'radar_pdf': r'產出時間[：:]\s*' + DATE,
    }
    found = re.search(patterns[key], text)
    if not found:
        raise ValueError('Report date label missing from PDF; cannot use modifiedTime instead')
    return found[1].replace('/', '-')


def last_completed_week(target, opens, closed):
    sunday = target + timedelta(days=6 - target.weekday())
    remaining = [target + timedelta(days=i) for i in range(1, (sunday-target).days+1)]
    if not any(is_trading_day(d, opens, closed) for d in remaining):
        return target
    d = target - timedelta(days=target.weekday()+1)
    for _ in range(21):
        if is_trading_day(d, opens, closed):
            return d
        d -= timedelta(days=1)
    raise ValueError('No completed weekly trading session')


def assess(expected, observed):
    return 'current' if observed == expected else ('stale' if observed < expected else 'unexpected_future')


def audit():
    now = datetime.now(TAIPEI_TZ)
    closed = None
    for attempt in range(3):
        opens, closed = fetch_twse_calendar()
        if closed is not None:
            break
        if attempt < 2:
            clock.sleep(5)
    if closed is None:
        raise RuntimeError('Official calendar unavailable: no assumed target date')
    rules = ScheduleGateRules(time(17,15), True)
    closed = add_recent_emergency_market_closure(now, opens, closed, rules)
    target = evaluate_schedule_gate(now, opens, closed, rules=rules).target_date
    if target is None:
        raise RuntimeError('No completed session')
    weekly = last_completed_week(target, opens, closed)
    client = SheetsClient(SHEETS['v4d'][0])
    headers = client.headers
    results = {}
    for key, (sid, dashboard, database) in SHEETS.items():
        expected = target.isoformat()
        try:
            base = f'https://sheets.googleapis.com/v4/spreadsheets/{sid}'
            meta = request(requests.get, base, headers=headers,
                params={'fields':'sheets.properties.title'}, timeout=30)
            meta.raise_for_status()
            titles = {s['properties']['title'] for s in meta.json()['sheets']}
            if not {dashboard, database} <= titles:
                raise ValueError('Required Dashboard or database tab absent')
            values = []
            for a1 in [f"'{dashboard}'!B2", f"'{database}'!A1:A5000"]:
                r = request(requests.get, f'{base}/values/{requests.utils.quote(a1, safe="")}',
                    headers=headers, timeout=30)
                r.raise_for_status()
                values.append(r.json().get('values', []))
            screen = str(values[0][0][0])
            dates = [str(row[0]) for row in values[1] if row and re.fullmatch(r'20\d{2}-\d{2}-\d{2}', str(row[0]))]
            latest = max(dates) if dates else ''
            status = assess(expected, screen)
            if latest > expected or screen > expected:
                status = 'unexpected_future'
            elif not latest or screen != latest:
                status = 'inconsistent'
            results[key] = dict(status=status, expected_date=expected,
                observed_date=screen, database_date=latest)
        except Exception as exc:
            results[key] = dict(status='unavailable', expected_date=expected, error=type(exc).__name__)
    from pypdf import PdfReader
    for key, fid in PDFS.items():
        expected = (weekly if key == 'weekly_pdf' else target).isoformat()
        try:
            base = f'https://www.googleapis.com/drive/v3/files/{fid}'
            meta = request(requests.get, base, headers=headers,
                params={'fields':'mimeType,modifiedTime,size'}, timeout=30)
            meta.raise_for_status()
            if meta.json()['mimeType'] != 'application/pdf':
                raise ValueError('Expected PDF')
            if int(meta.json().get('size', 0)) > 20_000_000:
                raise ValueError('PDF exceeds audit size bound')
            raw = request(requests.get, base, headers=headers, params={'alt':'media'}, timeout=60)
            raw.raise_for_status()
            reader = PdfReader(io.BytesIO(raw.content))
            observed = pdf_date(key, reader.pages[0].extract_text())
            results[key] = dict(status=assess(expected, observed), expected_date=expected,
                observed_date=observed, pages=len(reader.pages), modified_time=meta.json()['modifiedTime'])
        except Exception as exc:
            results[key] = dict(status='unavailable', expected_date=expected, error=type(exc).__name__)
    return dict(checked_at=now.isoformat(), target_date=target.isoformat(), artifacts=results,
        all_current=all(v['status']=='current' for v in results.values()),
        formal_model_changed=False, trade_decision_changed=False)


def main():
    path = Path('publication-audit.json')
    try:
        result = audit()
    except Exception as exc:
        result = dict(all_current=False, artifacts={}, error=type(exc).__name__)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if not result['all_current']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
