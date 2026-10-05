from __future__ import annotations

import argparse
import json
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


def build_snapshot(*, as_of_date: str, theme_path: str | Path, output_path: str | Path,
                   payloads: dict[str, list[dict]] | None = None) -> dict:
    themes = load_themes(theme_path)
    members = {member.ticker: member for theme in themes for member in theme.members}
    data = payloads or {name: fetch_json(url) for name, url in ENDPOINTS.items()}
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
        if missing:
            gaps.append({"ticker": ticker, "missing": missing})
        date_key = "出表日期" if prefix == "TWSE" else "Date"
        year_key = "年度" if prefix == "TWSE" else "Year"
        quarter_key = "季別" if prefix == "TWSE" else "Season"
        result.append({
            "ticker": ticker, "company": member.company, "market": member.market,
            "report_year_roc": (income or balance or {}).get(year_key),
            "quarter": (income or balance or {}).get(quarter_key),
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
            "operating_cash_flow": None,
            "status": "READY_EXCEPT_CASH_FLOW" if not missing else "DATA_MISSING",
            "source_urls": [ENDPOINTS.get(f"{prefix}_income"), ENDPOINTS.get(f"{prefix}_balance")],
        })
    payload = {
        "model": "R1", "version": "r1-official-financial-snapshot-v0.1",
        "as_of_date": as_of_date, "requested_ticker_count": len(members),
        "actual_ticker_count": sum(row["status"] != "DATA_MISSING" for row in result),
        "rows": result, "gaps": gaps,
        "known_missing_field": "operating_cash_flow",
        "future_data_violation_count": 0,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--themes", default="config/r1_v02_themes.json")
    parser.add_argument("--output", default="data/r1/official_financial_latest.json")
    args = parser.parse_args()
    payload = build_snapshot(as_of_date=args.date, theme_path=args.themes, output_path=args.output)
    print(json.dumps({"requested": payload["requested_ticker_count"], "actual": payload["actual_ticker_count"],
                      "gaps": len(payload["gaps"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
