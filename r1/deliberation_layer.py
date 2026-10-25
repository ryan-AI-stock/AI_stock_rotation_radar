from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_not_future(payload: dict[str, Any], as_of_date: str, label: str,
                        *, exact: bool = False) -> None:
    source_date = payload.get("date") or payload.get("as_of_date")
    if not source_date:
        raise ValueError(f"R1 deliberation {label} has no source date")
    if source_date > as_of_date:
        raise ValueError(f"R1 deliberation {label} uses future data: {source_date}")
    if exact and source_date != as_of_date:
        raise ValueError(f"R1 deliberation {label} date mismatch: {source_date} != {as_of_date}")


def _previous_rows(history_root: str | Path, as_of_date: str) -> dict[str, dict[str, Any]]:
    files = sorted(
        path for path in Path(history_root).glob("????-??-??.json")
        if path.stem < as_of_date
    )
    if not files:
        return {}
    payload = _load(files[-1])
    return {str(row["ticker"]).zfill(4): row for row in payload.get("rows", [])}


def build_deliberation(*, as_of_date: str, context_path: str | Path,
                       score_path: str | Path, account_path: str | Path,
                       themes_path: str | Path,
                       history_root: str | Path = "data/r1/deliberation/history") -> dict[str, Any]:
    """Build auditable competing hypotheses; never emit or execute a trade."""
    context = _load(context_path)
    scores = _load(score_path)
    account = _load(account_path)
    themes = _load(themes_path)
    _require_not_future(context, as_of_date, "context", exact=True)
    _require_not_future(scores, as_of_date, "score", exact=True)
    _require_not_future(account, as_of_date, "account", exact=True)
    if themes.get("as_of_date") and themes["as_of_date"] > as_of_date:
        raise ValueError("R1 deliberation themes use future membership")

    held = {str(row["ticker"]).zfill(4) for row in account.get("positions", [])}
    targets = {str(value).zfill(4) for value in themes.get("target_portfolio_6m", [])}
    score_by_ticker = {
        str(row.get("ticker", "")).zfill(4): row for row in scores.get("rows", [])
    }
    previous = _previous_rows(history_root, as_of_date)
    rows: list[dict[str, Any]] = []
    for item in context.get("rows", []):
        ticker = str(item["ticker"]).zfill(4)
        state = item.get("context_state", "NO_CONTEXT_CHANGE")
        monthly = item.get("monthly_revenue_state")
        broad = bool(item.get("broad_selloff"))
        weak = bool(item.get("price_weak"))
        positive_confirmed = state == "POSITIVE_FUNDAMENTAL_CONFIRMED"
        thesis_confirmed = state == "THESIS_RISK_CONFIRMED"
        official_risk = bool(item.get("official_negative_event_types"))

        hypotheses = [
            {
                "id": "SYSTEMIC_SELLING",
                "support": "STRONG" if broad and weak else "WEAK",
                "evidence": ["候選池與加權指數同步急跌"] if broad and weak else [],
            },
            {
                "id": "COMPANY_THESIS_DAMAGE",
                "support": "STRONG" if thesis_confirmed else "MEDIUM" if official_risk else "WEAK",
                "evidence": list(item.get("official_negative_event_types", [])),
            },
            {
                "id": "PRICE_FUNDAMENTAL_DISLOCATION",
                "support": (
                    "STRONG" if broad and weak and monthly == "ACCELERATING" and not official_risk
                    else "MEDIUM" if broad and weak and not official_risk
                    else "WEAK"
                ),
                "evidence": (["市場急跌", "月營收加速"] if broad and weak and monthly == "ACCELERATING"
                             else ["市場急跌但基本面尚未確認"] if broad and weak else []),
            },
            {
                "id": "POSITIVE_CATALYST_CONFIRMED",
                "support": "STRONG" if positive_confirmed else "MEDIUM" if item.get("positive_event_count", 0) else "WEAK",
                "evidence": [f"正向事件{item.get('positive_event_count', 0)}項"],
            },
        ]
        contradictions = []
        if broad and weak:
            contradictions.append("全市場急跌使個股價格訊號無法單獨證明公司惡化")
        if official_risk and item.get("positive_event_count", 0):
            contradictions.append("官方負面與正向催化並存，須等待後續營收或財報確認")

        if thesis_confirmed:
            conclusion, confidence = "PRIORITIZE_REPLACEMENT_REVIEW", "HIGH"
            rationale = "公司投資邏輯風險已有多來源確認；僅提高人工換出檢視優先度"
        elif official_risk:
            conclusion, confidence = "HOLD_PENDING_CONFIRMATION", "MEDIUM"
            rationale = "已有官方負面，但缺第二項獨立確認，不因單一證據賣出"
        elif broad and weak and monthly == "ACCELERATING":
            conclusion, confidence = "WATCH_POTENTIAL_DISLOCATION", "MEDIUM"
            rationale = "價格隨市場下跌但月營收加速，可列錯殺候選；尚未形成買進指令"
        elif broad and weak:
            conclusion, confidence = "HOLD_NO_COMPANY_CONCLUSION", "LOW"
            rationale = "較像系統性賣壓，且基本面未形成正向或負向確認"
        elif positive_confirmed:
            conclusion, confidence = "REVIEW_ACCUMULATION_CANDIDATE", "MEDIUM"
            rationale = "正向事件已獲基本面確認，仍需估值與風險條件配合"
        else:
            conclusion, confidence = "KEEP_EXISTING_PLAN", "LOW"
            rationale = "沒有足夠新證據推翻原計畫"

        prior = previous.get(ticker, {})
        prior_conclusion = prior.get("conclusion")
        rows.append({
            "ticker": ticker,
            "company": item.get("company", ""),
            "is_held": ticker in held,
            "is_target": ticker in targets,
            "score": score_by_ticker.get(ticker, {}).get("v05_total_score"),
            "hypotheses": hypotheses,
            "contradictions": contradictions,
            "conclusion": conclusion,
            "confidence": confidence,
            "rationale": rationale,
            "previous_conclusion": prior_conclusion,
            "judgement_changed": bool(prior_conclusion and prior_conclusion != conclusion),
            "evidence_urls": item.get("evidence_urls", []),
        })

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["conclusion"]] = counts.get(row["conclusion"], 0) + 1
    return {
        "model": "R1",
        "layer": "bounded_deliberation_v0.1",
        "date": as_of_date,
        "status": "READY",
        "rows": rows,
        "conclusion_counts": counts,
        "reasoning_contract": [
            "同時保留互斥假說，不把價格下跌直接等同公司惡化",
            "支持證據、反證、資料缺口與前次判斷均需可追溯",
            "消息不能單獨觸發買賣，證據不足維持未知或原計畫",
            "輸出只供Ryan判斷，不自動下單",
        ],
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R1 bounded deliberation layer.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--context", default="data/r1/context_event_latest.json")
    parser.add_argument("--score", default="data/r1/v05/latest.json")
    parser.add_argument("--account", default="data/r1/actual_account_state.json")
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--history-root", default="data/r1/deliberation/history")
    parser.add_argument("--output", default="data/r1/deliberation/latest.json")
    args = parser.parse_args()
    payload = build_deliberation(
        as_of_date=args.date, context_path=args.context, score_path=args.score,
        account_path=args.account, themes_path=args.themes, history_root=args.history_root,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = Path(args.history_root) / f"{args.date}.json"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"date": args.date, "rows": len(payload["rows"]), "status": payload["status"]}))


if __name__ == "__main__":
    main()
