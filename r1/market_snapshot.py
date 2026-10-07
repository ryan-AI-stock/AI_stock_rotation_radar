from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from r1.config import R1Config
from r1.theme_policy import load_themes
from rotation_radar.base_cycle_daily_report import load_official_prices_and_turnover
from rotation_radar.v4d_top1_signal import ADJUSTED_WARMUP, LIQUIDITY_WARMUP, extend_adjusted_with_official_raw


RETURN_WINDOWS = {"daily_return": 1, "return_1w": 5, "return_1m": 20, "return_3m": 60, "return_6m": 120}


def _load_universe(*, config_path: str | Path, theme_path: str | Path | None = None) -> dict[str, dict]:
    if theme_path:
        universe = {
            member.ticker: {"company": member.company, "market": member.market}
            for theme in load_themes(theme_path) for member in theme.members
        }
        raw = json.loads(Path(theme_path).read_text(encoding="utf-8"))
        for theme in raw.get("themes", []):
            for ticker, company, market in theme.get("watch_discovery", []):
                universe[str(ticker).zfill(4)] = {"company": company, "market": market}
        return universe
    return {
        security.ticker: {"company": security.company, "market": security.market}
        for security in R1Config.load(config_path).securities
    }


def load_exact_complete_snapshot(*, output: str | Path, target: str,
                                 config_path: str | Path,
                                 theme_path: str | Path | None = None) -> dict | None:
    """Reuse only a complete snapshot for the exact requested date."""
    path = Path(output)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = set(_load_universe(config_path=config_path, theme_path=theme_path))
    rows = payload.get("rows", [])
    actual = {str(row.get("ticker", "")).zfill(4) for row in rows if row.get("raw_close") is not None}
    if payload.get("date") != target or actual != expected or payload.get("gaps"):
        return None
    if payload.get("requested_ticker_count") != len(expected) or payload.get("actual_ticker_count") != len(expected):
        return None
    return payload


