"""Append-only Google Sheets publishing primitives for the C6 research account.

This module intentionally does not calculate C6 signals or fabricate a replay.
It accepts source-materialized daily snapshots and account events, persists each
version immutably, and lets the dashboard point at one selected current version.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .v4d_dashboard_publish import SheetsClient
from .v4d_simulation_account import SELL_RATE


DASHBOARD_SHEET = "C6 Dashboard"
SNAPSHOT_SHEET = "C6每日Top1~3資料庫"
LEDGER_SHEET = "C6模擬帳戶流水"
VERSION_SHEET = "C6版本快照索引"
CURRENT_POINTER_SHEET = "C6目前版本指標"
C6_INITIAL_CAPITAL = 7_000_000.0
C6_SLOT_COUNT = 3
C6_WITHDRAWAL_AMOUNT = 75_000.0

SNAPSHOT_HEADERS = [
    "model_version", "snapshot_as_of", "data_status", "signal_date", "rank", "ticker", "name",
    "market", "candidate_status", "source_manifest_hash", "immutable_snapshot_key",
]
LEDGER_HEADERS = [
    "model_version", "snapshot_as_of", "account_date", "event_sequence", "slot_id", "event_type",
    "ticker", "shares", "raw_close", "gross_amount", "transaction_cost", "net_amount", "cash_after",
    "relative_return_pct", "reason", "immutable_event_key",
]
VERSION_HEADERS = [
    "model_version", "snapshot_as_of", "data_status", "source_manifest_hash", "published_as_current",
    "created_at", "notes",
]
CURRENT_POINTER_HEADERS = ["current_model_version", "current_snapshot_as_of", "data_status", "updated_at"]


def _key(row: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in fields)


def _append_only(existing: list[list[object]], headers: list[str], rows: list[dict], fields: tuple[str, ...]) -> list[list[object]]:
    if existing and existing[0] != headers:
        raise ValueError("Existing C6 sheet schema does not match the append-only publisher contract.")
    known = {tuple(str(value) for value in row[:len(fields)]) for row in existing[1:] if len(row) >= len(fields)}
    additions: list[list[object]] = []
    for row in rows:
        key = _key(row, fields)
        values = [row.get(header, "") for header in headers]
        if key in known:
            continue
        additions.append(values)
        known.add(key)
    return additions


def select_withdrawal_slot(
    slots: list[dict], *, cash: float = 0.0, target_amount: float = C6_WITHDRAWAL_AMOUNT,
) -> dict:
    """Choose the lowest mark-vs-cost slot and estimate an exact whole-share sale."""
    if cash >= target_amount:
        return {
            "status": "cash_withdrawal", "slot_id": None, "planned_shares": 0,
            "gross_amount": target_amount, "transaction_cost": 0.0, "net_amount": target_amount,
            "relative_return_pct": None,
        }
    eligible = [
        slot for slot in slots
        if int(slot.get("shares") or 0) > 0 and float(slot.get("raw_close") or 0) > 0
        and float(slot.get("position_cost") or 0) > 0
    ]
    if not eligible:
        return {
            "status": "cash_or_flat", "slot_id": None, "planned_shares": 0,
            "gross_amount": 0.0, "transaction_cost": 0.0, "net_amount": 0.0,
            "relative_return_pct": None,
        }
    def relative_return(slot: dict) -> float:
        marked = float(slot["raw_close"]) * int(slot["shares"])
        return (marked - float(slot["position_cost"])) / float(slot["position_cost"])
    selected = min(eligible, key=lambda slot: (relative_return(slot), str(slot.get("slot_id", ""))))
    stock_target = max(0.0, target_amount - cash)
    shares = min(int(selected["shares"]), max(1, round(stock_target / float(selected["raw_close"]))))
    gross = shares * float(selected["raw_close"])
    cost = gross * SELL_RATE
    return {
        "status": "planned_stock_sale",
        "slot_id": selected.get("slot_id"),
        "ticker": selected.get("ticker"),
        "planned_shares": shares,
        "gross_amount": gross,
        "transaction_cost": cost,
        "net_amount": gross - cost,
        "cash_withdrawal_amount": min(cash, target_amount),
        "relative_return_pct": relative_return(selected),
    }


def build_dashboard_values(
    *, model_version: str, snapshot_as_of: str, data_status: str, slots: list[dict], cash: float = 0.0,
    notes: str = "",
) -> list[list[object]]:
    withdrawal = select_withdrawal_slot(slots, cash=cash)
    return [
        ["C6研究版｜每日候選與三槽模擬帳戶", ""],
        ["model_version", model_version],
        ["snapshot_as_of", snapshot_as_of],
        ["data_status", data_status],
        ["初始資金", C6_INITIAL_CAPITAL],
        ["槽數", C6_SLOT_COUNT],
        ["提領規則", "每次75,000元；持股相對成本報酬最低槽優先，整股交易"],
        ["提領候選槽", withdrawal["slot_id"] or "空手／現金"],
        ["提領候選股票", withdrawal.get("ticker", "")],
        ["預計賣出股數", withdrawal["planned_shares"]],
        ["預估成交金額", withdrawal["gross_amount"]],
        ["預估費稅", withdrawal["transaction_cost"]],
        ["預估提領淨額", withdrawal["net_amount"]],
        ["現金提領額", withdrawal.get("cash_withdrawal_amount", 0.0)],
        ["候選槽相對成本報酬", withdrawal["relative_return_pct"]],
        ["資料缺口／備註", notes],
    ]


def publish_snapshot(
    spreadsheet_id: str,
    *,
    model_version: str,
    snapshot_as_of: str,
    data_status: str,
    source_manifest_hash: str,
    snapshot_rows: list[dict],
    ledger_rows: list[dict],
    slots: list[dict],
    cash: float = 0.0,
    notes: str = "",
) -> dict:
    """Append immutable C6 data, then move the mutable dashboard pointer."""
    for row in snapshot_rows:
        row.setdefault("model_version", model_version)
        row.setdefault("snapshot_as_of", snapshot_as_of)
        row.setdefault("data_status", data_status)
        row.setdefault("source_manifest_hash", source_manifest_hash)
        row.setdefault(
            "immutable_snapshot_key",
            "|".join(_key(row, ("model_version", "snapshot_as_of", "signal_date", "rank"))),
        )
    for row in ledger_rows:
        row.setdefault("model_version", model_version)
        row.setdefault("snapshot_as_of", snapshot_as_of)
        row.setdefault(
            "immutable_event_key",
            "|".join(_key(row, ("model_version", "snapshot_as_of", "account_date", "event_sequence"))),
        )
    client = SheetsClient(spreadsheet_id)
    snapshot_existing = client.get(f"'{SNAPSHOT_SHEET}'!A1:K50000")
    ledger_existing = client.get(f"'{LEDGER_SHEET}'!A1:P50000")
    version_existing = client.get(f"'{VERSION_SHEET}'!A1:G50000")
    snapshot_additions = _append_only(
        snapshot_existing, SNAPSHOT_HEADERS, snapshot_rows,
        ("model_version", "snapshot_as_of", "signal_date", "rank"),
    )
    ledger_additions = _append_only(
        ledger_existing, LEDGER_HEADERS, ledger_rows,
        ("model_version", "snapshot_as_of", "account_date", "event_sequence"),
    )
    version_row = {
        "model_version": model_version, "snapshot_as_of": snapshot_as_of, "data_status": data_status,
        "source_manifest_hash": source_manifest_hash, "published_as_current": True, "created_at": snapshot_as_of,
        "notes": notes,
    }
    version_additions = _append_only(version_existing, VERSION_HEADERS, [version_row], ("model_version", "snapshot_as_of"))
    if not snapshot_existing:
        client.update(f"'{SNAPSHOT_SHEET}'!A1", [SNAPSHOT_HEADERS, *snapshot_additions])
    elif snapshot_additions:
        client.update(f"'{SNAPSHOT_SHEET}'!A{len(snapshot_existing) + 1}", snapshot_additions)
    if not ledger_existing:
        client.update(f"'{LEDGER_SHEET}'!A1", [LEDGER_HEADERS, *ledger_additions])
    elif ledger_additions:
        client.update(f"'{LEDGER_SHEET}'!A{len(ledger_existing) + 1}", ledger_additions)
    if not version_existing:
        client.update(f"'{VERSION_SHEET}'!A1", [VERSION_HEADERS, *version_additions])
    elif version_additions:
        client.update(f"'{VERSION_SHEET}'!A{len(version_existing) + 1}", version_additions)
    pointer = [[model_version, snapshot_as_of, data_status, snapshot_as_of]]
    client.clear(f"'{CURRENT_POINTER_SHEET}'!A1:D2")
    client.update(f"'{CURRENT_POINTER_SHEET}'!A1", [CURRENT_POINTER_HEADERS, *pointer])
    dashboard = build_dashboard_values(
        model_version=model_version, snapshot_as_of=snapshot_as_of, data_status=data_status, slots=slots, cash=cash, notes=notes,
    )
    client.clear(f"'{DASHBOARD_SHEET}'!A1:B40")
    client.update(f"'{DASHBOARD_SHEET}'!A1", dashboard)
    return {
        "model_version": model_version,
        "snapshot_as_of": snapshot_as_of,
        "data_status": data_status,
        "snapshot_rows_appended": len(snapshot_additions),
        "ledger_rows_appended": len(ledger_additions),
        "version_rows_appended": len(version_additions),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an immutable C6 research snapshot to its Google Sheet.")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    result = publish_snapshot(args.spreadsheet_id, **payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
