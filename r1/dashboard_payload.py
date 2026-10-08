from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs
from r1.toalpha_revision_history import latest_rows as latest_supplemental_revision_rows
from r1.theme_policy import load_themes


MODEL_LOGIC = """R1 v0.3研究版｜AI瓶頸題材持有優先序

【模型任務】
R1負責維護11個AI發展瓶頸題材、每個題材的結構性Top1～Top3，以及各股票0～100分的優先持有參考值。Dashboard只顯示Ryan實際持股與未來半年五檔目標持股；完整題材池與Top3仍在模型資料中維護。R1不產生買進、賣出、加碼或減碼指令，實際操作由Ryan自行決定。

【季度Top3】
結構性龍頭評分：AI瓶頸直接性25%、產業與技術地位25%、AI營收兌現20%、財務與獲利品質20%、市場代表性10%。官方與公司正式揭露優先；分析師與市場共識只能補充，不能單獨決定排名。任一成分股必要證據不足時，該題材Top3維持待資料。

【每日優先持有參考值】
結構性龍頭30%、營收與獲利成長25%、估值相對自身歷史20%、股價風險安全度15%、需求訂單與催化10%。分數越高代表當下相對持有吸引力越高，不代表預測上漲機率。

【更新頻率】
每個交易日累積官方價格與市場資料；每週更新需求、事件與風險；每季財報揭露後重評Top3；每半年檢討題材與成分股。缺資料不補0、不重配權重、不以媒體稱號代替證據。

【模型邊界】
R1是研究challenger，不取代正式V4-D，也不改C6每日交易決策。舊買賣與換倉程式暫時保留，但不顯示於Dashboard，也不啟用交易。"""


def _build_v03_dashboard(*, config: R1Config, market: dict, theme_review: dict,
                         theme_path: str | Path, transition: dict | None = None) -> list[list[object]]:
    themes = load_themes(theme_path)
    membership_count = sum(len(theme.members) for theme in themes)
    universe_count = len({member.ticker for theme in themes for member in theme.members})
    reviews = {row.get("theme_id"): row for row in theme_review.get("themes", [])}
    held = {security.ticker: security for security in config.securities if security.shares > 0}
    membership: dict[str, list[str]] = {}
    for theme in themes:
        for member in theme.members:
            membership.setdefault(member.ticker, []).append(theme.name)
    theme_payload = json.loads(Path(theme_path).read_text(encoding="utf-8"))
    targets = [str(ticker).zfill(4) for ticker in theme_payload.get("target_portfolio_6m", [])]
    if len(targets) != 5 or len(set(targets)) != 5:
        raise ValueError("R1 six-month target portfolio must contain five unique tickers")
    securities = {security.ticker: security for security in config.securities}
    if any(ticker not in securities for ticker in targets):
        raise ValueError("R1 target portfolio contains ticker outside configured universe")
    priority_by_ticker: dict[str, object] = {}
    for review in reviews.values():
        for item in review.get("top3", []):
            ticker = str(item.get("ticker", "")).zfill(4)
            priority_by_ticker[ticker] = item.get("priority_score")
    display_tickers = targets + [
        ticker for ticker in held if ticker not in set(targets)
    ]
    rows: list[list[object]] = [
        ["R1研究版｜AI瓶頸預期差輪動"],
        ["最新資料日期", market["date"], "模型定位", "實際持股與半年目標持股", "非交易指令"],
        ["資料狀態", f"{len(themes)}題材、{universe_count}檔股票、{membership_count}筆題材歸屬（跨題材可重複）；Dashboard只顯示實際持股與五檔目標。"],
        ["01｜實際持股與未來半年目標持股"],
        ["所屬題材", "股票", "優先持有參考值", "實際持有", "半年目標"],
    ]
    for ticker in display_tickers:
        security = securities[ticker]
        rows.append([
            "；".join(membership.get(ticker, ["尚未納入11題材池"])),
            f"{ticker} {security.company}",
            priority_by_ticker.get(ticker) if priority_by_ticker.get(ticker) is not None else "待資料",
            f"實際持有｜{security.shares}股" if ticker in held else "",
            "未來半年目標" if ticker in targets else "既有實際持股",
        ])
    transition = transition or {}
    transition_status = transition.get("status", "尚未建立")
    rows.extend([
        ["02｜無差別殺盤過渡層（研究觀察）"],
        ["狀態", transition_status, "候選池下跌比例", transition.get("negative_share", "待資料"),
         f"報酬中位數：{transition.get('universe_median_return', '待資料')}"],
        ["執行邊界", "盤中只觀察；收盤後重算；不自動交易，長期五檔目標不變。"],
        ["03｜分數規則"],
        ["分數", "構成", "權重", "更新頻率", "用途"],
        ["季度結構性龍頭", "瓶頸直接性／產業技術地位／AI營收兌現／財務獲利品質／市場代表性",
         "25%／25%／20%／20%／10%", "每季", "決定每個題材Top1～Top3"],
        ["優先持有參考值", "結構性龍頭／營收獲利成長／自身歷史估值／價格風險安全度／需求訂單催化",
         "30%／25%／20%／15%／10%", "每日資料＋週月季事件", "提供Ryan自行比較持有優先序"],
        ["04｜更新排程"],
        ["頻率", "工作", "產出", "失敗處理", "交易影響"],
        ["每日收盤後", f"累積{universe_count}檔官方價格與市場資料", "每日資料庫", "缺資料重抓並列明缺口", "無"],
        ["每週最後交易日", "更新需求、訂單、事件與風險", "週度證據狀態", "證據不足維持原值或待資料", "無"],
        ["每季財報揭露後", f"重評{len(themes)}題材Top3", "季度排名", "全題材成分證據完整才發布", "無"],
        ["每半年", "檢討題材與成分股", "增刪建議與證據", "保留歷史版本", "無"],
        ["05｜模型完整說明"],
        [MODEL_LOGIC],
    ])
    return rows


