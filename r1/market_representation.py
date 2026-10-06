from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from r1.theme_policy import load_themes
from rotation_radar.daily_risk_features import fetch_foreign_ownership


WEIGHTS = {"market_cap": 0.50, "average_turnover_20td": 0.30, "foreign_ownership": 0.20}


def build_market_representation(*, target: str, theme_path: str | Path,
                                market_path: str | Path, output_path: str | Path,
                                ownership_cache_path: str | Path,
                                ownership_rows: list[dict] | None = None) -> dict:
    themes = load_themes(theme_path)
    ticker_theme = {member.ticker: theme.theme_id for theme in themes for member in theme.members}
    market = json.loads(Path(market_path).read_text(encoding="utf-8"))
    if market.get("date") != target:
        raise ValueError(f"market snapshot date {market.get('date')} does not equal {target}")
    wanted = set(ticker_theme)
    cache_path = Path(ownership_cache_path)
    cached = _read_cache(cache_path, target)
    manifests = []
    if ownership_rows is None and cached is None:
        ownership_rows, manifests = fetch_foreign_ownership(date.fromisoformat(target), wanted)
        _write_cache(cache_path, target, ownership_rows, manifests)
    elif ownership_rows is None:
        ownership_rows = cached["rows"]
        manifests = cached.get("sources", [])
    ownership = {str(row["ticker"]).zfill(4): row for row in ownership_rows}
    market_rows = {str(row["ticker"]).zfill(4): row for row in market.get("rows", [])}
    rows, gaps = [], []
    for ticker in sorted(wanted):
        quote, owner = market_rows.get(ticker), ownership.get(ticker)
        missing = []
        close = quote.get("raw_close") if quote else None
        turnover = quote.get("avg_turnover_20d") if quote else None
        turnover_source_urls = []
        if turnover is None and quote and quote.get("market") == "TWSE":
            turnover, turnover_source_urls = _fetch_twse_average_turnover(ticker, target)
        shares = _number(owner.get("issued_shares")) if owner else None
        foreign_ratio = _number(owner.get("foreign_holding_ratio")) if owner else None
        for field, value in (("official_close", close), ("issued_shares", shares),
                             ("average_turnover_20td", turnover), ("foreign_ownership", foreign_ratio)):
            if value is None:
                missing.append(field)
        row = {
            "ticker": ticker, "theme_id": ticker_theme[ticker], "date": target,
            "official_close": close, "issued_shares": shares,
            "market_cap_twd": None if close is None or shares is None else close * shares,
            "average_turnover_20td_twd": turnover,
            "foreign_ownership_pct": foreign_ratio,
            "source_urls": sorted({value for value in [owner.get("source_url") if owner else None,
                                                        *turnover_source_urls]
                                   if value}),
            "status": "READY" if not missing else "DATA_MISSING", "missing_fields": missing,
        }
        rows.append(row)
        if missing:
            gaps.append({"ticker": ticker, "missing_fields": missing})
    _score_by_theme(rows)
    payload = {
        "model": "R1", "version": "r1-market-representation-v0.1", "status": "challenger_draft",
        "date": target, "requested_ticker_count": len(wanted),
        "actual_ticker_count": sum(row["market_representation"] is not None for row in rows),
        "rows": rows, "gaps": gaps, "ownership_sources": manifests,
        "future_data_violation_count": 0,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _score_by_theme(rows: list[dict]) -> None:
    raw_fields = {
        "market_cap": "market_cap_twd",
        "average_turnover_20td": "average_turnover_20td_twd",
        "foreign_ownership": "foreign_ownership_pct",
    }
    for theme in {row["theme_id"] for row in rows}:
        group = [row for row in rows if row["theme_id"] == theme]
        for row in group:
            scores = {}
            for score_field, raw_field in raw_fields.items():
                values = [item[raw_field] for item in group if item[raw_field] is not None]
                scores[score_field] = _percentile(row[raw_field], values)
            row["subscores"] = scores
            row["market_representation"] = None if any(value is None for value in scores.values()) else round(
                sum(scores[field] * WEIGHTS[field] for field in WEIGHTS), 4
            )


def _percentile(value: float | None, values: list[float]) -> float | None:
    if value is None or not values:
        return None
    if len(values) == 1:
        return 50.0
    below = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (below + 0.5 * (equal - 1)) / (len(values) - 1) * 100


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "").replace("%", ""))


def _fetch_twse_average_turnover(ticker: str, target: str) -> tuple[float | None, list[str]]:
    target_date = date.fromisoformat(target)
    year, month = target_date.year, target_date.month
    rows: dict[str, float] = {}
    urls = []
    for _ in range(3):
        url = ("https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&"
               f"date={year:04d}{month:02d}01&stockNo={ticker}")
        urls.append(url)
        request = Request(url, headers={"User-Agent": "R1-research/1.0"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
        for item in payload.get("data", []):
            if len(item) < 3:
                continue
            roc_year, item_month, item_day = [int(part) for part in str(item[0]).split("/")]
            iso = f"{roc_year + 1911:04d}-{item_month:02d}-{item_day:02d}"
            if iso <= target:
                rows[iso] = float(str(item[2]).replace(",", ""))
        if len(rows) >= 20:
            break
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    values = [value for _, value in sorted(rows.items())[-20:]]
    return (sum(values) / len(values), urls) if len(values) == 20 else (None, urls)


def _read_cache(path: Path, target: str) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if payload.get("date") == target else None


def _write_cache(path: Path, target: str, rows: list[dict], sources: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"version": "r1-official-ownership-cache-v0.1", "date": target,
                                     "rows": rows, "sources": sources}, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--market", default="data/r1/daily_market_latest.json")
    parser.add_argument("--output", default="data/r1/market_representation_latest.json")
    parser.add_argument("--ownership-cache", default="data/r1/official_ownership_latest.json")
    args = parser.parse_args()
    payload = build_market_representation(target=args.date, theme_path=args.themes, market_path=args.market,
                                          output_path=args.output, ownership_cache_path=args.ownership_cache)
    print(json.dumps({"requested": payload["requested_ticker_count"],
                      "actual": payload["actual_ticker_count"], "gaps": len(payload["gaps"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
