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


MODEL_LOGIC = """R1 v0.6｜實際帳戶總覽與AI瓶頸換倉顧問

【模型任務】
R1記錄Ryan實際成交與帳戶結果，並與「8/5全部轉為0050正二後抱住」同起點基準每日比較。績效比較排除未包含於8/5共同本金的既有台積電持股及其配息；總持股區仍完整顯示。{performance_status}

【季度Top3】
結構性龍頭評分：AI瓶頸直接性25%、產業與技術地位25%、AI營收兌現20%、財務與獲利品質20%、市場代表性10%。官方與公司正式揭露優先；分析師與市場共識只能補充，不能單獨決定排名。任一成分股必要證據不足時，該題材Top3維持待資料。

【每日換倉優先序】
公開資料核心分數：結構瓶頸25%、營收獲利兌現25%、題材動能與催化15%、相對估值15%、價格籌碼風險20%。法人目標價上行與修正廣度另作信心加減項，缺少時不補0，也不阻斷核心排名。建議與實際成交分離，只有Ryan確認成交才更新持股。

【無差別殺盤過渡層】
未來半年五檔目標維持不變。當加權指數或十一題材候選池出現廣泛急跌時，R1開放全候選池進行過渡比較，包括五檔目標本身。跌深不是買進理由；候選仍須通過財務、題材催化及風險資料。盤中只列觀察，收盤後以官方資料確認；模型不自動成交。

【更新頻率】
每個交易日更新兩條績效線與換倉建議；每週更新12個月目標價共識、題材催化與風險；每季重評AI瓶頸題材、成分股與Top3。目標價採90日內至少3家可識別機構的中位數，單一外資只展示、不計分。

【模型邊界】
R1是report-only顧問，不自動下單。V4-D與C6程式保留但每日發布已暫停，直到Ryan明確要求恢復。"""


def _model_logic(*, comparison_ready: bool) -> str:
    performance_status = (
        "兩條線的共同起始NAV、外部現金流與目前現金已完成對帳，Dashboard可發布同口徑累積報酬與差額。"
        if comparison_ready else
        "兩條線尚未完成共同起始NAV與現金流對帳，因此暫不發布誰勝誰負。"
    )
    return MODEL_LOGIC.format(performance_status=performance_status)

PERFORMANCE_LINE_LABELS = {
    "ACTUAL": "Ryan 8/5後操作範圍（排除既有台積電）",
    "00631L_BUY_HOLD": "8/5全部轉0050正二後長抱",
}

RECOMMENDATION_DISPLAY = {
    ("NO_ACTION", "HOLD"): ("資料不足", "尚無法產生換倉建議"),
    ("WATCH1", "OBSERVE_ONLY"): ("觀察1", "僅觀察"),
    ("WATCH2", "OBSERVE_ONLY"): ("觀察2", "僅觀察"),
    ("WATCH3", "OBSERVE_ONLY"): ("觀察3", "僅觀察"),
}


def _money(value: object) -> str:
    return f"{float(value):,.1f}" if isinstance(value, (int, float)) else str(value)


def _percent(value: object) -> str:
    return f"{float(value):.1%}" if isinstance(value, (int, float)) else str(value)


