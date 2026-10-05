from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

from r1.theme_policy import load_themes


ENDPOINTS = {
    "TWSE_income": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "TWSE_balance": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci",
    "TPEx_income": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci",
    "TPEx_balance": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_ci",
}

MOPS_XBRL_URL = (
    "https://mopsov.twse.com.tw/server-java/t164sb01"
    "?step=1&CO_ID={ticker}&SYEAR={year}&SSEASON={quarter}&REPORT_ID=C"
)

_OCF_FACT = re.compile(
    r'<ix:nonFraction\b(?P<attrs>[^>]*\bname="[^"]*:CashFlowsFromUsedInOperatingActivities"[^>]*)>'
    r'(?P<value>[^<]+)</ix:nonFraction>',
    re.IGNORECASE,
)
_ATTR = re.compile(r'([A-Za-z][\w:-]*)="([^"]*)"')


def fetch_json(url: str, attempts: int = 3) -> list[dict]:
    error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "R1-research/1.0"})
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except Exception as exc:  # pragma: no cover - network dependent
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"official financial endpoint failed after {attempts} attempts: {url}") from error


def fetch_text(url: str, attempts: int = 3) -> str:
    error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "R1-research/1.0"})
            with urlopen(request, timeout=45) as response:
                raw = response.read()
                return raw.decode("big5", errors="replace")
        except Exception as exc:  # pragma: no cover - network dependent
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"official MOPS XBRL page failed after {attempts} attempts: {url}") from error


def parse_operating_cash_flow(page: str, *, report_year: int, quarter: int) -> tuple[float, str]:
    """Return the current cumulative OCF fact and its XBRL context.

    MOPS renders inline XBRL values in thousands of TWD (scale=3).  The
    current-period fact is selected by the exact cumulative context end date,
    so the prior-year comparison column cannot be mistaken for current data.
    """
    end_month_day = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}[quarter]
    expected_end = f"{report_year}{end_month_day}"
    candidates: list[tuple[int, float, str]] = []
    for match in _OCF_FACT.finditer(page):
        attrs = {key: html.unescape(value) for key, value in _ATTR.findall(match.group("attrs"))}
        context = attrs.get("contextRef", "")
        if expected_end not in context:
            continue
        raw = html.unescape(match.group("value")).strip().replace(",", "")
        value = float(raw)
        if attrs.get("sign") == "-":
            value = -value
        scale = int(attrs.get("scale", "0"))
        value *= 10 ** scale
        # Prefer a context beginning on January 1 (year-to-date cash flow).
        priority = 1 if f"From{report_year}0101" in context else 0
        candidates.append((priority, value, context))
    if not candidates:
        raise ValueError(f"operating cash flow XBRL fact missing for {report_year} Q{quarter}")
    candidates.sort(reverse=True)
    _, value, context = candidates[0]
    return value, context


def fetch_operating_cash_flow(*, ticker: str, report_year: int, quarter: int) -> tuple[float, str, str]:
    url = MOPS_XBRL_URL.format(ticker=ticker, year=report_year, quarter=quarter)
    page = fetch_text(url)
    value, context = parse_operating_cash_flow(page, report_year=report_year, quarter=quarter)
    return value, context, url


