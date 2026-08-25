from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import requests


SIGNAL_SHEET = "V4-D每日訊號資料庫"
TRADE_SHEET = "V4-D模擬交易紀錄"
DASHBOARD_SHEET = "V4-D Dashboard"
EXCLUDED_INDUSTRIES = {"食品工業", "紡織纖維", "汽車工業", "電器電纜", "橡膠工業"}
SIGNAL_HEADERS = [
    "訊號日期", "原始順位", "股票代號", "股票名稱", "產業", "收盤價", "最終可交易Top1",
    "排除／遞補原因", "預定執行日", "成交金額20日排名", "流動性完整率", "近20日至少Top280天數",
    "60日自身報酬", "回檔前20TD強度", "Pos20", "Pos40", "Pos61", "Pos61級距", "止跌證據",
    "BIAS60歷史位階", "BIAS60風險層級", "波動度百分位", "資料完整狀態", "模型狀態",
]
TRADE_HEADERS = [
    "日期", "事件類型", "股票代號", "股票名稱", "動作", "成交／收盤價", "股數", "交易金額",
    "交易成本", "現金餘額", "已實現損益", "已實現報酬", "訊號日期", "持有TD", "當日漲跌",
    "累積報酬", "after-cost報酬", "最高after-cost報酬", "高點回落", "原因／狀態",
]


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def build_signal_rows(ranking: pd.DataFrame, state: dict) -> list[list[object]]:
    frame = ranking.copy()
    frame["candidate_rank"] = pd.to_numeric(frame["candidate_rank"], errors="coerce")
    frame = frame.sort_values("candidate_rank").head(3)
    final_ticker = str(state.get("ticker", "")).zfill(4)
    execution_date = state.get("execution_date", "")
    rows: list[list[object]] = []
    for row in frame.itertuples(index=False):
        ticker = str(row.ticker).zfill(4)
        industry = str(getattr(row, "industry_name", "") or "")
        is_final = ticker == final_ticker
        reason = ""
        if industry in EXCLUDED_INDUSTRIES:
            reason = f"排除產業：{industry}"
        elif not is_final and int(row.candidate_rank) < int(state.get("candidate_rank", 1)):
            reason = "原順位不可交易，依正式外殼遞補"
        elif is_final:
            reason = "最終可交易Top1"
        complete = all(
            pd.notna(getattr(row, key, None))
            for key in ("return_60d", "pre_pullback_20d_strength", "pos20", "pos40", "pos61")
        )
        rows.append([
            str(row.signal_date), int(row.candidate_rank), ticker, row.name, industry,
            float(getattr(row, "signal_close", state.get("signal_close", 0)) or state.get("signal_close", 0)),
            is_final, reason, execution_date if is_final else "",
            float(row.turnover_rank_20d), float(row.turnover_data_completeness),
            int(row.rank_le280_days_in_prior20), float(row.return_60d), float(row.pre_pullback_20d_strength),
            float(row.pos20), float(row.pos40), float(row.pos61), int(row.pos61_bucket), int(row.turnup_evidence),
            float(row.bias60_history_percentile), int(row.bias60_risk_tier), float(row.volatility_percentile),
            "完整" if complete and _bool(row.top30_minimum_pass) else "不完整", state.get("status", "signal_only") if is_final else "觀察",
        ])
    return rows


def build_trade_rows(simulation: dict) -> list[list[object]]:
    rows: list[list[object]] = []
    for tx in simulation.get("transactions", []):
        rows.append([
            tx.get("trade_date", ""), "成交", str(tx.get("ticker", "")).zfill(4), tx.get("name", ""),
            "買進" if tx.get("action") == "buy" else "賣出", tx.get("execution_price"), tx.get("shares"),
            tx.get("gross_amount"), tx.get("transaction_cost"), tx.get("cash_after"), tx.get("realized_pnl"),
            None if tx.get("realized_return_pct") is None else tx.get("realized_return_pct") / 100,
            tx.get("signal_date", ""), None, None, None, None, None, None, tx.get("reason", ""),
        ])
    position = simulation.get("position") or {}
    for mark_date, mark in sorted((position.get("daily_marks") or {}).items()):
        rows.append([
            mark_date, "每日持有", str(position.get("ticker", "")).zfill(4), position.get("name", ""), "續抱",
            mark.get("close"), position.get("shares"), None, None, simulation.get("cash"), None, None,
            position.get("signal_date", ""), mark.get("model_td"),
            None if mark.get("daily_return_pct") is None else mark.get("daily_return_pct") / 100,
            None if mark.get("cumulative_return_pct") is None else mark.get("cumulative_return_pct") / 100,
            None if mark.get("after_cost_return_pct") is None else mark.get("after_cost_return_pct") / 100,
            None if mark.get("peak_after_cost_return_pct") is None else mark.get("peak_after_cost_return_pct") / 100,
            None if mark.get("trailing_drawdown_pct") is None else mark.get("trailing_drawdown_pct") / 100,
            "持有中",
        ])
    return sorted(rows, key=lambda row: (str(row[0]), 0 if row[1] == "成交" else 1))


