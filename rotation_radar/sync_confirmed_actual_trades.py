from __future__ import annotations

import argparse
import json

from .v4d_dashboard_publish import SheetsClient


DASHBOARD = "C6 Dashboard"
TRADES = "C6實際交易紀錄"


def sync(spreadsheet_id: str, *, trade_date: str) -> dict:
    client = SheetsClient(spreadsheet_id)
    dashboard = client.get(f"'{DASHBOARD}'!A1:H60")
    ledger = client.get(f"'{TRADES}'!A1:R1000")
    if not dashboard or not ledger:
        raise ValueError("C6 actual dashboard or ledger unavailable")
    matches = [index for index, row in enumerate(dashboard, start=1)
               if len(row) > 1 and str(row[1]).startswith("2327 國巨｜")]
    if len(matches) != 1:
        raise ValueError(f"expected one 國巨 holding row, found {len(matches)}")
    if any(len(row) > 1 and str(row[1]).startswith("2303 聯電｜") for row in dashboard):
        raise ValueError("聯電 already exists in C6 actual holdings")
    row_number = matches[0]
    slot = dashboard[row_number - 1][0]
    cost = 148.13 * 1200
    client.update(f"'{DASHBOARD}'!A{row_number}:H{row_number}", [[
        slot, "2303 聯電｜1200股", 148.13, cost, "", "", "", "",
    ]])
    existing_keys = {(str(row[0]), str(row[3]), str(row[5])) for row in ledger[1:] if len(row) > 5}
    records = [
        [trade_date, slot, "實際成交（人工）", "2327", "國巨", "賣出", 651, 5000,
         3255000, "", "現金／淨收待券商資料", "", "", "", "", "", "",
         "Ryan人工賣出；舊帳4,000股與本次5,000股差1,000股，未推估淨收與已實現損益。"],
        [trade_date, slot, "實際成交（人工）", "2303", "聯電", "買進", 148.13, 1200,
         cost, "含交易成本", "現金餘額待Ryan後續回報", "", "", "", "", "", "",
         f"實際買入日{trade_date}；每股成本148.13元含交易成本；Ryan人工成交，非C6模型指令。"],
    ]
    next_row = len(ledger) + 1
    for record in records:
        key = (record[0], record[3], record[5])
        if key in existing_keys:
            continue
        client.update(f"'{TRADES}'!A{next_row}:R{next_row}", [record])
        next_row += 1
    holding_check = client.get(f"'{DASHBOARD}'!A{row_number}:H{row_number}")
    ledger_check = client.get(f"'{TRADES}'!A1:R1000")
    if not holding_check or holding_check[0][1] != "2303 聯電｜1200股":
        raise RuntimeError("C6 actual holding readback mismatch")
    for ticker, action in (("2327", "賣出"), ("2303", "買進")):
        if not any(len(row) > 5 and str(row[0]) == trade_date and str(row[3]) == ticker
                   and str(row[5]) == action for row in ledger_check[1:]):
            raise RuntimeError(f"C6 actual trade readback mismatch: {ticker}")
    return {"trade_date": trade_date, "holding": "2303 聯電｜1200股",
            "ledger_readback_verified": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--trade-date", required=True)
    args = parser.parse_args()
    print(json.dumps(sync(args.spreadsheet_id, trade_date=args.trade_date), ensure_ascii=False))


if __name__ == "__main__":
    main()
