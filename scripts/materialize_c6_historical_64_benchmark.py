"""Create the versioned historical C6 64-path dashboard reference block."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


DEFAULT_SOURCE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-experiments-diagnostic-validation-attribution"
    r"\outputs\c6_v4d_00631l_withdrawal_comparison_and_64_summary_20260831"
)
DEFAULT_OUTPUT = Path("data/c6_historical_64_benchmark.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metric(frame: pd.DataFrame, metric: str) -> float:
    row = frame.loc[frame["metric"].eq(metric)]
    if len(row) != 1:
        raise ValueError(f"expected exactly one metric row: {metric}")
    return float(row.iloc[0]["median"])


def materialize(source: Path, output: Path) -> dict:
    metrics_path = source / "c6_64_full_range_distribution_metrics.csv"
    summary_path = source / "summary.json"
    metrics = pd.read_csv(metrics_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    representative = next(
        value for value in summary.get("c6_64_invariant_summary", [])
        if value.get("lower_median_actual_route_id")
    )
    payload = {
        "coverage": "64個2023不同起點至2026-08-12；初始TWD7,000,000；歷史每月底提領TWD75,000",
        "capital_and_withdrawal": "TWD7,000,000／每月底TWD75,000",
        "statistical_median_final_nav": _metric(metrics, "final_nav"),
        "statistical_median_account_nav_mdd": _metric(metrics, "account_nav_mdd") / 100,
        "statistical_median_twr_cagr": _metric(metrics, "twr_cagr") / 100,
        "statistical_median_twr_mdd": _metric(metrics, "twr_mdd") / 100,
        "lower_median_actual_route_id": representative["lower_median_actual_route_id"],
        "lower_median_actual_final_nav": representative["lower_median_actual_final_nav"],
        "lower_median_account_nav_mdd": representative["lower_median_account_nav_mdd"],
        "lower_median_twr_cagr_and_mdd": f"{representative['lower_median_twr_cagr']:.4%}／{representative['lower_median_twr_mdd']:.4%}",
        "source_version": "Experiments c6_v4d_00631l_withdrawal_comparison_and_64_summary_20260831",
        "payment_date_note": "2421/3324 2023-07-27/28兩筆付款日歧義保留；四種合法情境不影響期末NAV、TWR、MDD、交易或整股units。",
        "source_metrics_sha256": sha256(metrics_path),
        "source_summary_sha256": sha256(summary_path),
        "future_data_violation_count": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
