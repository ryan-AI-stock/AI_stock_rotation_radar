"""Build a research-only daily theme/institutional panel from official raw files."""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/formal_sources/v4d_theme_institutional_20150518_20260722/raw"
OUT = ROOT / "data/formal_sources/v4d_theme_institutional_20150518_20260722"


def number(value: object) -> int:
    text = str(value or "").replace(",", "").replace("+", "").strip()
    if not text or text in {"--", "---", "-"}:
        return 0
    return int(float(text))


def table_with(payload: dict, required: tuple[str, ...]) -> dict:
    for table in payload.get("tables", []):
        fields = [str(x) for x in table.get("fields", [])]
        if all(any(token in field for field in fields) for token in required) and table.get("data"):
            return table
    return {}


def turnover_rows(family: str, path: Path) -> list[tuple[str, str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if family == "twse_turnover":
        table = table_with(payload, ("證券代號", "成交金額"))
    else:
        table = table_with(payload, ("代號", "成交金額"))
    fields = [str(x) for x in table.get("fields", [])]
    symbol_i = next((i for i, x in enumerate(fields) if "證券代號" in x or x == "代號"), 0)
    value_i = next(i for i, x in enumerate(fields) if "成交金額" in x)
    return [(str(r[symbol_i]).strip(), path.stem, number(r[value_i])) for r in table.get("data", [])]


def institutional_rows(family: str, path: Path) -> list[tuple[str, str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if family == "twse_institutional":
        fields = [str(x) for x in payload.get("fields", [])]
        data = payload.get("data", [])
    else:
        table = table_with(payload, ("代號", "三大法人買賣超"))
        fields = [str(x) for x in table.get("fields", [])]
        data = table.get("data", [])
    symbol_i = next((i for i, x in enumerate(fields) if "證券代號" in x or x == "代號"), 0)
    total_i = next(i for i, x in enumerate(fields) if "三大法人買賣超" in x)
    return [(str(r[symbol_i]).strip(), path.stem, number(r[total_i])) for r in data]


def write_gzip(path: Path, fields: list[str], rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    membership: dict[str, list[str]] = defaultdict(list)
    with (ROOT / "data/theme_map.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            membership[row["symbol"].strip()].append(row["theme"].strip())

    stock_turnover: list[dict] = []
    theme_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    institutional: list[dict] = []
    parse_errors: list[dict] = []
    for family in ("twse_turnover", "tpex_turnover"):
        for path in sorted((SOURCE / family).glob("*.json")):
            if path.name.endswith(".meta.json") or path.name.endswith(".error.json"):
                continue
            try:
                for symbol, ymd, value in turnover_rows(family, path):
                    date_text = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
                    stock_turnover.append({"date": date_text, "ticker": symbol, "turnover_twd": value, "market": family.split("_")[0].upper()})
                    for theme in membership.get(symbol, []):
                        theme_totals[date_text][theme] += value
            except Exception as exc:
                parse_errors.append({"family": family, "file": str(path), "error": f"{type(exc).__name__}: {exc}"})

    theme_rank: list[dict] = []
    for date_text, values in sorted(theme_totals.items()):
        for rank, (theme, value) in enumerate(sorted(values.items(), key=lambda x: (-x[1], x[0])), start=1):
            theme_rank.append({"date": date_text, "theme_rank": rank, "theme": theme, "turnover_twd": value})

    for family in ("twse_institutional", "tpex_institutional"):
        for path in sorted((SOURCE / family).glob("*.json")):
            if path.name.endswith(".meta.json") or path.name.endswith(".error.json"):
                continue
            try:
                for symbol, ymd, total in institutional_rows(family, path):
                    institutional.append({"date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", "ticker": symbol, "institutional_net_shares": total, "market": family.split("_")[0].upper()})
            except Exception as exc:
                parse_errors.append({"family": family, "file": str(path), "error": f"{type(exc).__name__}: {exc}"})

    write_gzip(OUT / "official_stock_turnover_daily.csv.gz", ["date", "ticker", "turnover_twd", "market"], stock_turnover)
    write_gzip(OUT / "current_taxonomy_theme_turnover_rank_daily.csv.gz", ["date", "theme_rank", "theme", "turnover_twd"], theme_rank)
    write_gzip(OUT / "official_institutional_net_daily.csv.gz", ["date", "ticker", "institutional_net_shares", "market"], institutional)
    with (OUT / "parse_errors.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["family", "file", "error"])
        writer.writeheader(); writer.writerows(parse_errors)
    summary = {
        "status": "research_only_current_taxonomy_until_date_aware_membership_ready",
        "stock_turnover_rows": len(stock_turnover),
        "theme_rank_rows": len(theme_rank),
        "institutional_rows": len(institutional),
        "parse_error_rows": len(parse_errors),
        "taxonomy_warning": "Current data/theme_map.csv is applied historically; this panel cannot be formal-ready or replace V4-D.",
    }
    (OUT / "panel_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
