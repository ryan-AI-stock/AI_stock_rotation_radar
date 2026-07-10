import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-DAILY-INCUMBENT-CHALLENGER-00631L-BENCHMARK-PRICE-GAP-FILL-001"
RADAR_ROOT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
CORE_LEDGER = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_daily_incumbent_challenger_state_machine_contract_ohlc_absorbed_20260710"
    r"\daily_incumbent_challenger_00631L_daily_price_gap_ledger.csv"
)
OUT = RADAR_ROOT / "outputs" / "radar_vnext_daily_incumbent_challenger_00631l_benchmark_price_gap_fill_20260710"
RAW = OUT / "raw_sources"

FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def ensure_dirs():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (OUT / "current_step.txt").write_text("started\n", encoding="utf-8")


def clean_num(value):
    if value is None:
        return ""
    text = str(value).replace(",", "").strip()
    if text in {"", "--", "X", "除權息"}:
        return ""
    return text


def roc_to_iso(text):
    m = re.match(r"\s*(\d+)/(\d+)/(\d+)\s*$", str(text))
    if not m:
        return ""
    year = int(m.group(1)) + 1911
    return f"{year:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def read_gap_rows():
    with CORE_LEDGER.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fetch_twse_stock_day(year_month):
    url = (
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        f"?date={year_month}01&stockNo=00631L&response=json"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 RadarData bounded source package"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    sha = hashlib.sha256(payload).hexdigest()
    raw_path = RAW / f"twse_stock_day_00631L_{year_month}.json"
    raw_path.write_bytes(payload)
    return url, payload, sha, raw_path


def fetch_twse_exact_day_absence_probe(date_text):
    ymd = date_text.replace("-", "")
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={ymd}&type=ALLBUT0999&response=json"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 RadarData bounded absence probe"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    sha = hashlib.sha256(payload).hexdigest()
    raw_path = RAW / f"twse_mi_index_allbut0999_{ymd}_absence_probe.json"
    raw_path.write_bytes(payload)
    stat = ""
    try:
        stat = json.loads(payload.decode("utf-8-sig")).get("stat", "")
    except Exception:
        stat = "json_parse_failed"
    return url, payload, sha, raw_path, stat


def parse_twse(payload, source_url, raw_sha, retrieved_at):
    doc = json.loads(payload.decode("utf-8-sig"))
    rows = []
    fields = doc.get("fields") or []
    for item in doc.get("data", []):
        row = dict(zip(fields, item))
        date = roc_to_iso(row.get("日期", ""))
        if not date:
            continue
        rows.append(
            {
                "date": date,
                "ticker": "00631L",
                "name": "元大台灣50正2",
                "market": "TWSE",
                "open": clean_num(row.get("開盤價")),
                "high": clean_num(row.get("最高價")),
                "low": clean_num(row.get("最低價")),
                "close": clean_num(row.get("收盤價")),
                "volume": clean_num(row.get("成交股數")),
                "turnover_value": clean_num(row.get("成交金額")),
                "source_route": "twse_stock_day_selected_etf_month",
                "source_url": source_url,
                "source_quality": "official_unadjusted_close_selected_etf_month",
                "raw_sha256": raw_sha,
                "retrieved_at_utc": retrieved_at,
                "adjustment_policy": "official_unadjusted_close_only; same_basis_adjusted_reference_not_found; adjusted_close_not_fabricated",
            }
        )
    return rows


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main():
    ensure_dirs()
    gap_rows = read_gap_rows()
    required_dates = sorted({r["price_date"] for r in gap_rows})
    months = sorted({d[:4] + d[5:7] for d in required_dates})
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    source_manifest = []
    all_price_rows = []
    for ym in months:
        try:
            url, payload, sha, raw_path = fetch_twse_stock_day(ym)
            parsed = parse_twse(payload, url, sha, retrieved_at)
            source_manifest.append(
                {
                    "ticker": "00631L",
                    "year_month": ym,
                    "market": "TWSE",
                    "route": "twse_stock_day_selected_etf_month",
                    "source_url": url,
                    "raw_cache_path": str(raw_path.relative_to(RADAR_ROOT)),
                    "raw_sha256": sha,
                    "route_status": "fetched",
                    "route_error": "",
                    "accepted_month_rows": len(parsed),
                    "response_bytes": len(payload),
                    "retrieved_at_utc": retrieved_at,
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )
            all_price_rows.extend(parsed)
        except Exception as exc:  # row-level blocking is handled after lookup.
            source_manifest.append(
                {
                    "ticker": "00631L",
                    "year_month": ym,
                    "market": "TWSE",
                    "route": "twse_stock_day_selected_etf_month",
                    "source_url": (
                        "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
                        f"?date={ym}01&stockNo=00631L&response=json"
                    ),
                    "raw_cache_path": "",
                    "raw_sha256": "",
                    "route_status": "route_error",
                    "route_error": repr(exc),
                    "accepted_month_rows": 0,
                    "response_bytes": 0,
                    "retrieved_at_utc": retrieved_at,
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
            )

    by_date = {r["date"]: r for r in all_price_rows}
    absence_probe_by_date = {}
    filled = []
    blocked = []
    for gap in gap_rows:
        price = by_date.get(gap["price_date"])
        base = {
            **gap,
            "same_basis_adjusted_reference_ready": False,
            "official_unadjusted_close_available": bool(price),
            "adjusted_close_ready": False,
            "source_quality": "",
            "source_route": "",
            "source_url": "",
            "raw_sha256": "",
            "close": "",
            "price_basis": "official_unadjusted_close_only",
            "adjustment_policy": "adjusted_close_not_fabricated",
            "blocked_reason": "",
            "future_data_violation_count": 0,
            **FLAGS,
        }
        if price and price.get("close"):
            row = {
                **base,
                "name": price["name"],
                "market": price["market"],
                "open": price["open"],
                "high": price["high"],
                "low": price["low"],
                "close": price["close"],
                "volume": price["volume"],
                "turnover_value": price["turnover_value"],
                "source_quality": price["source_quality"],
                "source_route": price["source_route"],
                "source_url": price["source_url"],
                "raw_sha256": price["raw_sha256"],
                "retrieved_at_utc": price["retrieved_at_utc"],
                "adjustment_policy": price["adjustment_policy"],
            }
            filled.append(row)
        else:
            absence_status = ""
            try:
                url, payload, sha, raw_path, stat = fetch_twse_exact_day_absence_probe(gap["price_date"])
                absence_status = stat
                absence_probe_by_date[gap["price_date"]] = {
                    "source_url": url,
                    "raw_sha256": sha,
                    "raw_cache_path": str(raw_path.relative_to(RADAR_ROOT)),
                    "response_bytes": len(payload),
                    "stat": stat,
                }
                source_manifest.append(
                    {
                        "ticker": "00631L",
                        "year_month": gap["price_date"].replace("-", "")[:6],
                        "market": "TWSE",
                        "route": "twse_mi_index_allbut0999_exact_day_absence_probe",
                        "source_url": url,
                        "raw_cache_path": str(raw_path.relative_to(RADAR_ROOT)),
                        "raw_sha256": sha,
                        "route_status": "absence_probe_fetched",
                        "route_error": stat,
                        "accepted_month_rows": 0,
                        "response_bytes": len(payload),
                        "retrieved_at_utc": retrieved_at,
                        "future_data_violation_count": 0,
                        **FLAGS,
                    }
                )
            except Exception as exc:
                absence_status = f"absence_probe_error={repr(exc)}"
            row = {
                **base,
                "blocked_reason": (
                    "official_twse_selected_etf_close_missing_for_price_date; "
                    f"twse_exact_day_absence_probe={absence_status}"
                ),
                "source_route": "twse_stock_day_selected_etf_month|twse_mi_index_allbut0999_exact_day_absence_probe",
            }
            blocked.append(row)

    input_count = len(gap_rows)
    filled_count = len(filled)
    blocked_count = len(blocked)
    official_ready = blocked_count == 0 and filled_count == input_count

    filled_fields = [
        "ticker",
        "price_date",
        "required_as",
        "impacted_signal_dates",
        "impacted_state_machine_variants",
        "source_requirement",
        "adjusted_close_required_for_same_basis",
        "next_owner",
        "name",
        "market",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover_value",
        "price_basis",
        "same_basis_adjusted_reference_ready",
        "official_unadjusted_close_available",
        "adjusted_close_ready",
        "source_route",
        "source_url",
        "source_quality",
        "raw_sha256",
        "retrieved_at_utc",
        "adjustment_policy",
        "blocked_reason",
        "future_data_violation_count",
        *FLAGS.keys(),
    ]
    blocked_fields = filled_fields
    manifest_fields = [
        "ticker",
        "year_month",
        "market",
        "route",
        "source_url",
        "raw_cache_path",
        "raw_sha256",
        "route_status",
        "route_error",
        "accepted_month_rows",
        "response_bytes",
        "retrieved_at_utc",
        "future_data_violation_count",
        *FLAGS.keys(),
    ]
    price_fields = [
        "date",
        "ticker",
        "name",
        "market",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover_value",
        "source_route",
        "source_url",
        "source_quality",
        "raw_sha256",
        "retrieved_at_utc",
        "adjustment_policy",
    ]

    write_csv(OUT / "daily_incumbent_challenger_00631L_benchmark_price_filled_rows.csv", filled, filled_fields)
    write_csv(OUT / "daily_incumbent_challenger_00631L_benchmark_price_blocked_ledger.csv", blocked, blocked_fields)
    write_csv(OUT / "daily_incumbent_challenger_00631L_benchmark_price_source_manifest.csv", source_manifest, manifest_fields)
    write_csv(
        OUT / "daily_incumbent_challenger_00631L_benchmark_price_unadjusted_close_rows.csv",
        [by_date[d] for d in required_dates if d in by_date],
        price_fields,
    )
    write_csv(
        OUT / "daily_incumbent_challenger_00631L_benchmark_price_coverage_audit.csv",
        [
            {
                "input_gap_dates": input_count,
                "filled_dates": filled_count,
                "blocked_dates": blocked_count,
                "same_basis_adjusted_reference_ready": False,
                "official_unadjusted_close_available": official_ready,
                "ready_for_core_absorption": official_ready,
                "future_data_violation_count": 0,
            }
        ],
        [
            "input_gap_dates",
            "filled_dates",
            "blocked_dates",
            "same_basis_adjusted_reference_ready",
            "official_unadjusted_close_available",
            "ready_for_core_absorption",
            "future_data_violation_count",
        ],
    )
    write_csv(
        OUT / "daily_incumbent_challenger_00631L_benchmark_price_future_data_audit.csv",
        [
            {
                "dataset": "daily_incumbent_challenger_00631L_benchmark_price",
                "future_data_violation_count": 0,
                "market_date_source": "official_twse_market_date_only",
                "query_response_datetime_as_market_date": "prohibited",
                "forward_returns_live_rule_usage": False,
                "adjusted_close_fabricated": False,
                "same_basis_adjusted_reference_ready": False,
            }
        ],
        [
            "dataset",
            "future_data_violation_count",
            "market_date_source",
            "query_response_datetime_as_market_date",
            "forward_returns_live_rule_usage",
            "adjusted_close_fabricated",
            "same_basis_adjusted_reference_ready",
        ],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": (
            "completed_official_unadjusted_00631L_price_package_ready_for_core_absorption"
            if official_ready
            else "blocked_00631L_price_dates_remaining"
        ),
        "input_gap_dates": input_count,
        "filled_dates": filled_count,
        "blocked_dates": blocked_count,
        "same_basis_adjusted_reference_ready": False,
        "official_unadjusted_close_available": official_ready,
        "ready_for_core_absorption": official_ready,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        **FLAGS,
        "blocked_reason": "" if official_ready else "some official close dates missing",
    }
    (OUT / "readiness_for_core_daily_incumbent_challenger_00631L_benchmark_absorption.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    artifacts = [
        "daily_incumbent_challenger_00631L_benchmark_price_filled_rows.csv",
        "daily_incumbent_challenger_00631L_benchmark_price_blocked_ledger.csv",
        "daily_incumbent_challenger_00631L_benchmark_price_source_manifest.csv",
        "daily_incumbent_challenger_00631L_benchmark_price_unadjusted_close_rows.csv",
        "daily_incumbent_challenger_00631L_benchmark_price_coverage_audit.csv",
        "daily_incumbent_challenger_00631L_benchmark_price_future_data_audit.csv",
        "readiness_for_core_daily_incumbent_challenger_00631L_benchmark_absorption.json",
        "manifest.json",
        "final_summary_zh.md",
        "current_step.txt",
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at": retrieved_at,
        "output_path": str(OUT),
        "artifacts": artifacts,
        "flags": FLAGS,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# Daily incumbent/challenger 00631L benchmark price gap fill

## 結論

- input gap dates: {input_count}
- filled dates: {filled_count}
- blocked dates: {blocked_count}
- same_basis_adjusted_reference_ready=false
- official_unadjusted_close_available={str(official_ready).lower()}
- ready_for_core_absorption={str(official_ready).lower()}
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Source policy

- 僅補 00631L ledger 內 21 個 price dates。
- 使用 TWSE STOCK_DAY selected ETF month official route。
- 本包輸出的是 official unadjusted close，不宣稱 adjusted close。
- 沒有使用 00631L+excess reconstruction。
- retrieval time 只作 metadata，不作 market date。

## Flags

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false

## 下一棒

交 Core/Data absorption / readiness refresh；Radar/Data 不直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
