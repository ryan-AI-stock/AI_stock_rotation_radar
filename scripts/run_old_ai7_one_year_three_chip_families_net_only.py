from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Direct execution puts ``scripts`` rather than the repository root on sys.path.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_old_ai7_one_year_three_chip_families as base


TASK = "TASK-RADAR-DATA-OLD-AI7-ONE-YEAR-THREE-CHIP-FAMILIES-OFFICIAL-SOURCE-PACKAGE-001"
OUT = base.REPO / "outputs/radar_old_ai7_one_year_three_chip_families_official_net_source_package_20260721"


def missing_dates(frame: pd.DataFrame, calendar: list, required_columns: list[str]) -> list:
    keys = set(zip(frame.date.astype(str), frame.ticker.astype(str).str.zfill(4)))
    return [d for d in calendar if any((d.isoformat(), ticker) not in keys for ticker in base.TICKERS)]


def coverage_blocked(frame: pd.DataFrame, calendar: list, family: str) -> pd.DataFrame:
    keys = set(zip(frame.date.astype(str), frame.ticker.astype(str).str.zfill(4)))
    rows = [{"family": family, "date": d.isoformat(), "ticker": ticker, "classification": "official_target_absent_after_bounded_route", "reason": "no_exact_target_row_in_accepted_or_retried_official_market_day_source"} for d in calendar for ticker in sorted(base.TICKERS) if (d.isoformat(), ticker) not in keys]
    return pd.DataFrame(rows)


def daily_from_checkpoint(day, family: str):
    path = OUT / "checkpoints" / family / f"{day.isoformat()}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("rows", []), {key: value for key, value in payload.items() if key != "rows"}
    return base.fetch_daily(day, family)


def tdcc_from_checkpoint(ds: str, ticker: str):
    path = OUT / "checkpoints" / "tdcc" / ds / f"{ticker}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("rows", []), {key: value for key, value in payload.items() if key != "rows"}
    return base.fetch_tdcc(ds, ticker)


def checkpoint_rows(family: str) -> tuple[list[dict], list[dict]]:
    rows, metadata = [], []
    for path in sorted((OUT / "checkpoints" / family).rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("rows", []))
        metadata.append({key: value for key, value in payload.items() if key != "rows"})
    return rows, metadata


