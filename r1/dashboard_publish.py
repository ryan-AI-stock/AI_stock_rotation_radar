from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs
from rotation_radar.v4d_dashboard_publish import SheetsClient


DASHBOARD = "R1 Dashboard"
SIGNALS = "R1每日訊號資料庫"
TRADES = "R1模擬交易紀錄"


def _keyed_signal_rows(rows: list[list[object]]) -> dict[tuple[str, str], list[object]]:
    return {
        (str(row[0]), str(row[1]).zfill(4)): row
        for row in rows
        if len(row) >= 2 and str(row[0]).strip() and str(row[1]).strip()
    }


def publish_payload(spreadsheet_id: str, payload_path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    tabs = payload["tabs"]
    validate_tabs(tabs)
    report_date = str(payload["date"])
    client = SheetsClient(spreadsheet_id)

    dashboard_rows = tabs[DASHBOARD]
    client.clear(f"'{DASHBOARD}'!A1:E100")
    client.update(f"'{DASHBOARD}'!A1", dashboard_rows)

    signal_header = list(TAB_SCHEMAS[SIGNALS])
    existing = client.get(f"'{SIGNALS}'!A1:Y10000")
    existing_rows = existing[1:] if existing and existing[0] == signal_header else []
    keyed = _keyed_signal_rows(existing_rows)
    keyed.update(_keyed_signal_rows(tabs[SIGNALS][1:]))
    merged = [keyed[key] for key in sorted(keyed)]
    client.clear(f"'{SIGNALS}'!A1:Y10000")
    client.update(f"'{SIGNALS}'!A1", [signal_header, *merged])

    trade_header = list(TAB_SCHEMAS[TRADES])
    trade_rows = tabs[TRADES][1:]
    existing_trades = client.get(f"'{TRADES}'!A1:P10000")
    if trade_rows:
        client.clear(f"'{TRADES}'!A1:P10000")
        client.update(f"'{TRADES}'!A1", [trade_header, *trade_rows])
    elif not existing_trades or existing_trades[0] != trade_header:
        client.clear(f"'{TRADES}'!A1:P10000")
        client.update(f"'{TRADES}'!A1", [trade_header])

    dashboard_check = client.get(f"'{DASHBOARD}'!A1:E100")
    signal_check = client.get(f"'{SIGNALS}'!A1:Y10000")
    trade_check = client.get(f"'{TRADES}'!A1:P10000")
    current_signals = [row for row in signal_check[1:] if row and str(row[0]) == report_date]
    expected_signals = len(tabs[SIGNALS]) - 1
    if not dashboard_check or dashboard_check[0] != list(TAB_SCHEMAS[DASHBOARD]):
        raise RuntimeError("R1 Dashboard readback header mismatch")
    if any(len(row) < 5 or str(row[4]) != report_date for row in dashboard_check[1:]):
        raise RuntimeError("R1 Dashboard readback date mismatch")
    if len(current_signals) != expected_signals:
        raise RuntimeError(
            f"R1 signal readback mismatch date={report_date} expected={expected_signals} actual={len(current_signals)}"
        )
    if not trade_check or trade_check[0] != trade_header:
        raise RuntimeError("R1 transaction readback header mismatch")
    if not trade_rows and len(trade_check) != 1:
        raise RuntimeError("R1 transaction tab must remain header-only before action approval")
    return {
        "spreadsheet_id": spreadsheet_id,
        "date": report_date,
        "dashboard_rows": len(dashboard_check) - 1,
        "signal_rows_for_date": len(current_signals),
        "transaction_rows": len(trade_check) - 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish and read back the three-tab R1 research dashboard.")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--payload", default="data/r1/dashboard_payload.json")
    args = parser.parse_args()
    print(json.dumps(publish_payload(args.spreadsheet_id, args.payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
