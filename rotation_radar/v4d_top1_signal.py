from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .base_cycle_daily_report import (
    ReportDataNotReady,
    load_official_prices_and_turnover,
)
from .schedule_gate import fetch_twse_calendar, is_trading_day


LAYER1_SNAPSHOT = Path("data/formal_v4d_layer1_snapshot_20260728.csv")
INDUSTRY_MAP = Path("data/formal_v4d_industry_map_current.csv")
LIQUIDITY_WARMUP = Path(
    "data/formal_v4d_liquidity_warmup_20260501_20260722.csv.gz"
)
ADJUSTED_WARMUP = Path(
    "data/formal_v4d_adjusted_warmup_20250901_20260722.csv.gz"
)
EXCLUDED_INDUSTRIES = {
    "食品工業",
    "紡織纖維",
    "汽車工業",
    "電器電纜",
    "橡膠工業",
}
INDUSTRY_CODE_NAMES = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "20": "其他",
    "21": "化學工業",
    "22": "生技醫療",
    "23": "油電燃氣",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "35": "綠能環保",
    "36": "數位雲端",
    "37": "運動休閒",
    "38": "居家生活",
}


def next_trading_day(day: date) -> date:
    open_dates, closed_dates = fetch_twse_calendar()
    current = day + timedelta(days=1)
    while not is_trading_day(current, open_dates, closed_dates):
        current += timedelta(days=1)
    return current