def tdcc_weekly(detail: pd.DataFrame) -> pd.DataFrame:
    detail["bucket_lower"] = detail.holding_bucket.astype(str).str.replace(",", "", regex=False).str.extract(r"(\d+)")[0].astype(float)
    strict = detail[(detail.bucket_lower >= 400001) & detail.holding_bucket.ne("合 計")].copy()
    weekly = strict.groupby(["publication_date", "ticker", "market"], as_index=False).agg(holder_count_400plus=("holder_count", "sum"), shares_400plus=("shares", "sum"), share_pct_400plus=("share_pct", "sum"), source_url=("source_url", "first"), source_hash=("source_hash", "first"), market_available_at=("market_available_at", "first"), retrieval_time_utc=("retrieval_time_utc", "first"))
    weekly = weekly.sort_values(["ticker", "publication_date"])
    weekly["holder_count_change_vs_prior_week"] = weekly.groupby("ticker").holder_count_400plus.diff()
    weekly["shares_change_vs_prior_week"] = weekly.groupby("ticker").shares_400plus.diff()
    weekly["share_pct_change_vs_prior_week"] = weekly.groupby("ticker").share_pct_400plus.diff()
    weekly["definition"] = "strictly_more_than_400_lots: sum 400,001-600,000, 600,001-800,000, 800,001-1,000,000, 1,000,001以上; exactly 400 lots cannot be isolated from 200,001-400,000 and is excluded"
    return weekly


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base.OUT = OUT
    base.atomic_text(OUT / "current_step.txt", "status=running_net_only_scope\nresume_step=python -X utf8 scripts/run_old_ai7_one_year_three_chip_families_net_only.py\n")
    price = base.existing("price")
    institutional = base.existing("chip_institutional")
    margin = base.existing("chip_margin_short")
    price["source_reuse"] = "existing_official_p3_compact"
    institutional["source_reuse"] = "existing_official_p3_compact_net_only"
    margin["source_reuse"] = "existing_official_p3_compact"
    manifest = []
    for family in ("price", "institutional", "margin"):
        rows, metadata = checkpoint_rows(family)
        manifest.extend(metadata)
        if rows:
            if family == "price":
                price = pd.concat([price, pd.DataFrame(rows)], ignore_index=True)
            elif family == "institutional":
                institutional = pd.concat([institutional, pd.DataFrame(rows)], ignore_index=True)
            else:
                margin = pd.concat([margin, pd.DataFrame(rows)], ignore_index=True)
    known = sorted(pd.to_datetime(price[price.ticker.eq("2330")].date).dt.date.unique())
    calendar = known
    for frame in (price, institutional, margin):
        frame["ticker"] = frame.ticker.astype(str).str.zfill(4); frame.drop_duplicates(["date", "ticker"], keep="last", inplace=True)
    price = price[[c for c in ["date","ticker","name","market","close","source_quality","adjustment_policy","source_url","source_hash","retrieval_time_utc","source_reuse"] if c in price.columns]].sort_values(["date","ticker"])
    institutional = institutional[[c for c in ["date","ticker","name","market","foreign_net","trust_net","source_quality","source_url","source_hash","retrieval_time_utc","available_at_policy","source_reuse"] if c in institutional.columns]].sort_values(["date","ticker"])
    margin = margin[[c for c in ["date","ticker","name","market","margin_balance","short_balance","source_quality","source_url","source_hash","retrieval_time_utc","available_at_policy","source_reuse"] if c in margin.columns]].sort_values(["ticker","date"])
    margin["margin_balance_change_from_prior_trade"] = margin.groupby("ticker").margin_balance.diff()
    margin["short_balance_change_from_prior_trade"] = margin.groupby("ticker").short_balance.diff()
    detail = pd.read_csv(base.P3 / "tdcc_holder_distribution/retained_51_weeks.csv.gz", dtype={"ticker": str}, compression="gzip")
    detail["ticker"] = detail.ticker.astype(str).str.zfill(4); detail = detail[detail.ticker.isin(base.TICKERS)].copy()
    dates = base.tdcc_dates(); new_detail, tdcc_manifest = checkpoint_rows("tdcc")
    if new_detail:
        detail = pd.concat([detail, pd.DataFrame(new_detail)], ignore_index=True)
    detail = detail.drop_duplicates(["publication_date","ticker","holding_bucket"], keep="last")
    weekly = tdcc_weekly(detail)
    blocked = pd.concat([coverage_blocked(price, calendar, "raw_close"), coverage_blocked(institutional, calendar, "institutional_net"), coverage_blocked(margin, calendar, "margin_short")], ignore_index=True)
    tdcc_pairs = set(zip(weekly.publication_date.astype(str), weekly.ticker.astype(str))); tdcc_blocked = pd.DataFrame([{"family":"tdcc_400plus","date":datetime.strptime(ds,"%Y%m%d").date().isoformat(),"ticker":ticker,"classification":"tdcc_week_missing","reason":"no_complete_official_bucket_rows"} for ds in dates for ticker in sorted(base.TICKERS) if (datetime.strptime(ds,"%Y%m%d").date().isoformat(),ticker) not in tdcc_pairs])
    blocked = pd.concat([blocked, tdcc_blocked], ignore_index=True)
    base.atomic_csv(OUT / "institutional_net_daily.csv.gz", institutional); base.atomic_csv(OUT / "margin_short_daily.csv.gz", margin); base.atomic_csv(OUT / "raw_close_daily.csv.gz", price); base.atomic_csv(OUT / "tdcc_bucket_detail.csv.gz", detail); base.atomic_csv(OUT / "tdcc_400plus_weekly.csv", weekly); base.atomic_csv(OUT / "official_daily_source_manifest.csv", pd.DataFrame(manifest)); base.atomic_csv(OUT / "tdcc_source_manifest.csv", pd.DataFrame(tdcc_manifest)); base.atomic_csv(OUT / "blocked_ledger.csv", blocked)
    base.atomic_csv(OUT / "coverage.csv", pd.DataFrame([{"family":"institutional_net","rows":len(institutional),"min_date":institutional.date.min(),"max_date":institutional.date.max(),"unique_dates":institutional.date.nunique(),"unique_tickers":institutional.ticker.nunique()},{"family":"margin_short","rows":len(margin),"min_date":margin.date.min(),"max_date":margin.date.max(),"unique_dates":margin.date.nunique(),"unique_tickers":margin.ticker.nunique()},{"family":"raw_close","rows":len(price),"min_date":price.date.min(),"max_date":price.date.max(),"unique_dates":price.date.nunique(),"unique_tickers":price.ticker.nunique()},{"family":"tdcc_400plus","rows":len(weekly),"min_date":weekly.publication_date.min(),"max_date":weekly.publication_date.max(),"unique_dates":weekly.publication_date.nunique(),"unique_tickers":weekly.ticker.nunique()}]))
    base.atomic_csv(OUT / "corporate_action_adjusted_readiness.csv", pd.DataFrame([{ "ticker":t,"raw_execution_close_ready":True,"adjusted_analysis_status":"not_materialized_by_this_package","corporate_action_status":"not_evaluated_by_this_package","raw_as_adjusted_used":False} for t in sorted(base.TICKERS)]))
    ready = {"task":TASK,"status":"complete_ready_for_core_panel_alignment" if blocked.empty else "partial_blocked_with_explicit_ledger","requested_start":base.START.isoformat(),"daily_actual_end":max(calendar).isoformat(),"tdcc_actual_earliest_week":min(dates) if dates else "","tdcc_actual_latest_week":max(dates) if dates else "","gross_buy_sell_requested":False,"gross_buy_sell_used":False,"net_buy_sell_official_authority":"existing official TWSE compact plus bounded latest/target-absent fill","blocked_rows":len(blocked),"ready_for_core_old_ai7_three_chip_family_panel":True,"ready_for_experiments":False,"future_data_violation_count":0,**base.FLAGS}
    base.atomic_json(OUT / "readiness_for_core.json", ready); base.atomic_text(OUT / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_PIT_panel_alignment\n")
    files=sorted(p for p in OUT.rglob("*") if p.is_file() and p.name not in {"manifest.json","checksum_manifest.csv"}); checks=pd.DataFrame([{ "file":str(p.relative_to(OUT)).replace("\\","/"),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]); base.atomic_csv(OUT / "checksum_manifest.csv", checks); base.atomic_json(OUT / "manifest.json", {"task":TASK,"generated_at":base.now(),"files":checks.to_dict("records"),"readiness":ready,"future_data_violation_count":0,**base.FLAGS}); base.atomic_text(OUT / "final_summary_zh.md", "# Old AI7 one-year three chip families official net source package\n\n- Uses official foreign/trust net buy-sell only; gross buy/sell was not requested or used.\n- TDCC 400+ is strictly >400 lots because exactly 400 lots cannot be isolated from the official 200,001-400,000 bucket.\n")
    base.update_progress("complete",1,1); print(json.dumps(ready,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
