from __future__ import annotations

import argparse
import json
from pathlib import Path

from .drive_publish import _build_google_drive_credentials
from .v4d_actual_trade import load_actual_trade_state


SPREADSHEET_ID = "1OCaie8vTZWUwqJNcTbJUBIdFlI_2KEq_JvoBzakV-f0"
MODEL_SHEET = "V4-D完整交易明細 模型交易回合"
EVENT_SHEET = "V4-D完整交易明細 公司行動與股利事件"
WITHDRAWAL_SHEET = "V4-D完整交易明細 每月提領紀錄"
ACTUAL_SECTION = "實際交易追蹤｜自2026-08-05起"


def _trade_rounds(state: dict) -> list[dict]:
    rounds: list[dict] = []
    active: dict | None = None
    for trade in state.get("actual_trades", []):
        action = trade.get("action")
        if action == "v4d_buy":
            active = {"buy": trade, "sell": None}
            rounds.append(active)
        elif action == "v4d_sell" and active is not None:
            if str(active["buy"].get("ticker")).zfill(4) == str(trade.get("ticker")).zfill(4):
                active["sell"] = trade
                active = None
    return rounds


def _actual_round_row(round_number: int, trade_round: dict, state: dict) -> list:
    buy = trade_round["buy"]
    sell = trade_round.get("sell")
    position = state.get("position") or {}
    is_active = not sell and str(position.get("ticker", "")).zfill(4) == str(buy["ticker"]).zfill(4)
    pending = position.get("pending_exit") if is_active else None
    status = "已完成" if sell else "持有中"
    exit_decision = ""
    reason = "實際持有中"
    if pending:
        status = "持有中（已形成賣出訊號）"
        exit_decision = pending.get("decision_date", "")
        reason = (
            f"實際持有中；{exit_decision}形成{pending.get('reason', '賣出')}訊號，"
            f"預定{pending.get('execution_date', '')}執行"
        )
    elif sell:
        reason = sell.get("note") or "實際賣出"

    shares = int(buy["shares"])
    entry_price = float(buy["average_price"])
    entry_total = float(buy.get("total_cost", shares * entry_price))
    exit_shares = int(sell["shares"]) if sell else ""
    exit_price = float(sell["average_price"]) if sell else ""
    exit_total = float(sell.get("gross_amount", exit_shares * exit_price)) if sell else ""
    exit_net = float(sell.get("net_proceeds", exit_total - float(sell.get("fee", 0)))) if sell else ""
    pnl = float(sell.get("realized_pnl", exit_net - entry_total)) if sell else ""
    return_pct = pnl / entry_total if sell and entry_total else ""
    remaining_cash = buy.get("remaining_cash")
    if remaining_cash is not None:
        reason += f"；買進後剩餘現金{float(remaining_cash):,.0f}元"
    reason += "；券商成交均價已含交易成本"
    return [
        f"實盤{round_number}", status, str(buy["ticker"]).zfill(4), buy.get("name", ""),
        buy.get("industry", ""), buy.get("signal_date", ""), pnl, return_pct,
        buy.get("trade_date", ""), 1, shares, entry_price, entry_total, 0,
        exit_decision, sell.get("trade_date", "") if sell else "", exit_shares,
        exit_price, exit_total, float(sell.get("fee", 0)) if sell else "", 0, 0, 0, 0, 0, reason,
    ]


def _ensure_actual_section(service, sheet_name: str, width: int, header: list[str] | None = None) -> None:
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"'{sheet_name}'!A1:A1000"
    ).execute().get("values", [])
    if any(row and row[0].startswith(ACTUAL_SECTION) for row in values):
        return
    rows = [[ACTUAL_SECTION]]
    if header:
        rows.append(header)
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def _replace_actual_rows(service, rows: list[list]) -> None:
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"'{MODEL_SHEET}'!A1:Z1000"
    ).execute().get("values", [])
    section_index = next((i for i, row in enumerate(values) if row and row[0].startswith(ACTUAL_SECTION)), None)
    if section_index is None:
        raise RuntimeError("Actual-trading section is missing from the model-round sheet.")
    header_row = section_index + 2
    first_data_row = header_row + 1
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{MODEL_SHEET}'!A{first_data_row}:Z1000",
        body={},
    ).execute()
    if rows:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{MODEL_SHEET}'!A{first_data_row}:Z{first_data_row + len(rows) - 1}",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()


def sync_actual_state(state: dict) -> None:
    credentials, _ = _build_google_drive_credentials()
    if not credentials:
        raise RuntimeError("Google OAuth credentials are unavailable; Sheet sync was not performed.")
    from googleapiclient.discovery import build

    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    _ensure_actual_section(service, MODEL_SHEET, 26)
    rows = [_actual_round_row(i, item, state) for i, item in enumerate(_trade_rounds(state), 1)]
    _replace_actual_rows(service, rows)

    _ensure_actual_section(service, EVENT_SHEET, 8)
    _ensure_actual_section(service, WITHDRAWAL_SHEET, 12)
    print(json.dumps({"actual_rounds_synced": len(rows), "spreadsheet_id": SPREADSHEET_ID}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync actual V4-D trades to the tracking Google Sheet.")
    parser.add_argument("--state", default="data/formal_v4d_actual_trade_state.json")
    args = parser.parse_args()
    sync_actual_state(load_actual_trade_state(Path(args.state)))


if __name__ == "__main__":
    main()
