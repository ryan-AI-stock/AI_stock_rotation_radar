from __future__ import annotations

import csv
from pathlib import Path


def valuation_scenarios(
    *, price: float | None, bear_eps: float | None, base_eps: float | None, bull_eps: float | None,
    bear_pe: float | None, base_pe: float | None, bull_pe: float | None,
) -> dict[str, float | None]:
    values = {}
    for name, eps, pe in (("bear", bear_eps, bear_pe), ("base", base_eps, base_pe), ("bull", bull_eps, bull_pe)):
        fair_value = None if eps is None or pe is None else eps * pe
        upside = None if fair_value is None or not price else fair_value / price - 1
        values[f"{name}_fair_value"] = fair_value
        values[f"{name}_upside"] = upside
    values["forward_pe"] = None if base_eps in {None, 0} or price is None else price / base_eps
    return values


def load_valuation_reference(path: str | Path, *, as_of_date: str) -> dict[str, dict]:
    """Load only valuation observations already available by the requested date."""
    source = Path(path)
    if not source.exists():
        return {}
    result: dict[str, dict] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = str(row.get("ticker", "")).zfill(4)
            data_date = str(row.get("data_date", ""))[:10]
            if not ticker or not data_date or data_date > as_of_date:
                continue
            try:
                percentile = float(row["five_year_percentile"])
                median = float(row["five_year_median_forward_pe"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= percentile <= 1 and median > 0:
                result[ticker] = {
                    **row,
                    "five_year_percentile": percentile,
                    "five_year_median_forward_pe": median,
                }
    return result


def valuation_position(*, forward_pe: float | None, reference: dict | None) -> dict[str, float | None]:
    """Expose valuation position without inventing an unapproved score threshold."""
    if not reference:
        return {
            "forward_pe_percentile_5y": None,
            "forward_pe_median_5y": None,
            "forward_pe_vs_median": None,
        }
    median = float(reference["five_year_median_forward_pe"])
    return {
        "forward_pe_percentile_5y": float(reference["five_year_percentile"]),
        "forward_pe_median_5y": median,
        "forward_pe_vs_median": None if forward_pe is None else forward_pe / median - 1,
    }
