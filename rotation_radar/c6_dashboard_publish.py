"""Append-only Google Sheets publishing primitives for the C6 research account.

This module intentionally does not calculate C6 signals or fabricate a replay.
It accepts source-materialized daily snapshots and account events, persists each
version immutably, and lets the dashboard point at one selected current version.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .v4d_dashboard_publish import SheetsClient
from .v4d_simulation_account import SELL_RATE, second_wednesday


DASHBOARD_SHEET = "C6 Dashboard"
SNAPSHOT_SHEET = "C6每日Top1~3資料庫"
LEDGER_SHEET = "C6模擬帳戶流水"
VERSION_SHEET = "C6版本快照索引"
CURRENT_POINTER_SHEET = "C6目前版本指標"
C6_INITIAL_CAPITAL = 7_000_000.0
C6_SLOT_COUNT = 3
C6_WITHDRAWAL_AMOUNT = 75_000.0
C6_FORWARD_START_DATE = "2026-08-05"
C6_WITHDRAWAL_START_DATE = "2026-09-09"
DEFAULT_HISTORICAL_BENCHMARK_PATH = Path("data/c6_historical_64_benchmark.json")

SNAPSHOT_HEADERS = [
    "model_version", "snapshot_as_of", "data_status", "signal_date", "rank", "ticker", "name",
    "market", "candidate_status", "source_manifest_hash", "immutable_snapshot_key",
]
PUBLIC_SNAPSHOT_HEADERS = [
    "訊號日期", "順位", "股票代號", "股票名稱", "官方收盤價", "C6分數", "合格/不合格原因", "預定執行日", "資料狀態",
]
LEDGER_HEADERS = [
    "模型版本", "帳本資料截至", "帳務日期", "當日事件順序", "槽位", "事件",
    "股票代號", "股數", "官方收盤價", "成交或市值金額", "交易成本", "現金增減", "事件後現金",
    "相對買進成本報酬", "原因", "事件識別碼",
]
VERSION_HEADERS = [
    "版本名稱", "資料日期", "目前可用程度", "資料驗證碼", "是否顯示為目前版本",
    "建立日期", "備註",
]
CURRENT_POINTER_HEADERS = ["目前版本", "正式帳本日期", "目前狀態", "最後更新"]
LEDGER_FIELDS = [
    "model_version", "snapshot_as_of", "account_date", "event_sequence", "slot_id", "event_type",
    "ticker", "shares", "raw_close", "gross_amount", "transaction_cost", "net_amount", "cash_after",
    "relative_return_pct", "reason", "immutable_event_key",
]
VERSION_FIELDS = [
    "model_version", "snapshot_as_of", "data_status", "source_manifest_hash", "published_as_current",
    "created_at", "notes",
]


def _key(row: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in fields)


def _append_only(existing: list[list[object]], headers: list[str], rows: list[dict], fields: tuple[str, ...]) -> list[list[object]]:
    if existing and existing[0] != headers:
        raise ValueError("Existing C6 sheet schema does not match the append-only publisher contract.")
    field_indexes = [headers.index(field) for field in fields]
    known = {
        tuple(str(row[index]) if index < len(row) else "" for index in field_indexes)
        for row in existing[1:]
    }
    additions: list[list[object]] = []
    for row in rows:
        key = _key(row, fields)
        values = [row.get(header, "") for header in headers]
        if key in known:
            continue
        additions.append(values)
        known.add(key)
    return additions


def _human_data_status(data_status: str) -> str:
    if "whole_share_replay_pit_blocked" in data_status:
        return "整股帳本已建立至目前權威日期；後續交易判斷仍待補齊"
    if "no_whole_share_replay" in data_status or "replay_not_materialized" in data_status:
        return "候選排名已完成；三槽模擬帳戶仍在完整重算"
    if data_status in {"complete", "ready", "formal_ready"}:
        return "資料完整"
    return "研究資料更新中"


def _human_rank_reason(rank: int) -> str:
    if rank == 0:
        return "當日沒有股票通過C6買進條件"
    return f"通過C6條件，列入當日Top{rank}"


def _human_source_status(rank: int) -> str:
    return "排名資料與官方收盤價完整" if rank else "當日候選結果已確認"


def _human_event(event_type: str) -> str:
    return {"buy": "買進", "sell": "賣出", "daily_mark": "每日收盤估值", "withdrawal": "每月提領"}.get(event_type, event_type)


def _human_model_version(model_version: str) -> str:
    if "forward-known-segment" in model_version:
        return "C6三槽整股模擬"
    if model_version.endswith("-v2"):
        return "新版排名"
    return "初版排名"


def _human_version_status(data_status: str) -> str:
    if "whole_share_replay_pit_blocked" in data_status:
        return "整股帳本已核對至權威日期；後續交易尚未完成"
    if "no_whole_share_replay" in data_status or "replay_not_materialized" in data_status:
        return "只有候選排名，尚未建立整股交易帳本"
    return "資料完整"


def _human_candidate_status(row: dict) -> str:
    status = str(row.get("candidate_status") or "")
    if status:
        return "已列入當日排名"
    return "排名資料已完成"


def _execution_date(signal_date: str) -> str:
    if not signal_date:
        return ""
    return (pd.Timestamp(signal_date) + pd.offsets.BDay(1)).date().isoformat()


def build_public_snapshot_values(snapshot_rows: list[dict]) -> list[list[object]]:
    """Return one current, de-duplicated, human-readable Top1~3 table."""
    unique: dict[tuple[str, int], dict] = {}
    for row in snapshot_rows:
        signal_date = str(row.get("signal_date") or "")
        rank = int(row.get("rank") or 0)
        if signal_date and rank in {0, 1, 2, 3}:
            unique[(signal_date, rank)] = row
    values = [PUBLIC_SNAPSHOT_HEADERS]
    for (signal_date, rank), row in sorted(unique.items()):
        if rank == 0:
            values.append([
                signal_date,
                "無候選" if "no_eligible" in str(row.get("candidate_status")) else "PIT待補",
                "", "", "", "", _human_rank_reason(0),
                str(row.get("planned_execution_date") or ""), _human_source_status(0),
            ])
            continue
        score = row.get("score", row.get("c6_score", row.get("selection_score", "")))
        values.append([
            signal_date,
            rank,
            str(row.get("ticker") or ""),
            str(row.get("name") or ""),
            row.get("display_close", row.get("raw_close", row.get("close", ""))),
            score,
            _human_rank_reason(rank),
            str(row.get("planned_execution_date") or _execution_date(signal_date)),
            _human_source_status(rank),
        ])
    return values


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


def _next_withdrawal_dates(as_of: str, *, count: int = 2) -> list[str]:
    """Return future second-Wednesday dates without claiming market execution."""
    cursor = pd.Timestamp(as_of).date()
    start = pd.Timestamp(C6_WITHDRAWAL_START_DATE).date()
    dates: list[str] = []
    year, month = max((cursor.year, cursor.month), (start.year, start.month))
    while len(dates) < count:
        due = second_wednesday(year, month)
        if due >= start and due > cursor:
            dates.append(due.isoformat())
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return dates


def build_dashboard_values(
    *, model_version: str, snapshot_as_of: str, data_status: str, slots: list[dict], cash: float = 0.0,
    notes: str = "", historical_benchmark: dict | None = None, snapshot_rows: list[dict] | None = None,
    ranking_snapshot_as_of: str | None = None, accounting_snapshot_as_of: str | None = None,
) -> list[list[object]]:
    replay_not_materialized = (
        "no_whole_share_replay" in data_status
        or "replay_not_materialized" in data_status
        or "whole_share_replay_pit_blocked" in data_status
    )
    withdrawal = select_withdrawal_slot(slots, cash=cash)
    next_dates = _next_withdrawal_dates(snapshot_as_of)
    benchmark = historical_benchmark or {}
    benchmark_rows = [
        ["", ""],
        ["64條歷史路徑比較基準", "不納入 forward 模擬帳戶損益"],
        ["歷史範圍", benchmark.get("coverage", "2023不同起點至2026-08-12")],
        ["歷史初始資金／提領", benchmark.get("capital_and_withdrawal", "TWD7,000,000／每月底TWD75,000")],
        ["64條期末資產統計中位數", benchmark.get("statistical_median_final_nav", "")],
        ["64條帳戶NAV MDD中位數", benchmark.get("statistical_median_account_nav_mdd", "")],
        ["64條TWR CAGR中位數", benchmark.get("statistical_median_twr_cagr", "")],
        ["64條TWR MDD中位數", benchmark.get("statistical_median_twr_mdd", "")],
        ["下中位實際路徑", benchmark.get("lower_median_actual_route_id", "")],
        ["下中位實際路徑期末資產", benchmark.get("lower_median_actual_final_nav", "")],
        ["下中位帳戶NAV MDD", benchmark.get("lower_median_account_nav_mdd", "")],
        ["下中位TWR CAGR／MDD", benchmark.get("lower_median_twr_cagr_and_mdd", "")],
        ["歷史來源版本", benchmark.get("source_version", "")],
        ["日期歧義", benchmark.get("payment_date_note", "")],
    ]
    if replay_not_materialized:
        withdrawal_rows = [
            ["提領候選槽", "無法估算｜尚無權威整股帳本"],
            ["提領候選股票", ""],
            ["預計賣出股數", ""],
            ["預估成交金額", ""],
            ["預估費稅", ""],
            ["預估提領淨額", ""],
            ["現金提領額", ""],
            ["候選槽相對成本報酬", ""],
        ]
    else:
        withdrawal_rows = [
            ["提領候選槽", withdrawal["slot_id"] or "空手／現金"],
            ["提領候選股票", withdrawal.get("ticker", "")],
            ["預計賣出股數", withdrawal["planned_shares"]],
            ["預估成交金額", withdrawal["gross_amount"]],
            ["預估費稅", withdrawal["transaction_cost"]],
            ["預估提領淨額", withdrawal["net_amount"]],
            ["現金提領額", withdrawal.get("cash_withdrawal_amount", 0.0)],
            ["候選槽相對成本報酬", withdrawal["relative_return_pct"]],
        ]
    current_rows = build_public_snapshot_values(snapshot_rows or [])[1:]
    current_rows = [row for row in current_rows if row[1] in {1, 2, 3}]
    latest_date = max((str(row[0]) for row in current_rows), default=snapshot_as_of)
    latest_rows = [row for row in current_rows if str(row[0]) == latest_date]
    latest_by_rank = {int(row[1]): row for row in latest_rows}
    top_rows = [["今日Top1～Top3", "C6分數／排名說明"]]
    for rank in (1, 2, 3):
        row = latest_by_rank.get(rank)
        if row:
            score = f"{row[5]}分" if row[5] != "" else "分數資料待補"
            top_rows.append([f"Top{rank}｜{row[2]} {row[3]}", f"{score}｜通過C6條件，當日排名第{rank}"])
        else:
            top_rows.append([f"Top{rank}", "資料待補"])
    account_status = (
        "三槽整股模擬帳戶仍在完整重算，暫不顯示持股與損益"
        if replay_not_materialized else "三槽模擬帳戶已更新"
    )
    concise_note = (
        f"目前候選排名更新至{latest_date}；缺漏日期與三槽帳本正在補齊。"
        if replay_not_materialized else f"候選排名與三槽帳戶已更新至{latest_date}。"
    )
    return [
        ["C6研究版｜每日候選與三槽模擬帳戶", ""],
        ["排名資料截至", ranking_snapshot_as_of or latest_date],
        ["整股帳本截至", accounting_snapshot_as_of or snapshot_as_of],
        ["目前進度", _human_data_status(data_status)],
        ["Forward起始／初始資金／槽數", f"{C6_FORWARD_START_DATE}／TWD{C6_INITIAL_CAPITAL:,.0f}／{C6_SLOT_COUNT}"],
        ["模擬帳戶狀態", account_status],
        ["", ""],
        *top_rows,
        ["", ""],
        ["Forward提領規則", "第二個星期三；每次目標市值TWD75,000，最低相對成本報酬槽優先，整股交易"],
        ["下次提領排定日", next_dates[0]],
        ["下下次提領排定日", next_dates[1]],
        ["休市處理", "排定日無官方可交易收盤價時順延下一交易日；不假成交"],
        *withdrawal_rows,
        ["資料說明", concise_note],
        *benchmark_rows,
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
    historical_benchmark: dict | None = None,
    ranking_snapshot_as_of: str | None = None,
    accounting_snapshot_as_of: str | None = None,
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
    ledger_existing = client.get(f"'{LEDGER_SHEET}'!A1:P50000")
    version_existing = client.get(f"'{VERSION_SHEET}'!A1:G50000")
    public_snapshot_values = build_public_snapshot_values(snapshot_rows)
    ledger_known = {str(row[15]) for row in ledger_existing[1:] if len(row) > 15 and row[15]}
    ledger_additions = []
    for row in ledger_rows:
        event_key = str(row.get("immutable_event_key") or "")
        if event_key in ledger_known:
            continue
        display = dict(row)
        display["model_version"] = _human_model_version(str(row.get("model_version") or ""))
        display["event_type"] = _human_event(str(row.get("event_type") or ""))
        ledger_additions.append([display.get(field, "") for field in LEDGER_FIELDS])
        ledger_known.add(event_key)
    version_row = {
        "model_version": model_version, "snapshot_as_of": snapshot_as_of, "data_status": data_status,
        "source_manifest_hash": source_manifest_hash, "published_as_current": True, "created_at": snapshot_as_of,
        "notes": notes,
    }
    known_hashes = {str(row[3]) for row in version_existing[1:] if len(row) > 3 and row[3]}
    version_additions = []
    if source_manifest_hash not in known_hashes:
        display_version = dict(version_row)
        display_version["model_version"] = _human_model_version(model_version)
        display_version["data_status"] = _human_version_status(data_status)
        display_version["published_as_current"] = "是"
        version_additions.append([display_version.get(field, "") for field in VERSION_FIELDS])
    client.clear(f"'{SNAPSHOT_SHEET}'!A1:Z50000")
    client.update(f"'{SNAPSHOT_SHEET}'!A1", public_snapshot_values)
    if not ledger_existing:
        client.update(f"'{LEDGER_SHEET}'!A1", [LEDGER_HEADERS, *ledger_additions])
    elif ledger_additions:
        client.update(f"'{LEDGER_SHEET}'!A{len(ledger_existing) + 1}", ledger_additions)
    if not version_existing:
        client.update(f"'{VERSION_SHEET}'!A1", [VERSION_HEADERS, *version_additions])
    elif version_additions:
        client.update(f"'{VERSION_SHEET}'!A{len(version_existing) + 1}", version_additions)
    pointer = [[
        _human_model_version(model_version),
        accounting_snapshot_as_of or snapshot_as_of,
        f"排名已更新至{ranking_snapshot_as_of or snapshot_as_of}；持股與損益只核對至{accounting_snapshot_as_of or snapshot_as_of}",
        ranking_snapshot_as_of or snapshot_as_of,
    ]]
    client.clear(f"'{CURRENT_POINTER_SHEET}'!A1:D2")
    client.update(f"'{CURRENT_POINTER_SHEET}'!A1", [CURRENT_POINTER_HEADERS, *pointer])
    dashboard = build_dashboard_values(
        model_version=model_version, snapshot_as_of=snapshot_as_of, data_status=data_status, slots=slots, cash=cash,
        notes=notes, historical_benchmark=historical_benchmark, snapshot_rows=snapshot_rows,
        ranking_snapshot_as_of=ranking_snapshot_as_of, accounting_snapshot_as_of=accounting_snapshot_as_of,
    )
    client.clear(f"'{DASHBOARD_SHEET}'!A1:B60")
    client.update(f"'{DASHBOARD_SHEET}'!A1", dashboard)
    return {
        "model_version": model_version,
        "snapshot_as_of": snapshot_as_of,
        "data_status": data_status,
        "snapshot_rows_published": len(public_snapshot_values) - 1,
        "ledger_rows_appended": len(ledger_additions),
        "version_rows_appended": len(version_additions),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an immutable C6 research snapshot to its Google Sheet.")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    # Coverage remains immutable payload metadata; it is not a Sheets write argument.
    payload.pop("coverage", None)
    if "historical_benchmark" not in payload and DEFAULT_HISTORICAL_BENCHMARK_PATH.exists():
        payload["historical_benchmark"] = json.loads(DEFAULT_HISTORICAL_BENCHMARK_PATH.read_text(encoding="utf-8"))
    contract_fields = {
        "model_version", "snapshot_as_of", "data_status", "source_manifest_hash", "snapshot_rows",
        "ledger_rows", "slots", "cash", "notes", "historical_benchmark", "ranking_snapshot_as_of",
        "accounting_snapshot_as_of",
    }
    result = publish_snapshot(args.spreadsheet_id, **{key: value for key, value in payload.items() if key in contract_fields})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