def build_liquidity_authority(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw["date"] = pd.to_datetime(raw["date"])
    raw["ticker"] = raw["ticker"].astype(str).str.zfill(4)
    raw["turnover_value"] = pd.to_numeric(raw["turnover_value"], errors="coerce")
    raw = raw.dropna(subset=["turnover_value"])
    calendar = sorted(raw["date"].unique())
    turnover = raw.pivot(index="date", columns="ticker", values="turnover_value")
    turnover = turnover.reindex(calendar)
    observed = turnover.notna().astype("int8")
    rolling_observed = observed.rolling(20, min_periods=20).sum()
    rolling_average = turnover.fillna(0).rolling(20, min_periods=20).mean()
    daily_rank = rolling_average.rank(axis=1, method="min", ascending=False)
    daily_rank = daily_rank.where(rolling_observed.ge(18))
    stable = daily_rank.le(280).rolling(20, min_periods=20).sum()
    authority = pd.concat(
        [
            daily_rank.stack().rename("turnover_rank_20d"),
            (rolling_observed / 20).stack().rename("turnover_data_completeness"),
            stable.stack().rename("rank_le280_days_in_prior20"),
        ],
        axis=1,
    ).reset_index(names=["signal_date", "ticker"])
    authority["liquidity_pass"] = (
        authority["turnover_rank_20d"].le(250)
        & authority["rank_le280_days_in_prior20"].ge(18)
        & authority["turnover_data_completeness"].ge(0.90)
    )
    names = raw.sort_values("date").drop_duplicates("ticker", keep="last")
    return authority.merge(
        names[["ticker", "name", "market"]], on="ticker", how="left"
    )


def add_price_features(adjusted: pd.DataFrame, target: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict] = []
    for ticker, group in adjusted.groupby("ticker", sort=False):
        item = (
            group[["date", "adjusted_analysis_close"]]
            .drop_duplicates("date", keep="last")
            .sort_values("date")
        )
        item["date"] = pd.to_datetime(item["date"])
        item = item[item["date"].le(target)].reset_index(drop=True)
        if item.empty or item.iloc[-1]["date"] != target:
            continue
        close = item["adjusted_analysis_close"].astype(float)
        if len(close) < 180:
            continue
        values: dict[str, object] = {
            "ticker": ticker,
            "return_60d": close.iloc[-1] / close.iloc[-60] - 1,
            "pre_pullback_20d_strength": close.iloc[-11] / close.iloc[-31] - 1,
            "ma60": close.iloc[-60:].mean(),
            "volatility20": close.pct_change().iloc[-20:].std(),
        }
        for window in (20, 40, 61):
            sample = close.iloc[-window:]
            low, high = float(sample.min()), float(sample.max())
            values[f"pos{window}"] = (
                (float(close.iloc[-1]) - low) / (high - low) * 100
                if high != low
                else np.nan
            )
        recent10 = close.iloc[-10:].to_numpy()
        low_offset = 9 - int(np.argmin(recent10))
        turn_low = 1 <= low_offset <= 5
        # For three equally spaced closes, OLS slope is exactly
        # (last - first) / 2. This avoids platform-specific polyfit epsilon
        # treating a flat 1010, 1015, 1010 path as a positive slope.
        turn_slope = (float(close.iloc[-1]) - float(close.iloc[-3])) / 2 > 0
        turn_higher_low = close.iloc[-3:].min() > close.iloc[-6:-3].min()
        values["turnup_evidence"] = int(turn_low) + int(turn_slope) + int(
            turn_higher_low
        )
        bias = close / close.rolling(60, min_periods=60).mean() - 1
        current_bias = float(bias.iloc[-1])
        history = bias.iloc[-121:-1].dropna().to_numpy()
        values["bias60_prior_count"] = len(history)
        values["bias60_history_percentile"] = (
            np.sum(history < current_bias) / len(history) * 100
            if len(history) >= 108
            else np.nan
        )
        prior_max = float(np.max(history)) if len(history) >= 108 else np.nan
        values["bias60_risk_tier"] = (
            3
            if current_bias > prior_max
            else 2
            if values["bias60_history_percentile"] >= 95
            else 1
            if values["bias60_history_percentile"] >= 80
            else 0
        )
        values["base_position_median"] = float(
            np.nanmedian([values["pos20"], values["pos40"], values["pos61"]])
        )
        values["pos61_bucket"] = float(
            np.clip(np.floor(float(values["pos61"]) / 10), 0, 9)
        )
        rows.append(values)
    return pd.DataFrame(rows)


def extend_adjusted_with_official_raw(
    adjusted: pd.DataFrame,
    historical_raw: pd.DataFrame,
    recent_official: pd.DataFrame,
) -> pd.DataFrame:
    adjusted = adjusted.copy()
    historical_raw = historical_raw.copy()
    recent_official = recent_official.copy()
    adjusted["adjusted_analysis_close"] = pd.to_numeric(
        adjusted["adjusted_analysis_close"], errors="coerce"
    )
    historical_raw["raw_close"] = pd.to_numeric(
        historical_raw["raw_close"], errors="coerce"
    )
    recent_official["close"] = pd.to_numeric(
        recent_official["close"], errors="coerce"
    )
    common = adjusted.merge(
        historical_raw[["ticker", "date", "raw_close"]],
        on=["ticker", "date"],
        how="inner",
    )
    common["factor"] = (
        common["adjusted_analysis_close"] / common["raw_close"]
    )
    factors = (
        common.dropna(subset=["factor"])
        .sort_values("date")
        .drop_duplicates("ticker", keep="last")[["ticker", "factor"]]
    )
    extension = recent_official.rename(columns={"close": "raw_close"}).merge(
        factors, on="ticker", how="left"
    )
    extension["adjusted_analysis_close"] = (
        extension["raw_close"] * extension["factor"]
    )
    return (
        pd.concat(
            [
                adjusted[["ticker", "date", "adjusted_analysis_close"]],
                extension[["ticker", "date", "adjusted_analysis_close"]],
            ],
            ignore_index=True,
        )
        .dropna(subset=["adjusted_analysis_close"])
        .drop_duplicates(["ticker", "date"], keep="last")
        .sort_values(["ticker", "date"])
    )


def select_top1(
    *,
    target: pd.Timestamp,
    source_repo: Path,
    source_cache: Path,
    layer1_path: Path,
    industry_path: Path,
    offline: bool = False,
) -> tuple[dict, pd.DataFrame]:
    empty_current = pd.DataFrame(columns=["ticker", "name", "market"])
    official, turnover = load_official_prices_and_turnover(
        source_repo=source_repo,
        target=target,
        current=empty_current,
        source_cache=source_cache,
        offline=offline,
    )
    warmup = pd.read_csv(LIQUIDITY_WARMUP, dtype={"ticker": str})
    warmup["date"] = pd.to_datetime(warmup["date"])
    turnover = pd.concat(
        [
            warmup[["date", "ticker", "name", "market", "turnover_value"]],
            turnover,
        ],
        ignore_index=True,
    ).drop_duplicates(["date", "ticker"], keep="last")
    liquidity = build_liquidity_authority(turnover)
    current_liquidity = liquidity[liquidity["signal_date"].eq(target)].copy()
    current_liquidity = current_liquidity[current_liquidity["liquidity_pass"]]
    if current_liquidity.empty:
        raise ReportDataNotReady(f"No V4-D liquidity candidates for {target:%Y-%m-%d}")

    layer1 = pd.read_csv(layer1_path, dtype={"ticker": str})
    layer1["ticker"] = layer1["ticker"].str.zfill(4)
    allowed = set(layer1.loc[layer1["layer1_pass"].astype(bool), "ticker"])
    current_liquidity = current_liquidity[
        current_liquidity["ticker"].isin(allowed)
    ].copy()
    adjusted_warmup = pd.read_csv(ADJUSTED_WARMUP, dtype={"ticker": str})
    adjusted_warmup = adjusted_warmup.rename(
        columns={"adjusted_close": "adjusted_analysis_close"}
    )
    adjusted_warmup["date"] = pd.to_datetime(adjusted_warmup["date"])
    raw_warmup = warmup[
        ["date", "ticker", "raw_close"]
    ].dropna(subset=["raw_close"])
    recent_official = official.copy()
    recent_official["ticker"] = recent_official["ticker"].astype(str).str.zfill(4)
    recent_official["date"] = pd.to_datetime(recent_official["date"])
    prices = extend_adjusted_with_official_raw(
        adjusted_warmup,
        raw_warmup,
        recent_official,
    )
    features = add_price_features(prices, target)
    candidates = current_liquidity.merge(features, on="ticker", how="left")
    candidates["volatility_percentile"] = candidates["volatility20"].rank(
        pct=True, method="average"
    )
    required = [
        "return_60d",
        "pre_pullback_20d_strength",
        "pos20",
        "pos40",
        "pos61",
        "bias60_history_percentile",
        "volatility20",
    ]
    candidates["top30_minimum_pass"] = (
        candidates[required].notna().all(axis=1)
        & candidates["return_60d"].gt(0)
        & candidates["pre_pullback_20d_strength"].gt(0)
        & candidates["turnup_evidence"].ge(2)
        & candidates["bias60_prior_count"].ge(108)
        & candidates["volatility_percentile"].lt(0.975)
    )
    ranked = candidates[candidates["top30_minimum_pass"]].sort_values(
        [
            "pos61_bucket",
            "turnup_evidence",
            "pre_pullback_20d_strength",
            "bias60_risk_tier",
            "pos61",
            "base_position_median",
            "return_60d",
            "turnover_rank_20d",
            "ticker",
        ],
        ascending=[True, False, False, True, True, True, False, True, True],
    )
    ranked["candidate_rank"] = range(1, len(ranked) + 1)
    industries = pd.read_csv(
        industry_path, dtype={"ticker": str, "industry_code": str}
    )
    industries["ticker"] = industries["ticker"].str.zfill(4)
    industries["industry_code"] = industries["industry_code"].str.zfill(2)
    normalized = industries["industry_code"].map(INDUSTRY_CODE_NAMES)
    placeholder = industries["industry_name"].astype(str).str.startswith("產業代碼")
    industries.loc[placeholder & normalized.notna(), "industry_name"] = normalized
    ranked = ranked.merge(
        industries[["ticker", "industry_name"]], on="ticker", how="left"
    )
    current_closes = official.loc[
        pd.to_datetime(official["date"]).eq(target), ["ticker", "close"]
    ].copy()
    current_closes["ticker"] = current_closes["ticker"].astype(str).str.zfill(4)
    current_closes = current_closes.drop_duplicates("ticker", keep="last").rename(
        columns={"close": "signal_close"}
    )
    ranked = ranked.merge(current_closes, on="ticker", how="left")
    eligible = ranked[
        ~ranked["industry_name"].isin(EXCLUDED_INDUSTRIES)
        & ranked["candidate_rank"].le(3)
    ]
    if eligible.empty:
        raise ReportDataNotReady(
            f"No non-excluded V4-D Top1-to-Top3 candidate for {target:%Y-%m-%d}"
        )
    row = eligible.iloc[0]
    close_rows = official[
        official["ticker"].astype(str).str.zfill(4).eq(row["ticker"])
        & pd.to_datetime(official["date"]).eq(target)
    ]
    if close_rows.empty:
        raise ReportDataNotReady(f"Official close missing for {row['ticker']}")
    result = {
        "version": 2,
        "model": "V4-D",
        "ticker": row["ticker"],
        "name": row["name"],
        "market": row["market"],
        "signal_date": target.strftime("%Y-%m-%d"),
        "signal_close": float(close_rows.iloc[-1]["close"]),
        "execution_date": next_trading_day(target.date()).isoformat(),
        "entry_close": None,
        "status": "signal_only",
        "daily_marks": {},
        "candidate_rank": int(row["candidate_rank"]),
        "industry": row.get("industry_name", ""),
        "layer1_snapshot_date": layer1_path.stem.rsplit("_", 1)[-1],
    }
    return result, ranked.head(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-repo", default=".")
    parser.add_argument("--source-cache", default="data/current_base_cycle_source_cache")
    parser.add_argument("--state", default="data/formal_v4d_top1_state.json")
    parser.add_argument("--ranking-output", default="reports/formal_v4d_top30_daily.csv")
    parser.add_argument("--layer1", default=str(LAYER1_SNAPSHOT))
    parser.add_argument("--industry-map", default=str(INDUSTRY_MAP))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        state, ranked = select_top1(
            target=pd.Timestamp(args.date),
            source_repo=Path(args.source_repo),
            source_cache=Path(args.source_cache),
            layer1_path=Path(args.layer1),
            industry_path=Path(args.industry_map),
            offline=args.offline,
        )
    except ReportDataNotReady as exc:
        print(f"report_data_not_ready: {exc}")
        raise SystemExit(75) from exc
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ranking_path = Path(args.ranking_output)
    ranking_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(ranking_path, index=False, encoding="utf-8-sig")
    print(json.dumps(state, ensure_ascii=False))


if __name__ == "__main__":
    main()
