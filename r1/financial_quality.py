from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path

from r1.official_financial_snapshot import MOPS_XBRL_URL, fetch_text
from r1.theme_policy import load_themes


FACT = re.compile(
    r'<ix:nonFraction\b(?P<attrs>[^>]*\bname="(?P<name>[^"]+)"[^>]*)>(?P<value>[^<]+)</ix:nonFraction>',
    re.IGNORECASE,
)
ATTR = re.compile(r'([A-Za-z][\w:-]*)="([^"]*)"')
TAGS = {
    "revenue": ("Revenue", "OperatingRevenue"),
    "gross_profit": ("GrossProfitLossFromOperations",),
    "operating_income": ("ProfitLossFromOperatingActivities",),
    "net_income": ("ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
    "eps": ("BasicEarningsLossPerShare",),
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities",),
    "current_assets": ("CurrentAssets",),
    "current_liabilities": ("CurrentLiabilities",),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
}


def parse_financial_facts(page: str, *, report_year: int, quarter: int) -> dict:
    end = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}[quarter]
    current_duration = f"From{report_year}0101To{report_year}{end}"
    prior_duration = f"From{report_year - 1}0101To{report_year - 1}{end}"
    current_instant = f"AsOf{report_year}{end}"
    parsed: dict[tuple[str, str], float] = {}
    aliases = {alias: key for key, values in TAGS.items() for alias in values}
    for match in FACT.finditer(page):
        local_name = match.group("name").split(":")[-1]
        key = aliases.get(local_name)
        if key is None:
            continue
        attrs = {name: html.unescape(value) for name, value in ATTR.findall(match.group("attrs"))}
        context = attrs.get("contextRef", "")
        if context not in {current_duration, prior_duration, current_instant}:
            continue
        raw = html.unescape(match.group("value")).strip().replace(",", "")
        try:
            value = float(raw) * (10 ** int(attrs.get("scale", "0")))
        except ValueError:
            continue
        if attrs.get("sign") == "-":
            value = -value
        parsed.setdefault((key, context), value)
    result = {
        "current_context": current_duration,
        "prior_context": prior_duration,
        "balance_context": current_instant,
    }
    for key in ("revenue", "gross_profit", "operating_income", "net_income", "eps", "operating_cash_flow"):
        result[f"current_{key}"] = parsed.get((key, current_duration))
        result[f"prior_{key}"] = parsed.get((key, prior_duration))
    for key in ("current_assets", "current_liabilities", "total_assets", "total_liabilities"):
        result[key] = parsed.get((key, current_instant))
    return result


