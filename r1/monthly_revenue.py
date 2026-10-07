from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

from r1.theme_policy import load_themes


BASE_URL = "https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{month}_{company_type}.html"
MARKETS = {"sii": "TWSE", "otc": "TPEx"}


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif self._row is not None and tag.lower() in {"td", "th"}:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_text("".join(self._cell)))
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def conservative_available_date(period: str) -> date:
    year, month = map(int, period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    result = date(year, month, 10)
    while result.weekday() >= 5:
        result = date.fromordinal(result.toordinal() + 1)
    return result


def released_periods(as_of_date: str, count: int = 3) -> list[str]:
    asof = date.fromisoformat(as_of_date)
    year, month = asof.year, asof.month
    values: list[str] = []
    while len(values) < count:
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        period = f"{year:04d}-{month:02d}"
        if conservative_available_date(period) <= asof:
            values.append(period)
    return sorted(values)


def parse_html(html: str, *, period: str, market: str, source_url: str) -> list[dict]:
    parser = _TableParser()
    parser.feed(html)
    available = conservative_available_date(period).isoformat()
    rows = []
    for cells in parser.rows:
        if len(cells) < 7 or not re.fullmatch(r"\d{4}", cells[0].strip()):
            continue
        try:
            revenue = int(float(cells[2].replace(",", ""))) * 1000
            prior_year = int(float(cells[5].replace(",", ""))) * 1000
            yoy = float(cells[6].replace(",", "")) / 100
        except ValueError:
            continue
        rows.append({
            "ticker": cells[0].strip(), "company": cells[1].strip(), "market": market,
            "revenue_year_month": period, "revenue_twd": revenue,
            "prior_year_revenue_twd": prior_year, "yoy": yoy,
            "available_date": available, "source_url": source_url,
            "source_type": "MOPS_MONTHLY_REVENUE_STATIC_HTML",
        })
    return rows


def acceleration_state(rows: list[dict]) -> tuple[str, list[str]]:
    ordered = sorted(rows, key=lambda row: row["revenue_year_month"])
    if len(ordered) != 3 or any(row.get("yoy") is None for row in ordered):
        return "DATA_MISSING", ["THREE_RELEASED_MONTHS_NOT_COMPLETE"]
    yoy = [float(row["yoy"]) for row in ordered]
    if yoy[0] < yoy[1] < yoy[2] and yoy[2] > 0:
        return "ACCELERATING", ["YOY_RISING_THREE_MONTHS", "LATEST_YOY_POSITIVE"]
    return "NOT_ACCELERATING", ["THREE_MONTH_YOY_RULE_NOT_MET"]


def _fetch(url: str, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            text = response.content.decode("big5", errors="replace")
            if "營業收入統計表" not in text:
                raise ValueError("not_monthly_revenue_html")
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"MOPS fetch failed: {url}: {last_error}")


def materialize(*, as_of_date: str, theme_path: str | Path, output_path: str | Path) -> dict:
    tickers = {member.ticker for theme in load_themes(theme_path) for member in theme.members}
    periods = released_periods(as_of_date)
    collected: dict[tuple[str, str], dict] = {}
    attempts = []
    for period in periods:
        year, month = map(int, period.split("-"))
        for market_code, market in MARKETS.items():
            for company_type in (0, 1):
                url = BASE_URL.format(market=market_code, roc_year=year - 1911,
                                      month=month, company_type=company_type)
                try:
                    parsed = parse_html(_fetch(url), period=period, market=market, source_url=url)
                    for row in parsed:
                        if row["ticker"] in tickers:
                            collected[(row["ticker"], period)] = row
                    attempts.append({"period": period, "market": market, "company_type": company_type,
                                     "status": "OK", "row_count": len(parsed), "source_url": url})
                except RuntimeError as exc:
                    attempts.append({"period": period, "market": market, "company_type": company_type,
                                     "status": "FAILED", "row_count": 0, "source_url": url,
                                     "error": str(exc)})
    rows = []
    for ticker in sorted(tickers):
        monthly = [collected[(ticker, period)] for period in periods if (ticker, period) in collected]
        state, reasons = acceleration_state(monthly)
        rows.append({"ticker": ticker, "state": state, "periods": periods,
                     "observations": monthly, "reasons": reasons})
    payload = {
        "model": "R1", "date": as_of_date, "periods": periods,
        "rows": rows, "coverage": {"actual": sum(row["state"] != "DATA_MISSING" for row in rows),
                                      "requested": len(tickers)},
        "attempts": attempts,
        "future_data_violation_count": sum(
            date.fromisoformat(obs["available_date"]) > date.fromisoformat(as_of_date)
            for row in rows for obs in row["observations"]
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize official R1 monthly-revenue acceleration evidence.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--output", default="data/r1/monthly_revenue/latest.json")
    args = parser.parse_args()
    payload = materialize(as_of_date=args.date, theme_path=args.themes, output_path=args.output)
    print(json.dumps({"date": payload["date"], "periods": payload["periods"],
                      "coverage": payload["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
