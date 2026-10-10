from __future__ import annotations

from typing import Any


def build_recommendations(*, date: str, candidates: list[dict[str, Any]], held_tickers: set[str],
                          target_tickers: set[str], max_items: int = 3) -> list[dict[str, Any]]:
    """Produce advisory-only ranked changes; incomplete inputs resolve to NO_ACTION."""
    eligible = [row for row in candidates if row.get("score") is not None and row.get("target_upside") is not None]
    eligible.sort(key=lambda row: (-float(row["score"]), -float(row["target_upside"]), str(row["ticker"])))
    if not eligible:
        return [_no_action(date, "目標價共識或必要評分資料不足，不以NA推導交易")]
    results = []
    for row in eligible:
        ticker = str(row["ticker"]).zfill(4)
        if ticker in held_tickers:
            continue
        results.append({
            "date": date, "priority": f"P{len(results) + 1}", "action": "REVIEW_SWITCH_IN",
            "source_ticker": row.get("source_ticker", "待Ryan決定"), "target_ticker": ticker,
            "target_company": row.get("company", ""), "target_score": row["score"],
            "target_upside": row["target_upside"],
            "confidence": "HIGH" if ticker in target_tickers else "MEDIUM",
            "reason": row.get("reason", "綜合排名較前；僅供換倉檢視"),
            "blocking_gaps": "", "execution_status": "建議，不視為成交",
        })
        if len(results) >= max_items:
            break
    return results or [_no_action(date, "高分候選已在持股中，今日不需要操作")]


def _no_action(date: str, reason: str) -> dict[str, Any]:
    return {
        "date": date, "priority": "NO_ACTION", "action": "HOLD", "source_ticker": "",
        "target_ticker": "", "target_company": "", "target_score": None, "target_upside": None,
        "confidence": "LOW", "reason": reason, "blocking_gaps": reason,
        "execution_status": "不執行；等待資料或新訊號",
    }
