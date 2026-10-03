from __future__ import annotations


class RequiredDataError(RuntimeError):
    """Activated R1 decisions must fail loudly when mandatory inputs are absent."""


def required_data_gaps(rows: list[dict], required_fields: tuple[str, ...]) -> list[dict]:
    gaps = []
    for row in rows:
        missing = [field for field in required_fields if row.get(field) is None]
        if missing:
            gaps.append({"ticker": str(row.get("ticker", "")), "missing_fields": missing})
    return gaps


def enforce_required_data(
    rows: list[dict], required_fields: tuple[str, ...], *, date: str, context: str,
) -> None:
    gaps = required_data_gaps(rows, required_fields)
    if gaps:
        details = "; ".join(
            f"{item['ticker']}:{','.join(item['missing_fields'])}" for item in gaps
        )
        raise RequiredDataError(f"R1_REQUIRED_DATA_MISSING date={date} context={context} {details}")