def build_financial_quality(*, as_of_date: str, theme_path: str | Path,
                            snapshot_path: str | Path, rubric_path: str | Path,
                            output_path: str | Path, facts_cache_path: str | Path,
                            pages: dict[str, str] | None = None) -> dict:
    themes = load_themes(theme_path)
    ticker_theme = {member.ticker: theme.theme_id for theme in themes for member in theme.members}
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    rubric = json.loads(Path(rubric_path).read_text(encoding="utf-8"))
    cache_path = Path(facts_cache_path)
    cache = _read_cache(cache_path)
    raw_rows, gaps = [], []
    for row in snapshot["rows"]:
        ticker = str(row["ticker"]).zfill(4)
        year = int(str(row["report_year_roc"])) + 1911
        quarter = int(str(row["quarter"]))
        cache_key = f"{ticker}:{year}:Q{quarter}"
        facts = cache.get(cache_key)
        url = MOPS_XBRL_URL.format(ticker=ticker, year=year, quarter=quarter)
        if facts is None:
            try:
                page = pages[ticker] if pages is not None else fetch_text(url)
                facts = parse_financial_facts(page, report_year=year, quarter=quarter)
                cache[cache_key] = facts
                _write_cache(cache_path, cache)
            except Exception as exc:  # network/source failure remains explicit
                gaps.append({"ticker": ticker, "reason": str(exc)})
                facts = {}
        metrics = _metrics(facts)
        absolute = _absolute_scores(metrics, rubric)
        missing = [key for key, value in absolute.items() if value is None]
        raw_rows.append({
            "ticker": ticker, "company": row["company"], "theme_id": ticker_theme[ticker],
            "report_year": year, "quarter": quarter, "source_url": url,
            "facts": facts, "metrics": metrics, "absolute_subscores": absolute,
            "status": "READY" if not missing else "DATA_MISSING", "missing_subscores": missing,
        })
    _apply_theme_percentiles(raw_rows, rubric)
    payload = {
        "model": "R1", "version": "r1-financial-quality-v0.1", "status": "challenger_draft",
        "as_of_date": as_of_date, "rubric_version": rubric["version"],
        "requested_ticker_count": len(raw_rows),
        "actual_ticker_count": sum(row["status"] == "READY" for row in raw_rows),
        "rows": raw_rows, "gaps": gaps,
        "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _metrics(f: dict) -> dict:
    revenue_yoy = _growth(f.get("current_revenue"), f.get("prior_revenue"))
    eps_yoy = _growth(f.get("current_eps"), f.get("prior_eps"))
    gross_margin = _ratio(f.get("current_gross_profit"), f.get("current_revenue"), 100)
    prior_gross_margin = _ratio(f.get("prior_gross_profit"), f.get("prior_revenue"), 100)
    op_margin = _ratio(f.get("current_operating_income"), f.get("current_revenue"), 100)
    prior_op_margin = _ratio(f.get("prior_operating_income"), f.get("prior_revenue"), 100)
    return {
        "revenue_yoy_pct": revenue_yoy,
        "gross_margin_pct": gross_margin,
        "gross_margin_change_pp": _difference(gross_margin, prior_gross_margin),
        "operating_margin_pct": op_margin,
        "operating_margin_change_pp": _difference(op_margin, prior_op_margin),
        "eps_yoy_pct": eps_yoy,
        "current_eps": f.get("current_eps"), "prior_eps": f.get("prior_eps"),
        "operating_cash_flow": f.get("current_operating_cash_flow"),
        "cash_conversion": _ratio(f.get("current_operating_cash_flow"), f.get("current_net_income"), 1),
        "current_ratio": _ratio(f.get("current_assets"), f.get("current_liabilities"), 1),
        "liabilities_to_assets_pct": _ratio(f.get("total_liabilities"), f.get("total_assets"), 100),
    }


def _absolute_scores(m: dict, rubric: dict) -> dict:
    a, rules = rubric["anchors"], rubric["rules"]
    margin_changes = [m.get("gross_margin_change_pp"), m.get("operating_margin_change_pp")]
    margin = None if any(value is None for value in margin_changes) else sum(
        _linear(value, *a["margin_change_pp"]) for value in margin_changes
    ) / 2
    if margin is not None and m.get("operating_margin_pct") is not None and m["operating_margin_pct"] < 0:
        margin = min(margin, rules["negative_current_operating_margin_cap"])
    eps = _eps_score(m, a["eps_yoy_pct"])
    if eps is not None and m.get("current_eps") is not None and m["current_eps"] < 0:
        eps = min(eps, rules["negative_current_eps_cap"])
    ocf = None
    if m.get("operating_cash_flow") is not None and m.get("cash_conversion") is not None:
        positive = 50.0 if m["operating_cash_flow"] > 0 else 0.0
        ocf = positive + 0.5 * _linear(m["cash_conversion"], *a["cash_conversion"])
        if m["operating_cash_flow"] < 0:
            ocf = min(ocf, rules["negative_current_operating_cash_flow_cap"])
    balance = None
    if m.get("current_ratio") is not None and m.get("liabilities_to_assets_pct") is not None:
        balance = (_linear(m["current_ratio"], *a["current_ratio"]) +
                   _linear(m["liabilities_to_assets_pct"], *a["liabilities_to_assets_pct"])) / 2
    return {
        "revenue_growth_quality": _maybe_linear(m.get("revenue_yoy_pct"), a["revenue_yoy_pct"]),
        "gross_and_operating_margin_quality": margin,
        "eps_growth_quality": eps,
        "operating_cash_flow_quality": ocf,
        "balance_sheet_safety": balance,
    }


def _apply_theme_percentiles(rows: list[dict], rubric: dict) -> None:
    fields = list(rubric["subweights"])
    for theme in {row["theme_id"] for row in rows}:
        group = [row for row in rows if row["theme_id"] == theme]
        for field in fields:
            values = [row["absolute_subscores"][field] for row in group
                      if row["absolute_subscores"][field] is not None]
            for row in group:
                value = row["absolute_subscores"][field]
                row.setdefault("theme_percentiles", {})[field] = _percentile(value, values)
        for row in group:
            combined = {}
            for field in fields:
                absolute = row["absolute_subscores"][field]
                percentile = row["theme_percentiles"][field]
                combined[field] = None if absolute is None or percentile is None else round(
                    rubric["absolute_weight"] * absolute + rubric["theme_percentile_weight"] * percentile, 4
                )
            row["combined_subscores"] = combined
            if any(value is None for value in combined.values()):
                row["financial_earnings_quality"] = None
                row["status"] = "DATA_MISSING"
            else:
                row["financial_earnings_quality"] = round(sum(
                    combined[field] * rubric["subweights"][field] for field in fields
                ), 4)


def _linear(value: float, low: float, high: float) -> float:
    if high == low:
        raise ValueError("invalid equal anchors")
    score = (value - low) / (high - low) * 100
    return max(0.0, min(100.0, score))


def _maybe_linear(value: float | None, anchors: list[float]) -> float | None:
    return None if value is None else _linear(value, *anchors)


def _growth(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior <= 0:
        return None
    return (current / prior - 1) * 100


def _eps_score(m: dict, anchors: list[float]) -> float | None:
    current, prior = m.get("current_eps"), m.get("prior_eps")
    if current is None or prior is None:
        return None
    if prior > 0:
        return _linear((current / prior - 1) * 100, *anchors)
    if current > 0:
        return 75.0
    return 0.0


def _ratio(numerator: float | None, denominator: float | None, scale: float) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * scale


def _difference(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else left - right


def _percentile(value: float | None, values: list[float]) -> float | None:
    if value is None or not values:
        return None
    if len(values) == 1:
        return 50.0
    below = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (below + 0.5 * (equal - 1)) / (len(values) - 1) * 100


def _read_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("facts", {})


def _write_cache(path: Path, facts: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"version": "r1-mops-financial-facts-cache-v0.1", "facts": facts},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--snapshot", default="data/r1/official_financial_latest.json")
    parser.add_argument("--rubric", default="config/r1_financial_quality_v01.json")
    parser.add_argument("--output", default="data/r1/financial_quality_latest.json")
    parser.add_argument("--cache", default="data/r1/mops_financial_facts_cache.json")
    args = parser.parse_args()
    payload = build_financial_quality(as_of_date=args.date, theme_path=args.themes,
                                      snapshot_path=args.snapshot, rubric_path=args.rubric,
                                      output_path=args.output, facts_cache_path=args.cache)
    print(json.dumps({"requested": payload["requested_ticker_count"],
                      "actual": payload["actual_ticker_count"], "gaps": len(payload["gaps"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
