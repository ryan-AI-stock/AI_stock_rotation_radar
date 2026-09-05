from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import requests

from .v4d_simulation_account import withdrawal_preview
from .sheets_retry import request as retry_request


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
MODEL_LOGIC = """全市場硬篩選＋低基期止跌轉強Top1（64條起始路徑中位代表路徑）

【候選與排序】
成交金額使用最新20日平均Top250，且過去20TD至少18天不差於Top280；通過PIT基本面／財務重大風險、60日自身報酬>0%、回檔前20TD自身強度>0%、止跌轉強證據至少2／3、Pos20／40／61完整、BIAS60自身歷史完整及波動度非前2.5%。依Pos61級距→止跌證據→回檔前20TD強度→BIAS60自身風險→Pos61精確值→多週期基期→60日自身報酬→流動性→代號排序。排除食品工業／紡織纖維／汽車工業／電器電纜／橡膠工業；原Top1被排除時依序遞補至Top3。最終標的若仍為處置股則空手，不再遞補。

【買進】
收盤後產生訊號，下一交易日依正式日線成交口徑買入；一次只持有一檔，700萬元策略資金100%投入。持股期間不因每日Top1改變而換股；賣出後CD=0。同一換倉日不得賣出後立即買回同一檔。

【賣出：收盤確認，下一交易日執行】
1. TD1～TD5：股價相對買入價下跌達-5%，退出。
2. 任意連續5TD：股價下跌達-10%，退出。
3. TD6起：累積after-cost報酬達-10%，退出。
4. 最高after-cost曾達+7%但未達+10%，其後當下回落至+1%或以下，退出。
5. TD14：當下after-cost未達+5%，且持有期間最高未達+10%，退出。
6. 最高after-cost曾達+10%後視為正式發動，改由持有高點回落10%管理。
7. TD22：持有期間從未達+10%，且當下after-cost未達+8%，退出。
8. TD55起：當下after-cost未達+20%，退出。
9. 每年首個交易日依歷史執行外殼強制刷新Top1。

【成本與資金】
買進成本：手續費0.0855%＋滑價0.10%；賣出成本：手續費0.0855%＋證交稅0.30%＋滑價0.10%。所有資產、損益及標示為after-cost的門檻均完整扣除成本；只有TD1～TD5的-5%快速失敗門檻直接比較股票價格。初始資金700萬元，100%策略股，無0050正二／00631L核心；每月底賣出約75,000元現值持股，扣除交易成本後提領。

【本列期間與代表性】
訊號起點2015-06-22、首次買入2015-06-23，結束2026-08-12。第5列與三個V4-D明細分頁均使用64條按期末資產排序後的下中位實際路徑（2015-06-23首次買入）；64條為偶數，統計中位數是兩條中央路徑的平均，本身不是一條真實交易路徑。不是舊年度重置路徑，也不是64條績效的逐年平均。"""


