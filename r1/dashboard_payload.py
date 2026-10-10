from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.config import R1Config
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs
from r1.toalpha_revision_history import latest_rows as latest_supplemental_revision_rows
from r1.theme_policy import load_themes
from r1.performance_comparison import build_comparison
from r1.recommendations import build_recommendations


MODEL_LOGIC = """R1 v0.5｜實際帳戶總覽與AI瓶頸換倉顧問

【模型任務】
R1記錄Ryan實際成交與帳戶結果，並與「8/5全部轉為0050正二後抱住」及「8/5原持股完全不動」兩條同起點基準每日比較。三條線未完成共同起始NAV與現金流對帳前，不發布誰勝誰負。

【季度Top3】
結構性龍頭評分：AI瓶頸直接性25%、產業與技術地位25%、AI營收兌現20%、財務與獲利品質20%、市場代表性10%。官方與公司正式揭露優先；分析師與市場共識只能補充，不能單獨決定排名。任一成分股必要證據不足時，該題材Top3維持待資料。

【每日換倉優先序】
結構瓶頸20%、營收獲利兌現20%、12個月目標價上行空間20%、目標價修正與機構廣度10%、題材動能與催化10%、相對估值10%、價格籌碼風險10%。缺一構面不補0、不重配權重。建議與實際成交分離，只有Ryan確認成交才更新持股。

【無差別殺盤過渡層】
未來半年五檔目標維持不變。當加權指數或十一題材候選池出現廣泛急跌時，R1開放全候選池進行過渡比較，包括五檔目標本身。跌深不是買進理由；候選仍須通過財務、題材催化及風險資料。盤中只列觀察，收盤後以官方資料確認；模型不自動成交。

【更新頻率】
每個交易日更新三條績效線與換倉建議；每週更新12個月目標價共識、題材催化與風險；每季重評AI瓶頸題材、成分股與Top3。目標價採90日內至少3家可識別機構的中位數，單一外資只展示、不計分。

【模型邊界】
R1是report-only顧問，不自動下單。V4-D與C6程式保留但每日發布已暫停，直到Ryan明確要求恢復。"""