def build_dashboard_values(signal_rows: list[list[object]], simulation: dict) -> list[list[object]]:
    position = simulation.get("position") or {}
    marks = position.get("daily_marks") or {}
    latest_mark = marks[sorted(marks)[-1]] if marks else {}
    latest_close = latest_mark.get("close")
    shares = int(position.get("shares") or 0)
    cash = float(simulation.get("cash") or 0)
    market_value = float(latest_close or 0) * shares
    nav = cash + market_value
    latest = signal_rows[0] if signal_rows else [""] * len(SIGNAL_HEADERS)
    final_row = next((row for row in signal_rows if row[6]), latest)
    values = [
        ["最新版個股模型V4-D｜每日訊號與模擬追蹤", ""],
        ["最新訊號日", final_row[0]], ["最終可交易Top1", f"{final_row[2]} {final_row[3]}"],
        ["預定執行日", final_row[8]],
        ["模型狀態", "持有中" if position else "空手"], ["目前模擬持股", f"{position.get('ticker', '')} {position.get('name', '')}" if position else "空手"],
        ["持有TD", latest_mark.get("model_td")], ["最新收盤", latest_close],
        ["after-cost報酬", None if latest_mark.get("after_cost_return_pct") is None else latest_mark.get("after_cost_return_pct") / 100],
        ["最高after-cost報酬", None if latest_mark.get("peak_after_cost_return_pct") is None else latest_mark.get("peak_after_cost_return_pct") / 100],
        ["高點回落", None if latest_mark.get("trailing_drawdown_pct") is None else latest_mark.get("trailing_drawdown_pct") / 100],
        ["持股市值", market_value], ["現金", cash], ["模擬總資產", nav],
        ["", ""], ["今日Top1～Top3", "產業／狀態"],
    ]
    for row in signal_rows:
        values.append([f"Top{row[1]}｜{row[2]} {row[3]}", f"{row[4]}｜{row[7] or '觀察'}"])
    values.extend([
        ["", ""], ["64條路徑中位數比較基準", "不納入模擬帳戶損益"],
        ["期末資產中位數", 1_230_902_878.8443353], ["總報酬中位數", 174.8432684063336],
        ["CAGR中位數", 0.5907543145186337], ["MDD中位數", -0.47398678813667246],
    ])
    return values


class SheetsClient:
    def __init__(self, spreadsheet_id: str) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        self.spreadsheet_id = spreadsheet_id
        credentials = Credentials(
            token=None,
            refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
        )
        credentials.refresh(Request())
        self.headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"

    def get(self, a1_range: str) -> list[list[object]]:
        response = requests.get(f"{self.base}/values/{a1_range}", headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json().get("values", [])

    def clear(self, a1_range: str) -> None:
        response = requests.post(f"{self.base}/values/{a1_range}:clear", headers=self.headers, json={}, timeout=30)
        response.raise_for_status()

    def update(self, a1_range: str, values: list[list[object]]) -> None:
        response = requests.put(
            f"{self.base}/values/{a1_range}", params={"valueInputOption": "USER_ENTERED"},
            headers=self.headers, json={"range": a1_range, "majorDimension": "ROWS", "values": values}, timeout=30,
        )
        response.raise_for_status()


def publish(spreadsheet_id: str, ranking_path: Path, state_path: Path, simulation_path: Path) -> None:
    ranking = pd.read_csv(ranking_path, dtype={"ticker": str})
    state = json.loads(state_path.read_text(encoding="utf-8"))
    simulation = json.loads(simulation_path.read_text(encoding="utf-8"))
    new_rows = build_signal_rows(ranking, state)
    client = SheetsClient(spreadsheet_id)

    existing = client.get(f"'{SIGNAL_SHEET}'!A1:X5000")
    data = existing[1:] if existing and existing[0] == SIGNAL_HEADERS else []
    keyed = {(str(row[0]), int(row[1])): row for row in data if len(row) >= 2}
    for row in new_rows:
        keyed[(str(row[0]), int(row[1]))] = row
    merged = [keyed[key] for key in sorted(keyed, key=lambda item: (item[0], item[1]))]
    client.clear(f"'{SIGNAL_SHEET}'!A1:X5000")
    client.update(f"'{SIGNAL_SHEET}'!A1", [SIGNAL_HEADERS, *merged])

    trade_rows = build_trade_rows(simulation)
    client.clear(f"'{TRADE_SHEET}'!A1:T5000")
    client.update(f"'{TRADE_SHEET}'!A1", [TRADE_HEADERS, *trade_rows])

    dashboard = build_dashboard_values(new_rows, simulation)
    client.clear(f"'{DASHBOARD_SHEET}'!A1:B40")
    client.update(f"'{DASHBOARD_SHEET}'!A1", dashboard)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish V4-D daily signal and simulation dashboard to Google Sheets.")
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--ranking", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--simulation", required=True, type=Path)
    args = parser.parse_args()
    publish(args.spreadsheet_id, args.ranking, args.state, args.simulation)


if __name__ == "__main__":
    main()
