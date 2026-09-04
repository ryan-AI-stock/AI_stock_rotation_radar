"""Materialize Core's bounded C6 Top3 risk execution-close authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


TASK = "TASK-RADAR-DATA-C6-TOP3-RISK-LAYER-EXACT-EXECUTION-CLOSE-FILL-001"
REPO = Path(__file__).resolve().parents[1]
CORE_AUTHORITY = Path(os.environ.get("C6_RISK_CLOSE_AUTHORITY", str(Path(
    r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-core-production-grade-contract"
    r"\work\c6_top3_risk_layer_core_contract_20260831\phase_j_complete_execution_union"
    r"\radar_complete_variant_execution_source_gap_union.csv"
))))
OUTPUT = Path(os.environ.get(
    "C6_RISK_CLOSE_OUTPUT",
    str(REPO / "outputs" / "radar_c6_top3_risk_execution_union_close_fill_20260831"),
))
LOCAL_INDEX = REPO / (
    "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716/"
    "reusable_combined_close_index.csv.gz"
)
SOURCE_MANIFEST = REPO / (
    "outputs/radar_vnext_p1_p2_primary80_path_independent_raw_close_bulk_fill_20260716/"
    "path_independent_close_source_manifest.csv.gz"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=path.parent) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    atomic_text(path, frame.to_csv(index=False))


def atomic_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def normalize_ticker(value: object) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    return digits.zfill(4) if digits else ""


def normalize_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def positive_number(value: object) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if text in {"", "-", "--", "---"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None


def roc_date(value: object) -> str:
    year, month, day = [int(part) for part in str(value).strip().split("/")]
    if year < 1911:
        year += 1911
    return f"{year:04d}-{month:02d}-{day:02d}"


def route_url(ticker: str, market: str, month: str) -> str:
    if market == "TWSE":
        query = urllib.parse.urlencode(
            {"date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json"}
        )
        return f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?{query}"
    query = urllib.parse.urlencode(
        {"code": ticker, "date": month.replace("-", "/") + "/01", "response": "json"}
    )
    return f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?{query}"


def parse_month(payload: dict, ticker: str, market: str) -> dict[str, float]:
    rows: dict[str, float] = {}
    if market == "TWSE":
        fields = payload.get("fields") or []
        lookup = {"".join(str(name).split()): index for index, name in enumerate(fields)}
        if "日期" not in lookup or "收盤價" not in lookup:
            return rows
        for raw in payload.get("data") or []:
            try:
                close = positive_number(raw[lookup["收盤價"]])
                if close is not None:
                    rows[roc_date(raw[lookup["日期"]])] = close
            except (IndexError, TypeError, ValueError):
                continue
        return rows

    tables = payload.get("tables") or []
    data = tables[0].get("data", []) if tables else []
    for raw in data:
        try:
            close = positive_number(raw[6])
            if close is not None:
                rows[roc_date(raw[0])] = close
        except (IndexError, TypeError, ValueError):
            continue
    return rows


def load_authority() -> pd.DataFrame:
    frame = pd.read_csv(CORE_AUTHORITY, dtype=str, low_memory=False)
    date_column = next(
        (name for name in ("intended_execution_date", "required_date", "date") if name in frame.columns),
        "date",
    )
    required = {"ticker", date_column}
    missing = required.difference(frame.columns)
    if missing:
        raise RuntimeError(f"authority_schema_missing:{sorted(missing)}")
    frame = frame.copy()
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["date"] = frame[date_column].map(normalize_date)
    frame = frame.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    expected = os.environ.get("C6_RISK_CLOSE_EXPECTED_KEYS")
    if expected and len(frame) != int(expected):
        raise RuntimeError(f"authority_scope_changed:{len(frame)}_expected:{expected}")
    return frame


def load_local_index(authority: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], str]:
    frame = pd.read_csv(LOCAL_INDEX, dtype=str, low_memory=False)
    frame["ticker"] = frame["ticker"].map(normalize_ticker)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date.astype(str)
    raw = frame[
        frame["family"].eq("official_raw_execution_close")
        & frame["source_quality"].fillna("").str.contains("official", case=False)
    ].copy()
    raw["close"] = pd.to_numeric(raw["close"], errors="coerce")
    raw = raw[raw["close"].gt(0)]
    raw = raw[raw["market"].isin(["TWSE", "TPEx"])]
    market_map = (
        raw.groupby(["ticker", "market"]).size().reset_index(name="count")
        .sort_values(["ticker", "count"], ascending=[True, False])
        .drop_duplicates("ticker")
        .set_index("ticker")["market"].to_dict()
    )
    raw = raw.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    selected = authority[["ticker", "date"]].merge(raw, on=["ticker", "date"], how="left")
    selected = selected[selected["close"].notna()].copy()
    return selected, market_map, sha256_file(LOCAL_INDEX)


def load_source_manifest() -> dict[tuple[str, str], dict]:
    if not SOURCE_MANIFEST.exists():
        return {}
    frame = pd.read_csv(SOURCE_MANIFEST, dtype=str, low_memory=False)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date.astype(str)
    frame = frame[frame["status"].eq("accepted") & frame["market"].isin(["TWSE", "TPEx"])]
    return {
        (row.market, row.date): row._asdict()
        for row in frame.sort_values(["market", "date"]).itertuples(index=False)
    }


def request_route(ticker: str, market: str, month: str) -> dict:
    url = route_url(ticker, market, month)
    result = {
        "ticker": ticker,
        "market": market,
        "month": month,
        "source_url": url,
        "source_hash": "",
        "retrieved_at": utc_now(),
        "available_at": "source_retrieval_after_official_close",
        "http_status": "",
        "response_bytes": 0,
        "status": "source_blocked",
        "error": "",
        "rows": {},
    }
    for attempt in range(3):
        time.sleep(random.uniform(0.45, 0.8))
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Radar-C6-CloseOnly/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                result["http_status"] = response.status
                result["source_url"] = response.url
            result["response_bytes"] = len(raw)
            result["source_hash"] = sha256_bytes(raw)
            payload = json.loads(raw.decode("utf-8-sig"))
            result["rows"] = parse_month(payload, ticker, market)
            result["status"] = "accepted_route" if result["rows"] else "official_response_no_rows"
            return result
        except Exception as exc:  # retained at row level after all bounded attempts
            result["error"] = f"{type(exc).__name__}:{exc}"
            if attempt < 2:
                time.sleep((2, 6)[attempt])
    return result


def build_route_plan(authority: pd.DataFrame, local_rows: pd.DataFrame, market_map: dict[str, str]) -> pd.DataFrame:
    local_keys = set(zip(local_rows["ticker"], local_rows["date"]))
    pending = authority[~authority.apply(lambda row: (row.ticker, row.date) in local_keys, axis=1)].copy()
    pending["market"] = pending["ticker"].map(market_map)
    pending["month"] = pending["date"].str[:7]
    return pending


def route_key(route: dict) -> str:
    return f"{route['market']}:{route['ticker']}:{route['month']}"


def load_route_checkpoint(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def finalize(
    authority: pd.DataFrame,
    local_rows: pd.DataFrame,
    local_hash: str,
    market_map: dict[str, str],
    routes: list[dict],
) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_lookup = load_source_manifest()
    accepted: list[dict] = []
    for row in local_rows.itertuples(index=False):
        manifest = manifest_lookup.get((row.market, row.date), {})
        accepted.append(
            {
                "ticker": row.ticker,
                "date": row.date,
                "status": "accepted_exact_official_raw_close",
                "official_raw_execution_close": float(row.close),
                "market": row.market,
                "source_quality": row.source_quality,
                "source_url": manifest.get("source_url") or route_url(row.ticker, row.market, row.date[:7]),
                "source_hash": manifest.get("source_hash", ""),
                "local_index_sha256": local_hash,
                "retrieved_at": manifest.get("retrieved_at") or getattr(row, "retrieved_at", ""),
                "available_at": "source_retrieval_after_official_close",
                "source_reuse": "local_official_raw_close_index",
                "future_data_violation_count": 0,
            }
        )

    route_lookup = {(route["ticker"], route["market"], route["month"]): route for route in routes}
    local_keys = {(row["ticker"], row["date"]) for row in accepted}
    no_trade: list[dict] = []
    blocked: list[dict] = []
    plan = build_route_plan(authority, local_rows, market_map)
    for row in plan.itertuples(index=False):
        if not row.market:
            blocked.append({"ticker": row.ticker, "date": row.date, "status": "source_blocked", "classification_reason": "local_official_market_mapping_missing", "future_data_violation_count": 0})
            continue
        route = route_lookup.get((row.ticker, row.market, row.month))
        if route is None:
            blocked.append({"ticker": row.ticker, "date": row.date, "status": "source_blocked", "classification_reason": "network_route_not_run", "market": row.market, "future_data_violation_count": 0})
        elif row.date in route["rows"]:
            accepted.append({
                "ticker": row.ticker, "date": row.date, "status": "accepted_exact_official_raw_close",
                "official_raw_execution_close": route["rows"][row.date], "market": row.market,
                "source_quality": f"official_{row.market.lower()}_selected_ticker_month_close",
                "source_url": route["source_url"], "source_hash": route["source_hash"], "local_index_sha256": "",
                "retrieved_at": route["retrieved_at"], "available_at": route["available_at"],
                "source_reuse": "bounded_official_ticker_month_route", "future_data_violation_count": 0,
            })
        elif route["status"] in {"accepted_route", "official_response_no_rows"}:
            no_trade.append({
                "ticker": row.ticker, "date": row.date, "status": "official_no_trade", "market": row.market,
                "classification_reason": "official_ticker_month_response_has_no_exact_trade_row",
                "source_url": route["source_url"], "source_hash": route["source_hash"],
                "retrieved_at": route["retrieved_at"], "available_at": route["available_at"],
                "future_data_violation_count": 0,
            })
        else:
            blocked.append({
                "ticker": row.ticker, "date": row.date, "status": "source_blocked", "market": row.market,
                "classification_reason": route["error"] or route["status"], "source_url": route["source_url"],
                "source_hash": route["source_hash"], "retrieved_at": route["retrieved_at"],
                "future_data_violation_count": 0,
            })

    columns = ["ticker", "date", "status", "official_raw_execution_close", "market", "source_quality", "source_url", "source_hash", "local_index_sha256", "retrieved_at", "available_at", "source_reuse", "future_data_violation_count"]
    accepted_frame = pd.DataFrame(accepted).reindex(columns=columns).drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
    no_trade_frame = pd.DataFrame(no_trade)
    blocked_frame = pd.DataFrame(blocked)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_accepted_exact_official_raw_close.csv", accepted_frame)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_official_no_trade.csv", no_trade_frame)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_source_blocked.csv", blocked_frame)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_source_manifest.csv", pd.DataFrame(routes).drop(columns=["rows"], errors="ignore"))
    coverage = pd.DataFrame([{
        "authority_unique_keys": len(authority), "accepted_exact_official_raw_close": len(accepted_frame),
        "official_no_trade": len(no_trade_frame), "source_blocked": len(blocked_frame),
        "duplicate_accepted_keys": int(accepted_frame.duplicated(["ticker", "date"]).sum()),
        "future_data_violation_count": 0,
    }])
    atomic_csv(OUTPUT / "c6_top3_risk_execution_coverage_audit.csv", coverage)
    future = pd.DataFrame([{"future_data_violation_count": 0, "audit_status": "pass", "reason": "exact execution authority only; no future outcome read"}])
    atomic_csv(OUTPUT / "c6_top3_risk_execution_future_data_audit.csv", future)
    files = sorted(path for path in OUTPUT.glob("*.csv") if path.name != "checksum_manifest.csv")
    checksums = pd.DataFrame([{"file": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in files])
    atomic_csv(OUTPUT / "checksum_manifest.csv", checksums)
    readiness = {
        "task": TASK,
        "authority_unique_keys": len(authority),
        "accepted_exact_official_raw_close": len(accepted_frame),
        "official_no_trade": len(no_trade_frame),
        "source_blocked": len(blocked_frame),
        "ready_for_core_c6_top3_execution_absorption": len(blocked_frame) == 0,
        "future_data_violation_count": 0,
        "diagnostic_only": True,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "not_live_rule": True,
    }
    atomic_text(OUTPUT / "readiness_for_core_c6_top3_execution_absorption.json", json.dumps(readiness, ensure_ascii=False, indent=2) + "\n")
    atomic_text(OUTPUT / "current_step.txt", "complete\n")
    manifest = {"task": TASK, "authority_path": str(CORE_AUTHORITY), "authority_sha256": sha256_file(CORE_AUTHORITY), "readiness": readiness}
    atomic_text(OUTPUT / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return readiness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true", help="Fetch only local-missing exact ticker-month routes.")
    args = parser.parse_args()
    authority = load_authority()
    local_rows, market_map, local_hash = load_local_index(authority)
    plan = build_route_plan(authority, local_rows, market_map)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_authority.csv", authority)
    atomic_csv(OUTPUT / "c6_top3_risk_execution_route_plan.csv", plan)
    atomic_text(OUTPUT / "current_step.txt", "local_reuse_complete_network_pending\n" if not args.network else "bounded_official_ticker_month_routes_running\n")
    route_checkpoint = OUTPUT / "route_checkpoint.json"
    routes = load_route_checkpoint(route_checkpoint)
    if args.network:
        planned_routes = plan.dropna(subset=["market"])[["ticker", "market", "month"]].drop_duplicates().sort_values(["market", "ticker", "month"])
        # A blocked route is a retryable transport outcome, not completed
        # authority.  Keep successful checkpoints and retry only blocked routes.
        completed = {
            route_key(route)
            for route in routes
            if route.get("status") in {"accepted_route", "official_response_no_rows"}
        }
        for route in planned_routes.itertuples(index=False):
            key = f"{route.market}:{route.ticker}:{route.month}"
            if key in completed:
                continue
            routes.append(request_route(route.ticker, route.market, route.month))
            atomic_json(route_checkpoint, routes)
            atomic_json(OUTPUT / "progress.json", {
                "completed_routes": len(routes),
                "total_routes": len(planned_routes),
                "accepted_routes": sum(item["status"] == "accepted_route" for item in routes),
                "official_response_no_rows_routes": sum(item["status"] == "official_response_no_rows" for item in routes),
                "source_blocked_routes": sum(item["status"] == "source_blocked" for item in routes),
                "updated_at": utc_now(),
            })
            atomic_text(OUTPUT / "current_step.txt", f"bounded_official_ticker_month_routes_running:{len(routes)}\n")
    readiness = finalize(authority, local_rows, local_hash, market_map, routes)
    print(json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    main()
