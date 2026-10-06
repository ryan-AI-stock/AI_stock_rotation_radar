from __future__ import annotations

import argparse
import json
from pathlib import Path

from r1.theme_policy import LEADER_FIELDS, PRIORITY_FIELDS, leader_score, load_themes
from r1.theme_score_rubric import load_and_validate


ALL_FIELDS = (*LEADER_FIELDS, *PRIORITY_FIELDS)
EVIDENCE_FIELDS = ("source_url", "source_date", "available_at", "source_family", "evidence_note")
MULTISOURCE_QUALITATIVE_FIELDS = {
    "bottleneck_directness", "industry_technology_position",
    "ai_revenue_realization", "demand_order_catalyst",
}


def materialize(*, as_of_date: str, theme_path: str | Path,
                source_path: str | Path, output_path: str | Path,
                rubric_path: str | Path = "config/r1_v03_score_rubric.json",
                financial_quality_path: str | Path | None = None,
                market_representation_path: str | Path | None = None) -> dict:
    rubric = load_and_validate(rubric_path)
    themes = load_themes(theme_path)
    members = {
        member.ticker: (member.company, theme.theme_id)
        for theme in themes for member in theme.members
    }
    source_file = Path(source_path)
    source_payload = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    source_rows = {
        str(row.get("ticker", "")).zfill(4): row for row in source_payload.get("rows", [])
    }
    financial_rows = _load_financial_quality(financial_quality_path, as_of_date)
    market_rows = _load_scored_input(
        market_representation_path, as_of_date, score_field="market_representation",
        date_field="date", source_family="TWSE_TPEX_OFFICIAL_MARKET_AND_OWNERSHIP",
    )
    extras = sorted(set(source_rows) - set(members))
    if extras:
        raise ValueError(f"theme leader input contains out-of-universe tickers: {extras}")

    rows = []
    rejected = []
    for ticker, (company, theme_id) in members.items():
        source = source_rows.get(ticker, {})
        evidence = dict(source.get("evidence", {})) if isinstance(source.get("evidence"), dict) else {}
        financial = financial_rows.get(ticker)
        if financial is not None and source.get("financial_earnings_quality") is None:
            source = dict(source)
            source["financial_earnings_quality"] = financial["financial_earnings_quality"]
            evidence["financial_earnings_quality"] = financial["evidence"]
        market_score = market_rows.get(ticker)
        if market_score is not None and source.get("market_representation") is None:
            source = dict(source)
            source["market_representation"] = market_score["market_representation"]
            evidence["market_representation"] = market_score["evidence"]
        row = {
            "ticker": ticker, "company": company, "theme_id": theme_id,
            "as_of_date": as_of_date, "evidence": evidence,
        }
        for field in ALL_FIELDS:
            value = source.get(field)
            if value is not None:
                value = float(value)
                if not 0 <= value <= 100:
                    raise ValueError(f"{ticker} {field} score must be within 0..100")
                proof = evidence.get(field)
                sources = _validate_evidence(ticker=ticker, field=field, proof=proof, as_of_date=as_of_date)
                if field in MULTISOURCE_QUALITATIVE_FIELDS and value >= 75:
                    families = {str(item["source_family"]) for item in sources}
                    if len(families) < int(rubric["principles"][
                        "minimum_independent_source_families_for_qualitative_75_plus"
                    ]):
                        raise ValueError(f"{ticker} {field} score 75+ requires independent source families")
            row[field] = value
        structural = leader_score(row)
        if structural is not None:
            row["structural_leader"] = structural
        missing_fields = [field for field in ALL_FIELDS if row.get(field) is None]
        row["status"] = "READY" if not missing_fields else "DATA_MISSING"
        row["missing_fields"] = missing_fields
        if missing_fields:
            rejected.append({"ticker": ticker, "missing_fields": missing_fields})
        rows.append(row)

    payload = {
        "model": "R1", "version": "r1-theme-leader-input-v0.2", "as_of_date": as_of_date,
        "score_rubric_version": rubric["version"],
        "requested_ticker_count": len(members), "actual_ticker_count": len(rows),
        "complete_ticker_count": sum(row["status"] == "READY" for row in rows),
        "rows": rows, "data_gaps": rejected, "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": True,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _load_financial_quality(path: str | Path | None, as_of_date: str) -> dict[str, dict]:
    if path is None:
        return {}
    file = Path(path)
    if not file.exists():
        return {}
    payload = json.loads(file.read_text(encoding="utf-8"))
    if str(payload.get("as_of_date", "")) > as_of_date:
        raise ValueError("financial quality snapshot uses future data")
    rows = {}
    for row in payload.get("rows", []):
        score = row.get("financial_earnings_quality")
        if row.get("status") != "READY" or score is None:
            continue
        ticker = str(row["ticker"]).zfill(4)
        rows[ticker] = {
            "financial_earnings_quality": score,
            "evidence": {
                "source_url": row["source_url"],
                "source_date": payload["as_of_date"],
                "available_at": payload["as_of_date"],
                "source_family": "MOPS_XBRL_OFFICIAL",
                "evidence_note": (
                    f"{payload['rubric_version']}；本期與去年同期財報、營業現金流及資產負債比率；"
                    "challenger草案，未啟用交易。"
                ),
            },
        }
    return rows


def _load_scored_input(path: str | Path | None, as_of_date: str, *, score_field: str,
                       date_field: str, source_family: str) -> dict[str, dict]:
    if path is None or not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source_date = str(payload.get(date_field, ""))
    if source_date > as_of_date:
        raise ValueError(f"{score_field} snapshot uses future data")
    result = {}
    for row in payload.get("rows", []):
        score = row.get(score_field)
        if score is None:
            continue
        urls = row.get("source_urls", [])
        result[str(row["ticker"]).zfill(4)] = {
            score_field: score,
            "evidence": {
                "source_url": urls[0] if urls else "https://www.twse.com.tw/",
                "source_date": source_date, "available_at": source_date,
                "source_family": source_family,
                "evidence_note": "同題材內市值、20TD平均成交金額與官方外資持股比例百分位。",
            },
        }
    return result


def _validate_evidence(*, ticker: str, field: str, proof: object, as_of_date: str) -> list[dict]:
    if not isinstance(proof, dict):
        raise ValueError(f"{ticker} {field} missing evidence fields: {list(EVIDENCE_FIELDS)}")
    sources = proof.get("sources")
    source_rows = sources if isinstance(sources, list) and sources else [proof]
    for source in source_rows:
        missing = [name for name in EVIDENCE_FIELDS if not isinstance(source, dict) or not source.get(name)]
        if missing:
            raise ValueError(f"{ticker} {field} missing evidence fields: {missing}")
        if str(source["available_at"]) > as_of_date:
            raise ValueError(f"{ticker} {field} uses future evidence")
    return source_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize evidence-gated R1 theme leader inputs.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--source", default="data/r1/theme_leader_inputs/source.json")
    parser.add_argument("--output", default="data/r1/theme_leader_inputs/latest.json")
    parser.add_argument("--rubric", default="config/r1_v03_score_rubric.json")
    parser.add_argument("--financial-quality", default="data/r1/financial_quality_latest.json")
    parser.add_argument("--market-representation", default="data/r1/market_representation_latest.json")
    args = parser.parse_args()
    payload = materialize(
        as_of_date=args.date, theme_path=args.themes,
        source_path=args.source, output_path=args.output, rubric_path=args.rubric,
        financial_quality_path=args.financial_quality,
        market_representation_path=args.market_representation,
    )
    print(json.dumps({
        "requested_ticker_count": payload["requested_ticker_count"],
        "complete_ticker_count": payload["complete_ticker_count"],
        "gap_count": len(payload["data_gaps"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
