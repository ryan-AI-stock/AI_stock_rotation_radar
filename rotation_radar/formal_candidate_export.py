from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import Bucket, StockMetrics, StockResult
from .scoring import score_stock


FORMAL_CANDIDATE_COLUMNS = [
    "report_date",
    "symbol",
    "name",
    "sector",
    "score",
    "bucket",
    "bucket_key",
    "rank_in_bucket",
    "selected_for_backtest_pool",
    "close",
    "pullback_quality",
    "chip_cleanliness",
    "technical_setup",
    "liquidity",
    "risk_heat",
    "thesis",
    "risk_reason",
]


def write_formal_radar_candidates(
    *,
    stocks: list[StockMetrics],
    output_path: str | Path = "data/formal_radar_candidates.latest.csv",
    report_date: str = "",
) -> Path:
    results = sorted((score_stock(stock) for stock in stocks), key=lambda item: item.score.total, reverse=True)
    actionable = [item for item in results if item.bucket is Bucket.ACTIONABLE]
    watch = [item for item in results if item.bucket is Bucket.WATCH]
    selected = actionable if actionable else watch[:3]
    selected_symbols = {item.metrics.symbol for item in selected}
    bucket_ranks = _rank_by_bucket(results)

    rows = [_row(result, report_date, bucket_ranks[result.bucket][result.metrics.symbol], selected_symbols) for result in results]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FORMAL_CANDIDATE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def _rank_by_bucket(results: list[StockResult]) -> dict[Bucket, dict[str, int]]:
    ranks: dict[Bucket, dict[str, int]] = defaultdict(dict)
    counters: dict[Bucket, int] = defaultdict(int)
    for result in results:
        counters[result.bucket] += 1
        ranks[result.bucket][result.metrics.symbol] = counters[result.bucket]
    return ranks


def _row(
    result: StockResult,
    report_date: str,
    rank_in_bucket: int,
    selected_symbols: set[str],
) -> dict[str, str]:
    metrics = result.metrics
    return {
        "report_date": report_date,
        "symbol": metrics.symbol,
        "name": metrics.name,
        "sector": metrics.sector,
        "score": f"{result.score.total:.1f}",
        "bucket": result.bucket.value,
        "bucket_key": _bucket_key(result.bucket),
        "rank_in_bucket": str(rank_in_bucket),
        "selected_for_backtest_pool": "true" if metrics.symbol in selected_symbols else "false",
        "close": f"{metrics.close:.2f}",
        "pullback_quality": f"{metrics.pullback_quality:.1f}",
        "chip_cleanliness": f"{metrics.chip_cleanliness:.1f}",
        "technical_setup": f"{metrics.technical_setup:.1f}",
        "liquidity": f"{metrics.liquidity:.1f}",
        "risk_heat": f"{metrics.risk_heat:.1f}",
        "thesis": metrics.thesis,
        "risk_reason": metrics.risk_reason,
    }


def _bucket_key(bucket: Bucket) -> str:
    if bucket is Bucket.ACTIONABLE:
        return "actionable"
    if bucket is Bucket.WATCH:
        return "watch"
    return "excluded"