def _build_v03_dashboard(*, config: R1Config, market: dict, theme_review: dict,
                         theme_path: str | Path, transition: dict | None = None,
                         comparison: dict | None = None,
                         recommendations: list[dict] | None = None) -> list[list[object]]:
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
        ["Ryan｜R1實際帳戶總覽與換倉顧問"],
        ["最新資料日期", market["date"], "模型定位", "實際績效追蹤＋report-only換倉建議", "不自動成交"],
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
    comparison = comparison or {"rows": [], "comparison_ready": False}
    recommendations = recommendations or []
    rows.extend([
        ["02｜三條績效線"],
        ["比較線", "當日NAV", "共同起始NAV", "累積報酬", "狀態"],
        *[[item["line"], item.get("nav") or item.get("equity_market_value") or "待對帳", item.get("starting_nav") or "待對帳",
           item.get("return_pct") if item.get("return_pct") is not None else "不發布",
           ("僅股票市值；現金待對帳" if item["line"] == "ACTUAL" and item.get("nav") is None
            and item.get("equity_market_value") is not None else item.get("status"))]
          for item in comparison.get("rows", [])],
        ["03｜今日換倉建議"],
        ["優先序", "動作", "換出", "換入", "理由／狀態"],
        *[[item["priority"], item["action"], item.get("source_ticker", ""),
           f"{item.get('target_ticker', '')} {item.get('target_company', '')}".strip(), item["reason"]]
          for item in recommendations],
    ])
    transition = transition or {}
    transition_status = transition.get("status", "尚未建立")
    rows.extend([
        ["04｜無差別殺盤過渡層（研究觀察）"],
        ["狀態", transition_status, "候選池下跌比例", transition.get("negative_share", "待資料"),
         f"報酬中位數：{transition.get('universe_median_return', '待資料')}"],
        ["加權指數單日報酬", transition.get("taiex_return", "待資料"), "是否啟動",
         "是｜等待Ryan檢視" if transition.get("triggered") else "否", "五檔長期目標維持不變"],
        ["過渡候選狀態", transition.get("candidate_status", "待資料"), "候選數",
         transition.get("candidate_count", 0), "只列比較，不自動成交"],
        *([
            [f"候選{index}", f"{item['ticker']} {item.get('company') or ''}",
             f"優先值 {item['priority_score']}", f"當日 {item['daily_return']:+.2%}",
             f"BIAS20 {item['bias20']:+.2%}"]
            for index, item in enumerate(transition.get("candidates", []), start=1)
        ]),
        ["執行邊界", "盤中只觀察；收盤後重算；不自動交易，長期五檔目標不變。"],
        ["05｜分數規則"],
        ["分數", "構成", "權重", "更新頻率", "用途"],
        ["季度結構性龍頭", "瓶頸直接性／產業技術地位／AI營收兌現／財務獲利品質／市場代表性",
         "25%／25%／20%／20%／10%", "每季", "決定每個題材Top1～Top3"],
        ["優先持有參考值", "結構性龍頭／營收獲利成長／自身歷史估值／價格風險安全度／需求訂單催化",
         "30%／25%／20%／15%／10%", "每日資料＋週月季事件", "提供Ryan自行比較持有優先序"],
        ["06｜更新排程"],
        ["頻率", "工作", "產出", "失敗處理", "交易影響"],
        ["每日收盤後", f"累積{universe_count}檔官方價格與市場資料", "每日資料庫", "缺資料重抓並列明缺口", "無"],
        ["每週最後交易日", "更新需求、訂單、事件與風險", "週度證據狀態", "證據不足維持原值或待資料", "無"],
        ["每季財報揭露後", f"重評{len(themes)}題材Top3", "季度排名", "全題材成分證據完整才發布", "無"],
        ["每半年", "檢討題材與成分股", "增刪建議與證據", "保留歷史版本", "無"],
        ["07｜模型完整說明"],
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
    benchmark_config_path: str | Path = "config/r1_performance_benchmarks.json",
    actual_account_path: str | Path = "data/r1/actual_account_state.json",
    benchmark_market_path: str | Path = "data/r1/benchmark_market_latest.json",
    target_price_path: str | Path = "data/r1/target_prices/latest.json",
    v05_rank_path: str | Path = "data/r1/v05/latest.json",
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

    benchmark_config = json.loads(Path(benchmark_config_path).read_text(encoding="utf-8"))
    actual_account_file = Path(actual_account_path)
    actual_account = json.loads(actual_account_file.read_text(encoding="utf-8")) if actual_account_file.exists() else {}
    benchmark_market_file = Path(benchmark_market_path)
    benchmark_market = json.loads(benchmark_market_file.read_text(encoding="utf-8")) if benchmark_market_file.exists() else {"rows": []}
    comparison_market = {"rows": [*market.get("rows", []), *benchmark_market.get("rows", [])]}
    comparison = build_comparison(
        date=market["date"], market=comparison_market, benchmark_config=benchmark_config,
        actual_snapshot=actual_account,
    )
    target_price_file = Path(target_price_path)
    target_prices = json.loads(target_price_file.read_text(encoding="utf-8")) if target_price_file.exists() else {"rows": []}
    target_price_by_ticker = {str(row.get("ticker", "")).zfill(4): row for row in target_prices.get("rows", [])}
    v05_file = Path(v05_rank_path)
    v05_payload = json.loads(v05_file.read_text(encoding="utf-8")) if v05_file.exists() else {"rows": []}
    if v05_payload.get("date") != market.get("date"):
        v05_payload = {"rows": []}
    v05_by_ticker = {str(row.get("ticker", "")).zfill(4): row for row in v05_payload.get("rows", [])}
    for item in comparison["rows"]:
        tabs["R1績效每日比較"].append([item[key] for key in TAB_SCHEMAS["R1績效每日比較"]])

    target_payload = json.loads(Path(theme_path).read_text(encoding="utf-8"))
    target_tickers = {str(value).zfill(4) for value in target_payload.get("target_portfolio_6m", [])}
    held_tickers = {security.ticker for security in config.securities if security.shares > 0}
    recommendation_candidates = []
    for ticker, weekly in weekly_by_ticker.items():
        v05 = v05_by_ticker.get(ticker, {})
        recommendation_candidates.append({
            "ticker": ticker, "company": market_by_ticker.get(ticker, {}).get("company", ""),
            "score": v05.get("v05_total_score"),
            "target_upside": target_price_by_ticker.get(ticker, {}).get("consensus_upside"),
            "reason": v05.get("v05_reason"),
        })
    recommendations = build_recommendations(
        date=market["date"], candidates=recommendation_candidates,
        held_tickers=held_tickers, target_tickers=target_tickers,
    )
    for item in recommendations:
        tabs["R1每日換倉建議"].append([item[key] for key in TAB_SCHEMAS["R1每日換倉建議"]])

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
        transition=transition, comparison=comparison, recommendations=recommendations,
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
            tabs["R1實際交易紀錄"].append([
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
    parser = argparse.ArgumentParser(description="Build the five-tab R1 actual-account advisory dashboard payload.")
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
    parser.add_argument("--benchmarks", default="config/r1_performance_benchmarks.json")
    parser.add_argument("--actual-account", default="data/r1/actual_account_state.json")
    parser.add_argument("--benchmark-market", default="data/r1/benchmark_market_latest.json")
    parser.add_argument("--target-prices", default="data/r1/target_prices/latest.json")
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
        benchmark_config_path=args.benchmarks,
        actual_account_path=args.actual_account,
        benchmark_market_path=args.benchmark_market, target_price_path=args.target_prices,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
