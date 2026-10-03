from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


MODEL_LOGIC = """R1研究版｜AI瓶頸／預期差動態輪動

【模型定位】
R1是獨立研究challenger，用來尋找AI剛性需求、基本面與財務面仍強，但市場預期尚未完全反映的股票。R1不取代正式V4-D，也不改C6每日交易決策。

【目前研究池】
目前追蹤14檔；台積電為CORE_LOCK核心部位，其餘股票屬可研究候選。畫面中的既有股數只用於參考市值，不代表R1已產生成交。

【五個評分構面】
EPS預估修正30%、前瞻估值25%、AI瓶頸程度20%、可驗證催化事件15%、價格與籌碼10%。每一項都必須使用當時可取得的PIT資料；缺資料不補0，也不推估成安全。

【輪動與風險限制】
研究設定每週換倉上限10%，主部位目標3檔，現金目標5%～20%。台積電核心部位不因短期訊號退出；其餘買進、減碼與退出門檻尚待完整資料累積與回測核准。

【目前狀態】
官方價格、價量籌碼歷史序列、EPS共識、五年估值定位、瓶頸與催化證據已接通；當日籌碼另行驗收，不能用歷史序列完整代替。EPS修正序列仍在累積。Action門檻核准前，只顯示資料與觀察狀態，不產生Top1～Top3、模擬成交或實際操作指令。"""


def _latest_valuation_rows(root: str | Path, target_date: str) -> dict[str, dict]:
    files = sorted(path for path in Path(root).glob("????-??-??.json") if path.stem <= target_date)
    if not files:
        return {}
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return {row["ticker"]: row for row in payload.get("rows", [])}


