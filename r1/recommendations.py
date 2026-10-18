from __future__ import annotations

from typing import Any


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
    used_sources: set[str] = set()
    for row in eligible:
        ticker = str(row["ticker"]).zfill(4)
        if ticker in held_tickers:
            continue
        source = next((
            item for item in available_sources
            if str(item["ticker"]).zfill(4) not in used_sources
            and float(item["score"]) < float(row["score"])
        ), None)
        if available_sources and source is None:
            continue
        source_ticker = str(source["ticker"]).zfill(4) if source else "待Ryan決定"
        if source:
            used_sources.add(source_ticker)
        has_target_overlay = row.get("target_upside") is not None
        overlay_gaps = row.get("overlay_missing_components", [])
        reason = row.get("reason", "公開資料核心排名較前；僅供換倉檢視")
        if source:
            reason += f"；相較{source_ticker}核心分數高{float(row['score']) - float(source['score']):.1f}分"
        results.append({
            "date": date, "priority": f"P{len(results) + 1}", "action": "REVIEW_SWITCH_IN",
            "source_ticker": source_ticker, "target_ticker": ticker,
            "target_company": row.get("company", ""), "target_score": row["score"],
            "target_upside": row["target_upside"],
            "confidence": (
                "HIGH" if ticker in target_tickers and has_target_overlay
                else "MEDIUM" if ticker in target_tickers or has_target_overlay
                else "LOW"
            ),
            "reason": reason,
            "blocking_gaps": "、".join(overlay_gaps),
            "execution_status": "建議檢視，不視為成交",
        })
        if len(results) >= max_items:
            break
    return results or [_no_action(date, "沒有未持有候選的核心分數高於可比較持股，今日不需要操作")]


def _no_action(date: str, reason: str) -> dict[str, Any]:
    return {
        "date": date, "priority": "NO_ACTION", "action": "HOLD", "source_ticker": "",
        "target_ticker": "", "target_company": "", "target_score": None, "target_upside": None,
        "confidence": "LOW", "reason": reason, "blocking_gaps": reason,
        "execution_status": "不執行；等待資料或新訊號",
    }