def model_logic_format_requests(sheet_id: int) -> list[dict]:
    """Return the idempotent A32:B32 merge and readable long-text formatting."""
    logic_range = {
        "sheetId": sheet_id,
        "startRowIndex": 31,
        "endRowIndex": 32,
        "startColumnIndex": 0,
        "endColumnIndex": 2,
    }
    return [
        {"unmergeCells": {"range": logic_range}},
        {"mergeCells": {"range": logic_range, "mergeType": "MERGE_ALL"}},
        {
            "repeatCell": {
                "range": logic_range,
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "TOP",
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,horizontalAlignment,verticalAlignment)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 31,
                    "endIndex": 32,
                },
                "properties": {"pixelSize": 760},
                "fields": "pixelSize",
            }
        },
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
        action = str(tx.get("action", ""))
        event_type = "每月提領" if action.startswith("monthly_withdrawal") else "成交"
        action_label = {
            "buy": "買進",
            "sell": "賣出",
            "monthly_withdrawal_stock_sale": "提領賣股",
            "monthly_withdrawal_cash": "現金提領",
            "monthly_withdrawal_unfunded_cash": "提領未完成",
        }.get(action, action)
        rows.append([
            tx.get("trade_date", ""), event_type, str(tx.get("ticker", "")).zfill(4), tx.get("name", ""),
            action_label, tx.get("execution_price"), tx.get("shares"),
            tx.get("gross_amount"), tx.get("transaction_cost"), tx.get("cash_after"), tx.get("realized_pnl"),
            None if tx.get("realized_return_pct") is None else tx.get("realized_return_pct") / 100,
            tx.get("signal_date", ""), None, None, None, None, None, None,
            f"{tx.get('reason', '')}｜排定日={tx.get('scheduled_withdrawal_date', '')}".rstrip("｜排定日="),
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
    as_of = sorted(marks)[-1] if marks else final_row[0] if signal_rows else "2026-01-01"
    withdrawal = withdrawal_preview(simulation, as_of_date=as_of, close=latest_close)
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
        ["下次提領排定日", withdrawal["next_scheduled_date"]],
        ["提領執行狀態", withdrawal["status"]],
        ["預計賣出股數", withdrawal["planned_shares"]],
        ["預估賣出金額", withdrawal["estimated_gross_amount"]],
        ["預估費稅", withdrawal["estimated_fee_tax"]],
        ["預估提領淨額", withdrawal["estimated_net_withdrawal"]],
        ["", ""], ["今日Top1～Top3", "產業／狀態"],
    ]
    for row in signal_rows:
        values.append([f"Top{row[1]}｜{row[2]} {row[3]}", f"{row[4]}｜{row[7] or '觀察'}"])
    values.extend([
        ["", ""], ["64條路徑中位數比較基準", "不納入模擬帳戶損益"],
        ["期末資產中位數", 1_230_902_878.8443353], ["總報酬中位數", 174.8432684063336],
        ["CAGR中位數", 0.5907543145186337], ["MDD中位數", -0.47398678813667246],
    ])
    while len(values) < 31:
        values.append(["", ""])
    values.append([MODEL_LOGIC, ""])
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
            # Keep the scope identical to the repository's existing OAuth token.
            # Google Sheets accepts the full Drive scope for spreadsheet access.
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        credentials.refresh(Request())
        self.headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"

    def get(self, a1_range: str) -> list[list[object]]:
        response = retry_request(requests.get, f"{self.base}/values/{a1_range}", headers=self.headers, timeout=30)
        self._raise_for_status(response)
        return response.json().get("values", [])

    def clear(self, a1_range: str) -> None:
        response = retry_request(requests.post, f"{self.base}/values/{a1_range}:clear", headers=self.headers, json={}, timeout=30)
        self._raise_for_status(response)

    def update(self, a1_range: str, values: list[list[object]]) -> None:
        response = retry_request(requests.put,
            f"{self.base}/values/{a1_range}", params={"valueInputOption": "USER_ENTERED"},
            headers=self.headers, json={"range": a1_range, "majorDimension": "ROWS", "values": values}, timeout=30,
        )
        self._raise_for_status(response)

    def format_model_logic(self, sheet_title: str) -> None:
        response = retry_request(requests.get,
            self.base,
            params={"fields": "sheets(properties(sheetId,title))"},
            headers=self.headers,
            timeout=30,
        )
        self._raise_for_status(response)
        sheet_id = next(
            int(sheet["properties"]["sheetId"])
            for sheet in response.json().get("sheets", [])
            if sheet.get("properties", {}).get("title") == sheet_title
        )
        response = retry_request(requests.post,
            f"{self.base}:batchUpdate",
            headers=self.headers,
            json={"requests": model_logic_format_requests(sheet_id)},
            timeout=30,
        )
        self._raise_for_status(response)

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if response.ok:
            return
        raise requests.HTTPError(
            f"Google Sheets API {response.status_code}: {response.text}",
            response=response,
        )


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
    client.clear(f"'{DASHBOARD_SHEET}'!A1:B50")
    client.update(f"'{DASHBOARD_SHEET}'!A1", dashboard)
    client.format_model_logic(DASHBOARD_SHEET)
    source = f"'{SIGNAL_SHEET}'"
    client.update(f"'{DASHBOARD_SHEET}'!B2", [[f'=MAX({source}!A2:A)']])
    for rank in range(1, 4):
        condition = f'{source}!A2:A=$B$2,{source}!B2:B={rank}'
        formula = f'=IFNA("Top{rank}｜"&INDEX(FILTER({source}!C2:C&" "&{source}!D2:D,{condition}),1),"無其他合格股票")'
        client.update(f"'{DASHBOARD_SHEET}'!A{rank+22}", [[formula]])
    expected_date = str(new_rows[0][0])
    if client.get(f"'{DASHBOARD_SHEET}'!B2") != [[expected_date]]:
        raise RuntimeError('V4-D Dashboard signal date read-back mismatch')
    for rank, row in enumerate(new_rows, 1):
        if client.get(f"'{DASHBOARD_SHEET}'!A{rank+22}") != [[f'Top{rank}｜{row[2]} {row[3]}']]:
            raise RuntimeError('V4-D Dashboard ranking read-back mismatch')
    if client.get(f"'{DASHBOARD_SHEET}'!B6") != [[dashboard[5][1]]]:
        raise RuntimeError('V4-D Dashboard holding read-back mismatch')


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