def _latest_valuation_rows(root: str | Path, target_date: str) -> dict[str, dict]:
    files = sorted(path for path in Path(root).glob("????-??-??.json") if path.stem <= target_date)
    if not files:
        return {}
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return {row["ticker"]: row for row in payload.get("rows", [])}


def _latest_weekly_rows(root: str | Path, target_date: str) -> dict[str, dict]:
    payload = _latest_weekly_payload(root, target_date)
    return {str(row.get("ticker", "")).zfill(4): row for row in payload.get("rows", [])}


def _latest_weekly_payload(root: str | Path, target_date: str) -> dict:
    files = sorted(
        path for path in Path(root).glob("weekly_snapshot_????-??-??.json")
        if path.stem.rsplit("_", 1)[-1] <= target_date
    )
    if not files:
        return {}
    return json.loads(files[-1].read_text(encoding="utf-8"))


def build_dashboard_payload(
    *, config_path: str | Path, market_path: str | Path,
    readiness_path: str | Path = "data/r1/evidence_readiness.json",
    valuation_root: str | Path = "data/r1/valuation_history",
    weekly_root: str | Path = "data/r1/weekly",
    supplemental_revision_path: str | Path = "data/r1/consensus/current_year_revision_history.csv",
    theme_review_path: str | Path = "data/r1/theme_reviews/latest.json",
    theme_path: str | Path = "config/r1_v02_themes.json",
    actual_transactions_path: str | Path = "data/r1/actual_transactions.json",
    transition_path: str | Path = "data/r1/transition/latest.json",
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
    weekly_by_ticker = _latest_weekly_rows(weekly_root, market["date"])
    weekly_payload = _latest_weekly_payload(weekly_root, market["date"])
    supplemental_revisions = latest_supplemental_revision_rows(
        supplemental_revision_path, as_of_date=market["date"],
    )
    theme_file = Path(theme_review_path)
    theme_review = json.loads(theme_file.read_text(encoding="utf-8")) if theme_file.exists() else {}
    transition_file = Path(transition_path)
    transition = json.loads(transition_file.read_text(encoding="utf-8")) if transition_file.exists() else {}
    if transition.get("date") != market.get("date"):
        transition = {}
    revision_progress = readiness.get("eps_revision_progress", {})
    revision_dates = revision_progress.get("earliest_calendar_eligibility", {})
    tabs: dict[str, list[list[object]]] = {
        title: ([] if title == "R1 Dashboard" else [list(headers)])
        for title, headers in TAB_SCHEMAS.items()
    }

    total_value = sum((market_by_ticker[s.ticker]["raw_close"] or 0) * s.shares for s in config.securities)
    held_count = sum(security.shares > 0 for security in config.securities)
    ranked = sorted(
        (
            row for row in weekly_by_ticker.values()
            if row.get("total_score") is not None and not row.get("core_lock")
        ),
        key=lambda row: (-float(row["total_score"]), str(row.get("ticker", ""))),
    )
    dashboard = tabs["R1 Dashboard"]
    dashboard.extend([
        ["R1研究版｜AI瓶頸預期差輪動"],
        ["最新資料日期", market["date"], "模型定位", "研究挑戰版", "尚未啟用交易"],
        ["資料狀態", "官方價格與五年估值定位已更新；當日籌碼獨立驗收，EPS修正序列仍在累積，不產生買賣指令。"],
        ["01｜今日候選排名"],
        ["順位", "股票", "R1分數", "代表意義", "狀態"],
        *([
            [
                f"Top{index}",
                f"{row['ticker']} {market_by_ticker[row['ticker']]['company']}",
                row["total_score"], "研究總分排名，不是交易指令", row.get("score_status", "READY"),
            ]
            for index, row in enumerate(ranked[:3], start=1)
        ] if ranked else [
            ["Top1", "尚未產生", "", "必要構面尚未完整", "研究資料累積中"],
            ["Top2", "尚未產生", "", "必要構面尚未完整", "研究資料累積中"],
            ["Top3", "尚未產生", "", "必要構面尚未完整", "研究資料累積中"],
        ]),
        ["排名不是交易指令", "R1核准前不會依排名自動買進、賣出或加碼。"],
        ["02｜目前追蹤持股（非R1成交）"],
        ["股票", "股數", "官方收盤", "參考市值", "狀態"],
    ])
    # R1 v0.3 replaces the legacy trade-oriented dashboard with a read-only
    # theme Top3 and holding-priority view. Legacy engines remain available but hidden.
    tabs["R1 Dashboard"] = _build_v03_dashboard(
        config=config, market=market, theme_review=theme_review, theme_path=theme_path,
        transition=transition,
    )

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
        ["03｜市場正在告訴我們什麼"],
        ["股票", "當年度EPS 30D／90D", "下年度EPS趨勢", "估值狀態", "籌碼狀態"],
    ])
    for security in config.securities:
        weekly = weekly_by_ticker.get(security.ticker, {})
        supplemental = supplemental_revisions.get(security.ticker, {})
        supplemental_text = "等待補充歷史"
        if supplemental:
            supplemental_text = (
                f"30D {float(supplemental['revision_30d']):+.1%}／"
                f"90D {float(supplemental['revision_90d']):+.1%}（不計分）"
            )
        dashboard.append([
            f"{security.ticker} {security.company}",
            supplemental_text,
            (
                f"{weekly.get('signal_stage')}／{weekly.get('trend_confidence')}／"
                f"{weekly.get('eps_trend_consecutive_weeks')}週"
            ) if weekly.get("signal_stage") else "等待跨週資料",
            weekly.get("valuation_state") or "等待跨週資料",
            weekly.get("flow_state") or "等待20TD資料",
        ])
    dashboard.extend([
        ["04｜AI瓶頸題材Top1（季度評估）"],
        ["題材", "目前Top1", "龍頭分數", "評估狀態", "資料缺口"],
    ])
    for theme in theme_review.get("themes", []):
        top1 = theme.get("top1") or {}
        gaps = theme.get("data_gaps", [])
        dashboard.append([
            theme.get("theme_name"),
            f"{top1.get('ticker')} {top1.get('company', '')}" if top1 else "尚未核准",
            top1.get("leader_score", ""),
            "季度Top1已完成" if theme.get("status") == "READY" else "必要資料未完整",
            f"{len(gaps)}檔待補" if gaps else "無",
        ])
    if not theme_review.get("themes"):
        dashboard.append(["題材契約已建立", "尚未核准", "", "等待題材資料建檔", "9個題材"])
    dashboard.extend([
        ["05｜產業瓶頸與催化狀態"],
        ["股票", "瓶頸階段／分數", "催化狀態／分數", "價量籌碼分數", "R1總分"],
    ])
    for security in config.securities:
        weekly = weekly_by_ticker.get(security.ticker, {})
        dashboard.append([
            f"{security.ticker} {security.company}",
            f"{weekly.get('bottleneck_stage')}／{weekly.get('bottleneck_score')}"
            if weekly.get("bottleneck_score") is not None else "等待證據或新週快照",
            f"{weekly.get('catalyst_state')}／{weekly.get('catalyst_score')}"
            if weekly.get("catalyst_score") is not None else "等待事件或新週快照",
            weekly.get("price_chip_score") if weekly.get("price_chip_score") is not None else "等待EPS 4W與籌碼",
            weekly.get("total_score") if weekly.get("total_score") is not None else "必要構面未完整",
        ])
    dashboard.extend([
        ["06｜下一個動態觸發條件"],
        ["股票", "下一次加碼", "下一次減碼", "退出", "目前輸入"],
    ])
    for security in config.securities:
        if security.shares <= 0:
            continue
        weekly = weekly_by_ticker.get(security.ticker, {})
        dashboard.append([
            f"{security.ticker} {security.company}",
            weekly.get("next_add_trigger") or "等待跨週資料",
            weekly.get("next_trim_trigger") or "等待跨週資料",
            weekly.get("next_exit_trigger") or "等待跨週資料",
            weekly.get("current_trigger_inputs") or "等待跨週資料",
        ])
    dashboard.extend([
        ["07｜Shadow換倉候選（非交易指令）"],
        ["來源股", "目標股", "總分優勢", "Shadow狀態", "原因"],
    ])
    shadow_candidates = weekly_payload.get("shadow_rotation_candidates", [])
    if shadow_candidates:
        for candidate in shadow_candidates[:5]:
            dashboard.append([
                candidate.get("source"), candidate.get("target"), candidate.get("score_advantage"),
                candidate.get("status"), candidate.get("reason"),
            ])
    else:
        dashboard.append([
            "尚未產生", "尚未產生", "",
            weekly_payload.get("shadow_rotation_status", "等待新週快照"),
            f"缺資料配對數：{weekly_payload.get('shadow_rotation_blocked_pair_count', 0)}",
        ])
    dashboard.extend([
        ["08｜資料與模型狀態"],
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
        ["09｜模型完整說明"],
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
            bool(readiness_row.get("price_chip_ready")), weekly_by_ticker.get(security.ticker, {}).get("total_score"),
            action, reason,
        ])

    actual_file = Path(actual_transactions_path)
    if actual_file.exists():
        actual_payload = json.loads(actual_file.read_text(encoding="utf-8"))
        for item in actual_payload.get("transactions", []):
            tabs["R1模擬交易紀錄"].append([
                item["transaction_date"], "", f"USER_CONFIRMED_{item['action']}", item["ticker"],
                item["company"], item["shares"], item["price"], item["gross_amount"],
                item.get("fees"), item.get("tax"), item.get("net_cash_flow"), "ACTUAL", "",
                item.get("realized_pnl"), 0, item["reason_status"],
            ])
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
    parser.add_argument("--weekly-root", default="data/r1/weekly")
    parser.add_argument("--supplemental-revision", default="data/r1/consensus/current_year_revision_history.csv")
    parser.add_argument("--theme-review", default="data/r1/theme_reviews/latest.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--actual-transactions", default="data/r1/actual_transactions.json")
    parser.add_argument("--transition", default="data/r1/transition/latest.json")
    parser.add_argument("--output", default="data/r1/dashboard_payload.json")
    args = parser.parse_args()
    payload = build_dashboard_payload(
        config_path=args.config, market_path=args.market, readiness_path=args.readiness,
        valuation_root=args.valuation_root, weekly_root=args.weekly_root,
        supplemental_revision_path=args.supplemental_revision,
        theme_review_path=args.theme_review,
        theme_path=args.themes,
        actual_transactions_path=args.actual_transactions,
        transition_path=args.transition,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
