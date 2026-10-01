from __future__ import annotations


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