def build_snapshot(*, as_of_date: str, theme_path: str | Path, output_path: str | Path,
                   payloads: dict[str, list[dict]] | None = None,
                   cash_flow_pages: dict[str, str] | None = None,
                   cash_flow_cache_path: str | Path | None = None) -> dict:
    themes = load_themes(theme_path)
    members = {member.ticker: member for theme in themes for member in theme.members}
    data = payloads or {name: fetch_json(url) for name, url in ENDPOINTS.items()}
    cash_cache_file = Path(cash_flow_cache_path) if cash_flow_cache_path else None
    cash_cache = _read_cash_cache(cash_cache_file)
    if payloads is None:
        _seed_cash_cache_from_snapshot(cash_cache, Path(output_path))
    indexes: dict[str, dict[str, dict]] = {}
    for name, rows in data.items():
        code_key = "公司代號" if name.startswith("TWSE") else "SecuritiesCompanyCode"
        indexes[name] = {str(row.get(code_key, "")).zfill(4): row for row in rows}
    result, gaps = [], []
    for ticker, member in sorted(members.items()):
        prefix = member.market
        income = indexes.get(f"{prefix}_income", {}).get(ticker)
        balance = indexes.get(f"{prefix}_balance", {}).get(ticker)
        missing = [name for name, row in (("income_statement", income), ("balance_sheet", balance)) if row is None]
        date_key = "出表日期" if prefix == "TWSE" else "Date"
        year_key = "年度" if prefix == "TWSE" else "Year"
        quarter_key = "季別" if prefix == "TWSE" else "Season"
        report_year_roc = (income or balance or {}).get(year_key)
        quarter_value = (income or balance or {}).get(quarter_key)
        operating_cash_flow = None
        cash_context = None
        cash_url = None
        if not missing and report_year_roc and quarter_value:
            try:
                report_year = int(str(report_year_roc)) + 1911
                quarter = int(str(quarter_value))
                cash_url = MOPS_XBRL_URL.format(ticker=ticker, year=report_year, quarter=quarter)
                cache_key = f"{ticker}:{report_year}:Q{quarter}"
                cached = cash_cache.get(cache_key)
                if cached is not None:
                    operating_cash_flow = float(cached["operating_cash_flow"])
                    cash_context = str(cached["context"])
                    cash_url = str(cached["source_url"])
                elif cash_flow_pages is not None:
                    page = cash_flow_pages[ticker]
                    operating_cash_flow, cash_context = parse_operating_cash_flow(
                        page, report_year=report_year, quarter=quarter
                    )
                elif payloads is None:
                    operating_cash_flow, cash_context, cash_url = fetch_operating_cash_flow(
                        ticker=ticker, report_year=report_year, quarter=quarter
                    )
                    cash_cache[cache_key] = {
                        "ticker": ticker, "report_year": report_year, "quarter": quarter,
                        "operating_cash_flow": operating_cash_flow, "context": cash_context,
                        "source_url": cash_url,
                    }
                    _write_cash_cache(cash_cache_file, cash_cache)
                else:
                    missing.append("cash_flow_statement")
            except (KeyError, RuntimeError, ValueError) as exc:
                missing.append("cash_flow_statement")
                gaps.append({"ticker": ticker, "missing": ["cash_flow_statement"], "reason": str(exc)})
        if missing and not any(gap["ticker"] == ticker for gap in gaps):
            gaps.append({"ticker": ticker, "missing": missing})
        status = "READY" if not missing and operating_cash_flow is not None else "DATA_MISSING"
        result.append({
            "ticker": ticker, "company": member.company, "market": member.market,
            "report_year_roc": report_year_roc,
            "quarter": quarter_value,
            "source_date_roc": (income or balance or {}).get(date_key),
            "revenue": _number((income or {}).get("營業收入")),
            "gross_profit": _number((income or {}).get("營業毛利（毛損）淨額") or (income or {}).get("營業毛利（毛損）")),
            "operating_income": _number((income or {}).get("營業利益（損失）")),
            "net_income": _number((income or {}).get("本期淨利（淨損）")),
            "eps": _number((income or {}).get("基本每股盈餘（元）")),
            "current_assets": _number((balance or {}).get("流動資產")),
            "current_liabilities": _number((balance or {}).get("流動負債")),
            "total_assets": _number((balance or {}).get("資產總計")),
            "total_liabilities": _number((balance or {}).get("負債總計")),
            "total_equity": _number((balance or {}).get("權益總計")),
            "operating_cash_flow": operating_cash_flow,
            "operating_cash_flow_context": cash_context,
            "status": status,
            "source_urls": [ENDPOINTS.get(f"{prefix}_income"), ENDPOINTS.get(f"{prefix}_balance"), cash_url],
        })
    payload = {
        "model": "R1", "version": "r1-official-financial-snapshot-v0.2",
        "as_of_date": as_of_date, "requested_ticker_count": len(members),
        "actual_ticker_count": sum(row["status"] == "READY" for row in result),
        "rows": result, "gaps": gaps,
        "known_missing_field": None if not gaps else "see_gaps",
        "future_data_violation_count": 0,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _read_cash_cache(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("facts", {}))


def _seed_cash_cache_from_snapshot(cache: dict[str, dict], path: Path) -> None:
    if not path.exists():
        return
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    except (OSError, json.JSONDecodeError):
        return
    for row in rows:
        if row.get("operating_cash_flow") is None or not row.get("operating_cash_flow_context"):
            continue
        year = int(str(row["report_year_roc"])) + 1911
        quarter = int(str(row["quarter"]))
        key = f"{str(row['ticker']).zfill(4)}:{year}:Q{quarter}"
        urls = [url for url in row.get("source_urls", []) if url]
        cache[key] = {
            "ticker": str(row["ticker"]).zfill(4), "report_year": year, "quarter": quarter,
            "operating_cash_flow": float(row["operating_cash_flow"]),
            "context": str(row["operating_cash_flow_context"]),
            "source_url": urls[-1] if urls else MOPS_XBRL_URL.format(
                ticker=str(row["ticker"]).zfill(4), year=year, quarter=quarter
            ),
        }


def _write_cash_cache(path: Path | None, facts: dict[str, dict]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"version": "r1-mops-cash-flow-cache-v0.1", "facts": facts},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--output", default="data/r1/official_financial_latest.json")
    parser.add_argument("--cash-flow-cache", default="data/r1/mops_cash_flow_cache.json")
    args = parser.parse_args()
    payload = build_snapshot(as_of_date=args.date, theme_path=args.themes, output_path=args.output,
                             cash_flow_cache_path=args.cash_flow_cache)
    print(json.dumps({"requested": payload["requested_ticker_count"], "actual": payload["actual_ticker_count"],
                      "gaps": len(payload["gaps"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