def build_market_snapshot(
    *, target: str, config_path: str | Path, source_repo: str | Path,
    source_cache: str | Path, output: str | Path, offline: bool = False,
    theme_path: str | Path | None = None,
) -> dict:
    target_day = pd.Timestamp(target)
    universe_meta = _load_universe(config_path=config_path, theme_path=theme_path)
    universe = set(universe_meta)
    official, recent_turnover = load_official_prices_and_turnover(
        source_repo=Path(source_repo), target=target_day,
        current=pd.DataFrame(columns=["ticker", "name", "market"]),
        source_cache=Path(source_cache), offline=offline,
    )
    official["ticker"] = official.ticker.astype(str).str.zfill(4)
    official["date"] = pd.to_datetime(official.date)
    official = official[official.ticker.isin(universe) & official.date.le(target_day)].copy()

    adjusted_seed = pd.read_csv(ADJUSTED_WARMUP, dtype={"ticker": str}).rename(
        columns={"adjusted_close": "adjusted_analysis_close"}
    )
    adjusted_seed["ticker"] = adjusted_seed.ticker.str.zfill(4)
    adjusted_seed["date"] = pd.to_datetime(adjusted_seed.date)
    adjusted_seed = adjusted_seed[adjusted_seed.ticker.isin(universe)]
    raw_seed = pd.read_csv(LIQUIDITY_WARMUP, dtype={"ticker": str})
    raw_seed["ticker"] = raw_seed.ticker.str.zfill(4)
    raw_seed["date"] = pd.to_datetime(raw_seed.date)
    raw_seed = raw_seed[raw_seed.ticker.isin(universe)]
    extension = extend_adjusted_with_official_raw(
        adjusted_seed,
        raw_seed[["ticker", "date", "raw_close"]].dropna(),
        official,
    )
    prices = pd.concat([adjusted_seed, extension], ignore_index=True, sort=False).drop_duplicates(
        ["ticker", "date"], keep="last"
    ).sort_values(["ticker", "date"])

    recent_turnover["ticker"] = recent_turnover.ticker.astype(str).str.zfill(4)
    recent_turnover["date"] = pd.to_datetime(recent_turnover.date)
    turnover = pd.concat([
        raw_seed[["ticker", "date", "turnover_value"]],
        recent_turnover[recent_turnover.ticker.isin(universe)][["ticker", "date", "turnover_value"]],
    ], ignore_index=True).drop_duplicates(["ticker", "date"], keep="last")
    turnover["turnover_value"] = pd.to_numeric(turnover.turnover_value, errors="coerce")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    rows = []
    gaps = []
    analysis_gaps = []
    for ticker in sorted(universe):
        frame = prices[(prices.ticker == ticker) & prices.date.le(target_day)].copy()
        raw = official[(official.ticker == ticker) & (official.date == target_day)]
        if raw.empty:
            gaps.append({"ticker": ticker, "field_group": "market_price", "status": "DATA_MISSING"})
            continue
        raw_close = float(raw.iloc[-1].close)
        if frame.empty or frame.iloc[-1].date != target_day:
            raw_turnover = turnover[(turnover.ticker == ticker) & (turnover.date == target_day)]
            analysis_gaps.append({
                "ticker": ticker,
                "field_group": "adjusted_price_history",
                "status": "DATA_MISSING",
                "note": "official raw close retained; adjusted analytics not substituted",
            })
            item = {
                "date": target, "ticker": ticker,
                "company": universe_meta[ticker]["company"],
                "market": universe_meta[ticker]["market"],
                "raw_close": raw_close, "adjusted_analysis_close": None,
                "ma20": None, "ma60": None, "bias20": None, "bias60": None,
                "source": "TWSE/TPEx official raw; adjusted history unavailable",
                "as_of_date": target, "published_at": None,
                "available_at": f"{target}T13:30:00+08:00", "retrieved_at": retrieved_at,
                "quality": "RAW_PRICE_READY_ADJUSTED_ANALYTICS_MISSING",
                "future_data_violation_count": 0,
                **{name: None for name in RETURN_WINDOWS},
                "turnover_value": _finite(raw_turnover.iloc[-1].turnover_value)
                if not raw_turnover.empty else None,
                "avg_turnover_20d": None,
                "volume": None, "avg_volume_20d": None,
                "volume_status": "DATA_MISSING_NOT_IN_REUSED_TURNOVER_CONTRACT",
            }
            rows.append(item)
            continue
        frame["ma20"] = frame.adjusted_analysis_close.rolling(20, min_periods=20).mean()
        frame["ma60"] = frame.adjusted_analysis_close.rolling(60, min_periods=60).mean()
        latest = frame.iloc[-1]
        item = {
            "date": target,
            "ticker": ticker,
            "company": universe_meta[ticker]["company"],
            "market": universe_meta[ticker]["market"],
            "raw_close": raw_close,
            "adjusted_analysis_close": float(latest.adjusted_analysis_close),
            "ma20": _finite(latest.ma20),
            "ma60": _finite(latest.ma60),
            "bias20": _ratio(latest.adjusted_analysis_close, latest.ma20),
            "bias60": _ratio(latest.adjusted_analysis_close, latest.ma60),
            "source": "TWSE/TPEx official raw extended with frozen accepted adjustment factor",
            "as_of_date": target,
            "published_at": None,
            "available_at": f"{target}T13:30:00+08:00",
            "retrieved_at": retrieved_at,
            "quality": "HIGH",
            "future_data_violation_count": 0,
        }
        for name, window in RETURN_WINDOWS.items():
            item[name] = _return(frame.adjusted_analysis_close, window)
        ticker_turnover = turnover[(turnover.ticker == ticker) & turnover.date.le(target_day)].sort_values("date")
        item["turnover_value"] = _finite(ticker_turnover.iloc[-1].turnover_value) if not ticker_turnover.empty else None
        item["avg_turnover_20d"] = _finite(ticker_turnover.tail(20).turnover_value.mean()) if len(ticker_turnover) >= 20 else None
        item["volume"] = None
        item["avg_volume_20d"] = None
        item["volume_status"] = "DATA_MISSING_NOT_IN_REUSED_TURNOVER_CONTRACT"
        rows.append(item)

    payload = {
        "model": "R1", "status": "challenger", "date": target,
        "universe_version": "r1-theme-universe-v0.2" if theme_path else "r1-0.1.0",
        "requested_ticker_count": len(universe), "actual_ticker_count": len(rows),
        "rows": rows, "gaps": gaps, "analysis_gaps": analysis_gaps,
        "formal_model_changed": False, "trade_decision_changed": False,
        "active_in_trade_decision": False, "report_changed": False,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _return(series: pd.Series, window: int) -> float | None:
    if len(series) <= window:
        return None
    return float(series.iloc[-1] / series.iloc[-1 - window] - 1)


def _ratio(value: float, mean: float) -> float | None:
    return None if pd.isna(mean) or mean == 0 else float(value / mean - 1)


def _finite(value: float) -> float | None:
    return None if pd.isna(value) else float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an R1 official daily market snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/r1.json")
    parser.add_argument("--themes", default=None,
                        help="Optional R1 v0.2 theme universe, kept separate from v0.1 scoring.")
    parser.add_argument("--source-repo", default=".")
    parser.add_argument("--source-cache", default="data/current_base_cycle_source_cache")
    parser.add_argument("--output", default="data/r1/daily_market_latest.json")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--reuse-exact-complete", action="store_true")
    args = parser.parse_args()
    payload = load_exact_complete_snapshot(
        output=args.output, target=args.date, config_path=args.config, theme_path=args.themes,
    ) if args.reuse_exact_complete else None
    if payload is None:
        payload = build_market_snapshot(
            target=args.date, config_path=args.config, source_repo=args.source_repo,
            source_cache=args.source_cache, output=args.output, offline=args.offline,
            theme_path=args.themes,
        )
    if payload["actual_ticker_count"] != payload["requested_ticker_count"]:
        raise SystemExit(75)
    print(json.dumps({"date": payload["date"], "ticker_count": payload["actual_ticker_count"]}))


if __name__ == "__main__":
    main()