def build_dashboard_payload(
    *, config_path: str | Path, market_path: str | Path,
    readiness_path: str | Path = "data/r1/evidence_readiness.json",
    valuation_root: str | Path = "data/r1/valuation_history",
) -> dict:
    config = R1Config.load(config_path)
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    readiness_file = Path(readiness_path)
    readiness = json.loads(readiness_file.read_text(encoding="utf-8")) if readiness_file.exists() else {
        "requested_ticker_count": len(config.securities), "consensus_ready_count": 0,
        "eps_revision_ready_count": 0,
        "catalyst_ready_count": 0, "bottleneck_ready_count": 0, "price_chip_ready_count": 0,
        "current_chip_ready_count": 0,
        "trade_ready_count": 0,
        "action_policy_approved": False, "rows": [],
    }
    readiness_by_ticker = {row["ticker"]: row for row in readiness.get("rows", [])}
    market_by_ticker = {row["ticker"]: row for row in market["rows"]}
    valuation_by_ticker = _latest_valuation_rows(valuation_root, market["date"])
    revision_progress = readiness.get("eps_revision_progress", {})
    revision_dates = revision_progress.get("earliest_calendar_eligibility", {})
    tabs: dict[str, list[list[object]]] = {
        title: ([] if title == "R1 Dashboard" else [list(headers)])
        for title, headers in TAB_SCHEMAS.items()
    }

    total_value = sum((market_by_ticker[s.ticker]["raw_close"] or 0) * s.shares for s in config.securities)
    held_count = sum(security.shares > 0 for security in config.securities)
    dashboard = tabs["R1 Dashboard"]
    dashboard.extend([
        ["R1研究版｜AI瓶頸預期差輪動"],
        ["最新資料日期", market["date"], "模型定位", "研究挑戰版", "尚未啟用交易"],
        ["資料狀態", "官方價格與五年估值定位已更新；當日籌碼獨立驗收，EPS修正序列仍在累積，不產生買賣指令。"],
        ["01｜今日候選排名"],
        ["順位", "股票", "R1分數", "代表意義", "狀態"],
        ["Top1", "尚未產生", "", "Action門檻尚未核准", "研究資料累積中"],
        ["Top2", "尚未產生", "", "Action門檻尚未核准", "研究資料累積中"],
        ["Top3", "尚未產生", "", "Action門檻尚未核准", "研究資料累積中"],
        ["排名不是交易指令", "R1核准前不會依排名自動買進、賣出或加碼。"],
        ["02｜目前追蹤持股（非R1成交）"],
        ["股票", "股數", "官方收盤", "參考市值", "狀態"],
    ])
    for security in config.securities:
        if security.shares <= 0:
            continue
        row = market_by_ticker[security.ticker]
        close = row["raw_close"]
        dashboard.append([
            f"{security.ticker} {security.company}", security.shares, close,
            None if close is None else close * security.shares,
            "核心持股" if security.core_lock else "既有持股／等待R1規則核准",
        ])
    dashboard.extend([
        ["03｜資料與模型狀態"],
        ["項目", "完成度", "顯示狀態", "用途", "資料日期"],
        ["官方市場資料", f"{market['actual_ticker_count']}/{market['requested_ticker_count']}",
         "完整" if not market["gaps"] else "資料不足", "收盤與技術資料", market["date"]],
        ["EPS共識", f"{readiness['consensus_ready_count']}/{readiness['requested_ticker_count']}",
         "完整" if readiness["consensus_ready_count"] == readiness["requested_ticker_count"] else "部分完成",
         "EPS修正與前瞻估值", market["date"]],
        ["EPS修正歷史", f"{readiness.get('eps_revision_ready_count', 0)}/{readiness['requested_ticker_count']}",
         "完整" if readiness.get("eps_revision_ready_count") == readiness["requested_ticker_count"] else "累積中",
         "至少具備1W、4W及12W PIT基準；最早日："
         f"1W {revision_dates.get('1w') or '待首筆'}／4W {revision_dates.get('4w') or '待首筆'}／"
         f"12W {revision_dates.get('12w') or '待首筆'}", market["date"]],
        ["催化證據", f"{readiness['catalyst_ready_count']}/{readiness['requested_ticker_count']}",
         "完整" if readiness["catalyst_ready_count"] == readiness["requested_ticker_count"] else "部分完成",
         "需求與事件驗證", market["date"]],
        ["瓶頸證據", f"{readiness['bottleneck_ready_count']}/{readiness['requested_ticker_count']}",
         "完整" if readiness["bottleneck_ready_count"] == readiness["requested_ticker_count"] else "部分完成",
         "AI剛性需求驗證", market["date"]],
        ["20日價量籌碼序列", f"{readiness.get('price_chip_ready_count', 0)}/{readiness['requested_ticker_count']}",
         "完整" if readiness.get("price_chip_ready_count") == readiness["requested_ticker_count"] else "部分完成",
         "歷史價格與籌碼構面", market["date"]],
        ["當日法人與融資", f"{readiness.get('current_chip_ready_count', 0)}/{readiness['requested_ticker_count']}",
         "完整" if readiness.get("current_chip_ready_count") == readiness["requested_ticker_count"] else "等待官方資料",
         "當期訊號驗收；不可由舊資料代替", market["date"]],
        ["五年估值定位", f"{sum(bool(row.get('valuation_ready')) for row in readiness.get('rows', []))}/{readiness['requested_ticker_count']}",
         "完整" if all(row.get("valuation_ready") for row in readiness.get("rows", [])) else "部分完成",
         "下年度Forward PE自身五年百分位", market["date"]],
        ["交易建議", f"{readiness['trade_ready_count']}/{readiness['requested_ticker_count']}",
         "尚未啟用", "Action規則核准後才產生", market["date"]],
        ["04｜模型完整說明"],
        [MODEL_LOGIC],
    ])

    for security in config.securities:
        row = market_by_ticker[security.ticker]
        readiness_row = readiness_by_ticker.get(security.ticker, {})
        valuation_row = valuation_by_ticker.get(security.ticker, {})
        if security.core_lock:
            action, reason = "CORE", "CORE_LOCK"
        elif readiness_row.get("trade_ready"):
            action, reason = "WATCH", "ACTION_ENGINE_NOT_MATERIALIZED"
        else:
            action = "DATA_MISSING"
            reason = ";".join(readiness_row.get("blocked_reasons", ["READINESS_NOT_MATERIALIZED"]))
        tabs["R1每日訊號資料庫"].append([
            market["date"], security.ticker, security.company, row["raw_close"], row["daily_return"],
            row["return_1w"], row["return_1m"], row["return_3m"], row["return_6m"], row["ma20"],
            row["ma60"], row["bias20"], row["bias60"], row["turnover_value"], row["avg_turnover_20d"],
            valuation_row.get("forward_eps_mean"), valuation_row.get("forward_pe"),
            bool(readiness_row.get("consensus_ready")), bool(readiness_row.get("catalyst_ready")),
            bool(readiness_row.get("bottleneck_ready")), bool(readiness_row.get("valuation_ready")),
            bool(readiness_row.get("price_chip_ready")), None, action, reason,
        ])

    # No transaction row is emitted until the action policy and execution ledger are both approved.
    validate_tabs(tabs)
    return {
        "model": "R1", "date": market["date"], "tabs": tabs,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the three-tab R1 dashboard payload.")
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--readiness", default="data/r1/evidence_readiness.json")
    parser.add_argument("--valuation-root", default="data/r1/valuation_history")
    parser.add_argument("--output", default="data/r1/dashboard_payload.json")
    args = parser.parse_args()
    payload = build_dashboard_payload(
        config_path=args.config, market_path=args.market, readiness_path=args.readiness,
        valuation_root=args.valuation_root,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
