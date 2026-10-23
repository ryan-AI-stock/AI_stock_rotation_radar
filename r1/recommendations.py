from __future__ import annotations

from typing import Any


# Conservative, economically interpretable guardrails for a long-hold advisory.
# A higher total score alone is not a reason to rotate: the incumbent must first
# show observable weakness/risk and the challenger must be healthy by the same
# free-data measures.  These are report-only defaults, not execution rules.
MINIMUM_SCORE_ADVANTAGE = 10.0
INCUMBENT_WEAK_THRESHOLD = 40.0
CHALLENGER_HEALTHY_THRESHOLD = 50.0


def _is_impaired(row: dict[str, Any]) -> bool:
    values = (row.get("price_chip_risk"), row.get("theme_momentum_and_catalyst"))
    observed = [float(value) for value in values if value is not None]
    return bool(observed) and min(observed) <= INCUMBENT_WEAK_THRESHOLD


def _is_healthy_challenger(row: dict[str, Any]) -> bool:
    values = (row.get("price_chip_risk"), row.get("theme_momentum_and_catalyst"))
    return all(value is not None and float(value) >= CHALLENGER_HEALTHY_THRESHOLD for value in values)


def build_recommendations(*, date: str, candidates: list[dict[str, Any]], held_tickers: set[str],
                          target_tickers: set[str], max_items: int = 3) -> list[dict[str, Any]]:
    """Produce advisory-only ranked changes; incomplete inputs resolve to NO_ACTION."""
    eligible = [row for row in candidates if row.get("score") is not None]
    eligible.sort(key=lambda row: (
        -float(row["score"]),
        -(float(row["target_upside"]) if row.get("target_upside") is not None else float("-inf")),
        str(row["ticker"]),
    ))
    if not eligible:
        observed = [
            row for row in candidates
            if isinstance(row.get("observed_points"), (int, float))
            and isinstance(row.get("observed_max_points"), (int, float))
            and row.get("observed_max_points", 0) > 0
        ]
        if not observed:
            return [_no_action(date, "目標價共識或必要評分資料不足，不以NA推導交易")]
        unheld = [row for row in observed if str(row["ticker"]).zfill(4) not in held_tickers]
        if not unheld:
            return [_no_action(date, "目前有觀察分的股票均已持有；資料未完整前不換倉")]
        max_coverage = max(float(row["observed_max_points"]) for row in unheld)
        comparable = [row for row in unheld if float(row["observed_max_points"]) == max_coverage]
        comparable.sort(key=lambda row: (-float(row["observed_points"]), str(row["ticker"])))
        watches = []
        for row in comparable:
            ticker = str(row["ticker"]).zfill(4)
            watches.append({
                "date": date, "priority": f"WATCH{len(watches) + 1}", "action": "OBSERVE_ONLY",
                "source_ticker": "", "target_ticker": ticker, "target_company": row.get("company", ""),
                "target_score": row["observed_points"], "target_upside": None, "confidence": "LOW",
                "reason": f"現有證據觀察分 {row['observed_points']:.1f}/{row['observed_max_points']:.1f}；尚缺完整構面，不構成換倉建議",
                "blocking_gaps": "、".join(row.get("missing_components", [])),
                "execution_status": "只觀察，不執行",
            })
            if len(watches) >= max_items:
                break
        return watches or [_no_action(date, "目前較高觀察分股票均已持有；資料未完整前不換倉")]
    results = []
    available_sources = sorted(
        (row for row in eligible if str(row["ticker"]).zfill(4) in held_tickers),
        key=lambda row: (float(row["score"]), str(row["ticker"])),
    )
    if held_tickers and len(available_sources) != len(held_tickers):
        return [_no_action(date, "部分實際持股缺少完整免費核心分數，不以不完整比較推導換倉")]
    impaired_sources = [row for row in available_sources if _is_impaired(row)]
    if available_sources and not impaired_sources:
        return [_no_action(date, "現有持股尚未出現價格籌碼風險或題材催化轉弱；即使他股分數較高也不頻繁換倉")]
    used_sources: set[str] = set()
    for row in eligible:
        ticker = str(row["ticker"]).zfill(4)
        if ticker in held_tickers:
            continue
        if not _is_healthy_challenger(row):
            continue
        source = next((
            item for item in impaired_sources
            if str(item["ticker"]).zfill(4) not in used_sources
            and float(row["score"]) - float(item["score"]) >= MINIMUM_SCORE_ADVANTAGE
        ), None)
        if impaired_sources and source is None:
            continue
        source_ticker = str(source["ticker"]).zfill(4) if source else "待Ryan決定"
        if source:
            used_sources.add(source_ticker)
        has_target_overlay = row.get("target_upside") is not None
        overlay_gaps = row.get("overlay_missing_components", [])
        reason = row.get("reason", "公開資料核心排名較前；僅供換倉檢視")
        if source:
            reason += f"；相較{source_ticker}核心分數高{float(row['score']) - float(source['score']):.1f}分"
        confidence = (
            "HIGH" if ticker in target_tickers and has_target_overlay
            else "MEDIUM" if ticker in target_tickers or has_target_overlay
            else "LOW"
        )
        item_no = len(results) + 1
        if confidence == "HIGH":
            priority = f"P{item_no}"
            action = "REVIEW_SWITCH_IN"
            execution_status = "資料完整度較高；Ryan人工檢視，不視為成交"
        elif confidence == "MEDIUM":
            priority = f"REVIEW{item_no}"
            action = "REVIEW_SWITCH_IN"
            execution_status = "資料部分完整；Ryan人工檢視，不視為成交"
        else:
            priority = f"WATCH{item_no}"
            action = "OBSERVE_ONLY"
            execution_status = "只觀察，不執行"
            anonymous_upside = row.get("anonymous_target_upside")
            if anonymous_upside is not None:
                reason += (
                    f"；匿名市場目標價中位上行{float(anonymous_upside):+.1%}，僅供參考；"
                    "尚無具名三機構嚴格共識且非半年目標股，不構成換倉建議"
                )
            else:
                reason += "；尚無具名三機構嚴格共識且非半年目標股，不構成換倉建議"
        results.append({
            "date": date, "priority": priority, "action": action,
            "source_ticker": source_ticker, "target_ticker": ticker,
            "target_company": row.get("company", ""), "target_score": row["score"],
            "target_upside": row["target_upside"],
            "confidence": confidence,
            "reason": reason,
            "blocking_gaps": "、".join(overlay_gaps),
            "execution_status": execution_status,
        })
        if len(results) >= max_items:
            break
    return results or [_no_action(
        date,
        "持股雖有弱項，但沒有同時通過健康門檻且核心分數至少高10分的候選，今日不換倉",
    )]


def _no_action(date: str, reason: str) -> dict[str, Any]:
    return {
        "date": date, "priority": "NO_ACTION", "action": "HOLD", "source_ticker": "",
        "target_ticker": "", "target_company": "", "target_score": None, "target_upside": None,
        "confidence": "LOW", "reason": reason, "blocking_gaps": reason,
        "execution_status": "不執行；等待資料或新訊號",
    }