def _build_v03_dashboard(*, config: R1Config, market: dict, theme_review: dict,
                         theme_path: str | Path, transition: dict | None = None,
                         comparison: dict | None = None,
                         recommendations: list[dict] | None = None,
                         weekly_by_ticker: dict[str, dict] | None = None,
                         v05_by_ticker: dict[str, dict] | None = None,
                         readiness: dict | None = None,
                         target_consensus_ready_count: int = 0,
                         anonymous_target_ready_count: int = 0,
                         anonymous_target_missing: list[str] | None = None,
                         total_actual_equity: float | None = None,
                         actual_positions: list[dict] | None = None) -> list[list[object]]:
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
    weekly_by_ticker = weekly_by_ticker or {}
    reference_by_ticker = {
        ticker: row.get("current_reference_score")
        for ticker, row in weekly_by_ticker.items()
        if row.get("current_reference_score") is not None
    }
    v05_by_ticker = v05_by_ticker or {}
    readiness = readiness or {}
    public_core_ready_count = sum(
        row.get("v05_status") == "READY" for row in v05_by_ticker.values()
    )
    target_overlay_ready_count = sum(
        row.get("v05_target_overlay_status") == "READY" for row in v05_by_ticker.values()
    )
    revision_progress = readiness.get("eps_revision_progress", {})
    revision_ready = revision_progress.get("ready_counts", {})
    required_rows = [row for row in readiness.get("rows", []) if row.get("score_required", True)]
    missing_consensus = [str(row.get("ticker", "")).zfill(4) for row in required_rows
                         if not row.get("consensus_ready")]
    target_missing_count = max(len(v05_by_ticker) - target_consensus_ready_count, 0)
    anonymous_target_missing = anonymous_target_missing or []
    for ticker, row in v05_by_ticker.items():
        if row.get("v05_reference_score") is not None:
            reference_by_ticker[ticker] = row["v05_reference_score"]
    closes = {
        str(item.get("ticker", "")).zfill(4): item.get("raw_close")
        for item in market.get("rows", [])
    }
    actual_positions = actual_positions or []
    for item in actual_positions:
        ticker = str(item.get("ticker", "")).upper()
        if ticker not in held and isinstance(item.get("shares"), (int, float)) and item["shares"] > 0:
            held[ticker] = item
        if isinstance(item.get("raw_close"), (int, float)):
            closes[ticker] = item["raw_close"]
    actual_equity = total_actual_equity if isinstance(total_actual_equity, (int, float)) else next(
        (item.get("equity_market_value") for item in (comparison or {}).get("rows", [])
         if item.get("line") == "ACTUAL"), None
    )
    display_tickers = targets + [
        ticker for ticker in held if ticker not in set(targets)
    ]
    rows: list[list[object]] = [
        ["Ryan｜R1實際帳戶總覽與換倉顧問"],
        ["最新資料日期", market["date"], "模型定位", "實際績效追蹤＋report-only換倉建議", "不自動成交"],
        ["資料狀態", (
            f"公開資料核心 {public_core_ready_count}/{len(v05_by_ticker)}；"
            f"法人目標價共識 {target_consensus_ready_count}/{len(v05_by_ticker)}；"
            f"具4W修正比較的完整信心層 {target_overlay_ready_count}/{len(v05_by_ticker)}；"
            f"EPS修正歷史 1W {revision_ready.get('1w', 0)}、"
            f"4W {revision_ready.get('4w', 0)}、12W {revision_ready.get('12w', 0)}。"
            "信心層缺值不補0、不阻斷核心排名；不產生自動交易。"
        )],
        ["01｜實際持股與未來半年目標持股"],
        ["所屬題材", "股票", "優先持有參考值", "實際持有", "當日收盤", "持股市值", "持股占比", "半年目標"],
    ]
    for ticker in display_tickers:
        security = securities.get(ticker)
        holding = held.get(ticker)
        company = security.company if security else holding.get("company", ticker)
        shares = security.shares if security else holding.get("shares", 0)
        close = closes.get(ticker)
        market_value = shares * close if ticker in held and isinstance(close, (int, float)) else None
        weight = market_value / actual_equity if market_value is not None and isinstance(actual_equity, (int, float)) and actual_equity else None
        rows.append([
            "；".join(membership.get(ticker, ["尚未納入11題材池"])),
            f"{ticker} {company}",
            (priority_by_ticker.get(ticker) if priority_by_ticker.get(ticker) is not None
             else reference_by_ticker.get(ticker) if reference_by_ticker.get(ticker) is not None
             else "評分資料未齊"),
            f"實際持有｜{shares:,}股" if ticker in held else "",
            _money(close) if ticker in held and close is not None else "",
            _money(market_value) if market_value is not None else "",
            _percent(weight) if weight is not None else "",
            "未來半年目標" if ticker in targets else "既有實際持股",
        ])
    comparison = comparison or {"rows": [], "comparison_ready": False}
    recommendations = recommendations or []
    comparison_rows = comparison.get("rows", [])
    actual_nav = next((item.get("nav") for item in comparison_rows if item.get("line") == "ACTUAL"), None)
    rows.extend([
        ["02｜兩條績效線"],
        ["比較線", "當日NAV", "累計投入本金", "累積報酬", "狀態", "相較實際操作差額"],
        *[[PERFORMANCE_LINE_LABELS.get(item["line"], item["line"]),
           _money(item.get("nav") or item.get("equity_market_value")) if
           (item.get("nav") or item.get("equity_market_value")) is not None else "待對帳",
           _money(item.get("starting_nav")) if item.get("starting_nav") is not None else "待對帳",
           _percent(item.get("return_pct")) if item.get("return_pct") is not None else "不發布",
           (item.get("source_note") if item["line"] == "ACTUAL" and item.get("nav") is None
            and item.get("equity_market_value") is not None else item.get("status")),
           ("=B21-B20"
            if item.get("line") == "00631L_BUY_HOLD"
            and isinstance(item.get("nav"), (int, float)) and isinstance(actual_nav, (int, float)) else "")]
          for item in comparison_rows],
        ["03｜今日換倉建議"],
        ["優先序", "動作", "換出", "換入", "理由／狀態"],
        *[[(f"優先{item['priority'][1:]}" if item["action"] == "REVIEW_SWITCH_IN" else
            RECOMMENDATION_DISPLAY.get((item["priority"], item["action"]),
                                       (item["priority"], item["action"]))[0]),
           ("換倉檢視" if item["action"] == "REVIEW_SWITCH_IN" else
            RECOMMENDATION_DISPLAY.get((item["priority"], item["action"]),
                                       (item["priority"], item["action"]))[1]),
           (f"{item.get('source_ticker')} {securities[item.get('source_ticker')].company}"
            if item.get("source_ticker") in securities else item.get("source_ticker", "")),
           f"{item.get('target_ticker', '')} {item.get('target_company', '')}".strip(), item["reason"]]
          for item in recommendations],
    ])
    transition = transition or {}
    transition_status = transition.get("status", "尚未建立")
    rows.extend([
        ["04｜無差別殺盤過渡層（研究觀察）"],
        ["狀態", transition_status, "候選池下跌比例", _percent(transition.get("negative_share")) if isinstance(transition.get("negative_share"), (int, float)) else "待資料",
         f"報酬中位數：{_percent(transition.get('universe_median_return')) if isinstance(transition.get('universe_median_return'), (int, float)) else '待資料'}"],
        ["加權指數單日報酬", _percent(transition.get("taiex_return")) if isinstance(transition.get("taiex_return"), (int, float)) else "待資料", "是否啟動",
         "是｜等待Ryan檢視" if transition.get("triggered") else "否", "五檔長期目標維持不變"],
        ["過渡候選狀態", transition.get("candidate_status", "待資料"), "候選數",
         transition.get("candidate_count", 0), "只列比較，不自動成交"],
        *([
            [f"候選{index}", f"{item['ticker']} {item.get('company') or ''}",
             f"優先值 {float(item['priority_score']):.1f}", f"當日 {float(item['daily_return']):+.1%}",
             f"BIAS20 {float(item['bias20']):+.1%}"]
            for index, item in enumerate(transition.get("candidates", []), start=1)
        ]),
        ["執行邊界", "盤中只觀察；收盤後重算；不自動交易，長期五檔目標不變。"],
        ["05｜分數規則"],
        ["分數", "構成", "權重", "更新頻率", "用途"],
        ["季度結構性龍頭", "瓶頸直接性／產業技術地位／AI營收兌現／財務獲利品質／市場代表性",
         "25%／25%／20%／20%／10%", "每季", "決定每個題材Top1～Top3"],
        ["每日換倉優先序", "結構瓶頸／營收獲利兌現／題材動能與催化／相對估值／價格籌碼風險；法人目標價另作信心加減項",
         "25%／25%／15%／15%／20%", "每日排名＋每週事件；目標價有資料才疊加", "從實際持股角度提供換出／換入優先序"],
        ["即時參考分數", "已取得的估值／瓶頸／催化／市場風險，依既定權重重新正規化；EPS另列信心",
         "report-only", "每日市場＋每週證據", "不因4W／12W未滿而整份空白，不產生交易指令"],
        ["資料完成度", "公開資料核心／法人目標價共識／完整目標價修正信心層／EPS修正PIT歷史",
         f"{public_core_ready_count}/{len(v05_by_ticker)}／{target_consensus_ready_count}/{len(v05_by_ticker)}／"
         f"{target_overlay_ready_count}/{len(v05_by_ticker)}／"
         f"1W {revision_ready.get('1w', 0)}、4W {revision_ready.get('4w', 0)}、12W {revision_ready.get('12w', 0)}",
         "每日讀回", "核心與信心層分開揭露，不再用舊0/52誤稱整體未完成"],
        ["06｜更新排程"],
        ["頻率", "工作", "產出", "失敗處理", "交易影響"],
        ["每日收盤後", f"累積{universe_count}檔官方價格與市場資料", "每日資料庫", "缺資料重抓並列明缺口", "無"],
        ["每週最後交易日", "更新需求、訂單、事件與風險", "週度證據狀態", "證據不足維持原值或待資料", "無"],
        ["每季財報揭露後", f"重評{len(themes)}題材Top3", "季度排名", "全題材成分證據完整才發布", "無"],
        ["每半年", "檢討題材與成分股", "增刪建議與證據", "保留歷史版本", "無"],
        ["07｜資料品質異常表"],
        ["項目", "目前覆蓋", "缺口", "處理方式", "是否阻擋核心排名"],
        ["公開核心五構面", f"{public_core_ready_count}/{len(v05_by_ticker)}",
         "無" if public_core_ready_count == len(v05_by_ticker) else "仍有必要構面缺漏",
         "每日收盤後有限重試", "是" if public_core_ready_count < len(v05_by_ticker) else "否"],
        ["法人EPS共識", f"{readiness.get('consensus_ready_count', 0)}/{len(v05_by_ticker)}",
         "無" if not missing_consensus else "缺：" + "、".join(missing_consensus),
         "每週重抓；單一來源不升格", "否，只降低信心"],
        ["嚴格法人目標價", f"{target_consensus_ready_count}/{len(v05_by_ticker)}",
         f"缺{target_missing_count}檔",
         "每週有限重試；需90日內至少3家可識別機構", "否，只降低信心"],
        ["匿名市場目標價", f"{anonymous_target_ready_count}/{len(v05_by_ticker)}",
         "無" if not anonymous_target_missing else "缺：" + "、".join(anonymous_target_missing),
         "每週有限重試；只展示、不計分、不提高信心", "否，只供參考"],
        ["EPS修正歷史", f"1W {revision_ready.get('1w', 0)}／4W {revision_ready.get('4w', 0)}／12W {revision_ready.get('12w', 0)}",
         f"4W最早{revision_progress.get('earliest_calendar_eligibility', {}).get('4w', '待累積')}；"
         f"12W最早{revision_progress.get('earliest_calendar_eligibility', {}).get('12w', '待累積')}",
         "只累積真實PIT快照，不回填", "否，只降低信心"],
        ["自動交易決策", "未啟用", "每日換倉參考仍正常發布",
         "實際買賣由Ryan自行決定", "不自動成交"],
        ["08｜模型完整說明"],
        [_model_logic(comparison_ready=bool(comparison.get("comparison_ready")))],
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
    anonymous_target_price_path: str | Path = "data/r1/target_prices/yahoo_aggregate_latest.json",
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
    readiness_date = readiness.get("as_of_date")
    if readiness_date and readiness_date != market.get("date"):
        raise ValueError(
            f"R1 readiness date {readiness_date} does not match market date {market.get('date')}"
        )
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
    anonymous_target_file = Path(anonymous_target_price_path)
    anonymous_targets = json.loads(anonymous_target_file.read_text(encoding="utf-8")) if anonymous_target_file.exists() else {"rows": []}
    anonymous_target_by_ticker = {
        str(row.get("ticker", "")).zfill(4): row for row in anonymous_targets.get("rows", [])
        if row.get("scoreable") is False and str(row.get("status", "")).startswith("READY_AGGREGATE")
    }
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
            "observed_points": v05.get("v05_observed_points"),
            "observed_max_points": v05.get("v05_observed_max_points"),
            "missing_components": v05.get("v05_missing_components", []),
            "overlay_missing_components": v05.get("v05_target_overlay_missing_components", []),
            "target_upside": target_price_by_ticker.get(ticker, {}).get("consensus_upside"),
            "anonymous_target_upside": anonymous_target_by_ticker.get(ticker, {}).get("median_upside"),
            "price_chip_risk": v05.get("price_chip_risk"),
            "theme_momentum_and_catalyst": v05.get("theme_momentum_and_catalyst"),
            "official_negative_flags": v05.get("official_negative_flags", []),
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
    score_required_count = readiness.get("score_required_ticker_count", readiness["requested_ticker_count"])
    required_readiness_rows = [
        row for row in readiness.get("rows", []) if row.get("score_required", True)
    ]
    score_required_tickers = {row.get("ticker") for row in required_readiness_rows}
    target_ready_required = sum(
        bool(row.get("scoreable")) and str(row.get("ticker", "")).zfill(4) in score_required_tickers
        for row in target_prices.get("rows", [])
    )
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
        weekly_by_ticker=weekly_by_ticker,
        v05_by_ticker=v05_by_ticker,
        readiness=readiness,
        target_consensus_ready_count=sum(
            bool(row.get("scoreable"))
            for ticker, row in target_price_by_ticker.items()
            if ticker in v05_by_ticker
        ),
        anonymous_target_ready_count=sum(ticker in anonymous_target_by_ticker for ticker in v05_by_ticker),
        anonymous_target_missing=sorted(ticker for ticker in v05_by_ticker if ticker not in anonymous_target_by_ticker),
        total_actual_equity=actual_account.get("equity_market_value"),
        actual_positions=actual_account.get("positions", []),
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
        ["EPS共識", f"{readiness['consensus_ready_count']}/{score_required_count}",
         "完整" if readiness["consensus_ready_count"] == score_required_count else "部分完成",
         "EPS修正與前瞻估值", market["date"]],
        ["EPS修正歷史", f"{readiness.get('eps_revision_ready_count', 0)}/{score_required_count}",
         "完整" if readiness.get("eps_revision_ready_count") == score_required_count else "累積中",
         "至少具備1W、4W及12W PIT基準；最早日："
         f"1W {revision_dates.get('1w') or '待首筆'}／4W {revision_dates.get('4w') or '待首筆'}／"
         f"12W {revision_dates.get('12w') or '待首筆'}", market["date"]],
        ["12個月目標價共識", f"{target_ready_required}/{score_required_count}",
         "完整" if target_ready_required == score_required_count else "部分完成",
         "90日內至少3家可識別機構的中位數；不足不評分", target_prices.get("date", market["date"])],
        ["催化證據", f"{readiness['catalyst_ready_count']}/{score_required_count}",
         "完整" if readiness["catalyst_ready_count"] == score_required_count else "部分完成",
         "需求與事件驗證", market["date"]],
        ["瓶頸證據", f"{readiness['bottleneck_ready_count']}/{score_required_count}",
         "完整" if readiness["bottleneck_ready_count"] == score_required_count else "部分完成",
         "AI剛性需求驗證", market["date"]],
        ["20日價量籌碼序列", f"{readiness.get('price_chip_ready_count', 0)}/{score_required_count}",
         "完整" if readiness.get("price_chip_ready_count") == score_required_count else "部分完成",
         "歷史價格與籌碼構面", market["date"]],
        ["當日法人與融資", f"{readiness.get('current_chip_ready_count', 0)}/{score_required_count}",
         "完整" if readiness.get("current_chip_ready_count") == score_required_count else "等待官方資料",
         "當期訊號驗收；不可由舊資料代替", market["date"]],
        ["五年估值定位", f"{sum(bool(row.get('valuation_ready')) for row in required_readiness_rows)}/{score_required_count}",
         "完整" if all(row.get("valuation_ready") for row in required_readiness_rows) else "部分完成",
         "下年度Forward PE自身五年百分位", market["date"]],
        ["交易建議", f"{readiness['trade_ready_count']}/{score_required_count}",
         "尚未啟用", "Action規則核准後才產生", market["date"]],
        ["09｜模型完整說明"],
        [_model_logic(comparison_ready=bool(comparison.get("comparison_ready")))],
    ])

    for security in config.securities:
        row = market_by_ticker[security.ticker]
        readiness_row = readiness_by_ticker.get(security.ticker, {})
        valuation_row = valuation_by_ticker.get(security.ticker, {})
        if security.core_lock:
            action, reason = "CORE", "CORE_LOCK"
        elif readiness_row.get("reference_score_ready"):
            action, reason = "OBSERVE_ONLY", "REPORT_ONLY_CORE_READY"
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
            gross_amount = item.get("gross_amount")
            if gross_amount is None and isinstance(item.get("net_cash_flow"), (int, float)):
                gross_amount = abs(float(item["net_cash_flow"]))
            tabs["R1實際交易紀錄"].append([
                item["transaction_date"], "", f"USER_CONFIRMED_{item['action']}", item["ticker"],
                item["company"], item["shares"], item["price"], gross_amount,
                item.get("fees"), item.get("tax"), item.get("net_cash_flow"), "ACTUAL", "",
                item.get("realized_pnl"), 0, item.get("reason_status", "Ryan券商截圖確認；金額已含交易成本。"),
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
