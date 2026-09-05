"""Share score0 signals with the actual account, without simulating actual fills.

This publisher owns only the signal database and the Dashboard signal/status cells.
Holdings, cash, actual transactions and exit history remain user-account authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .c6_dashboard_publish import build_public_snapshot_values
from .v4d_dashboard_publish import SheetsClient

SIGNALS = 'C6每日訊號資料庫'
DASHBOARD = 'C6 Dashboard'
ACTUAL_TRADES = 'C6實際交易紀錄'


def signal_formulas() -> dict[str, list[list[object]]]:
    # Use explicit rank lookups: fewer than three qualified names stay empty.
    source = f"'{SIGNALS}'"
    result = {f"'{DASHBOARD}'!B2": [[f'=IF(COUNT({source}!A2:A)=0,"",MAX({source}!A2:A))']]}
    for rank in range(1, 4):
        condition = f'{source}!A2:A=$B$2,{source}!B2:B={rank}'
        name = f'IFNA(INDEX(FILTER({source}!C2:C&" "&{source}!D2:D,{condition}),1),"無其他合格股票")'
        score = f'IFNA(INDEX(FILTER({source}!F2:F,{condition}),1),"")'
        result[f"'{DASHBOARD}'!B{rank+5}:D{rank+5}"] = [[f'={name}', f'={score}',
            f'=IF(C{rank+5}="","", "通過C6條件，當日排名第{rank}")']]
    return result


def publish(spreadsheet_id: str, payload: dict) -> dict:
    expected_date = str(payload['ranking_snapshot_as_of'])
    rows = build_public_snapshot_values(payload['snapshot_rows'])
    latest = [row for row in rows[1:] if str(row[0]) == expected_date]
    if not latest or max(str(row[0]) for row in rows[1:]) != expected_date:
        raise ValueError('Actual account signal source date mismatch')
    client = SheetsClient(spreadsheet_id)
    # Guard against accidentally targeting the simulation workbook.
    actual_ledger = client.get(f"'{ACTUAL_TRADES}'!A1:R1000")
    if not actual_ledger:
        raise ValueError('Actual account ledger is missing; refusing to publish')
    before = client.get(f"'{DASHBOARD}'!A10:D31")
    if not before:
        raise ValueError('Actual account holdings scaffold is missing')
    client.clear(f"'{SIGNALS}'!A1:G1000")
    client.update(f"'{SIGNALS}'!A1", rows)
    for address, values in signal_formulas().items():
        client.update(address, values)
    client.update(f"'{DASHBOARD}'!B27", [['每日排名已接通共用C6來源；持倉退出與公司行動核對尚未完成']])
    db = client.get(f"'{SIGNALS}'!A1:G{len(rows)}")
    actual = [row for row in db[1:] if row and str(row[0]) == expected_date]
    if [(str(r[1]), str(r[2]) if len(r) > 2 else '') for r in actual] != [
        (str(r[1]), str(r[2]) if len(r) > 2 else '') for r in latest
    ]:
        raise RuntimeError('Actual signal database read-back mismatch')
    if client.get(f"'{DASHBOARD}'!B2") != [[expected_date]]:
        raise RuntimeError('Actual Dashboard date read-back mismatch')
    for rank in range(1, 4):
        expected = next((r for r in latest if str(r[1]) == str(rank)), None)
        expected_name = f'{expected[2]} {expected[3]}' if expected else '無其他合格股票'
        if client.get(f"'{DASHBOARD}'!B{rank+5}") != [[expected_name]]:
            raise RuntimeError(f'Actual Dashboard rank {rank} read-back mismatch')
    if client.get(f"'{ACTUAL_TRADES}'!A1:R1000") != actual_ledger:
        raise RuntimeError('Actual trades changed during signal publication')
    # The only allowed change in this rectangle is the integration status B27.
    after = client.get(f"'{DASHBOARD}'!A10:D31")
    before[17][1] = after[17][1]
    if before != after:
        raise RuntimeError('Actual account fields changed during signal publication')
    return {'signal_date': expected_date, 'signal_readback_verified': True,
            'actual_trades_changed': False, 'account_exit_tracking_ready': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spreadsheet-id', required=True)
    parser.add_argument('--payload', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.spreadsheet_id, json.loads(args.payload.read_text(encoding='utf-8'))), ensure_ascii=False))


if __name__ == '__main__':
    main()
