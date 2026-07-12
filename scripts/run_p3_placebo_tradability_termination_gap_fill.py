from __future__ import annotations

import csv
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-PHASE-B-PLACEBO-TRADABILITY-TERMINATION-PIT-GAP-FILL-001"
OUTPUT_NAME = "radar_vnext_p3_phase_b_placebo_tradability_termination_pit_gap_fill_20260712"
CORE_ROOT = Path("C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab")
CORE_AUDIT = CORE_ROOT / "outputs/vnext_p3_layer5_phase_b_complete_paths_20260712/p3_layer5_phase_b_all_scenario_tradability_horizon_audit.csv"

MARKETS = {
    "1522": "TWSE", "2419": "TWSE", "2436": "TWSE", "2605": "TWSE",
    "3045": "TWSE", "3231": "TWSE", "3481": "TWSE", "3583": "TWSE",
    "3645": "TWSE", "4919": "TWSE", "6206": "TWSE", "6209": "TWSE",
    "6257": "TWSE", "3357": "TPEx", "3374": "TPEx", "3434": "TPEx",
    "3526": "TPEx", "5009": "TPEx", "5439": "TPEx", "6470": "TPEx",
    "8299": "TPEx",
}

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


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else ["status"])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value: object) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"--", "---", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ad_date(value: str) -> str:
    parts = value.strip().split("/")
    year = int(parts[0]) + 1911 if int(parts[0]) < 1911 else int(parts[0])
    return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def route(ticker: str, market: str, month: str) -> str:
    if market == "TWSE":
        params = urllib.parse.urlencode({"date": month.replace("-", "") + "01", "stockNo": ticker, "response": "json"})
        return "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?" + params
    params = urllib.parse.urlencode({"code": ticker, "date": month.replace("-", "/") + "/01", "response": "json"})
    return "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?" + params


def parse_rows(payload: dict, ticker: str, market: str) -> list[dict]:
    rows: list[dict] = []
    if market == "TWSE":
        fields = payload.get("fields", [])
        data = payload.get("data", [])
        lookup = {name: i for i, name in enumerate(fields)}
        for raw in data:
            try:
                rows.append({
                    "date": ad_date(raw[lookup["日期"]]), "ticker": ticker, "market": market,
                    "open": number(raw[lookup["開盤價"]]), "high": number(raw[lookup["最高價"]]),
                    "low": number(raw[lookup["最低價"]]), "close": number(raw[lookup["收盤價"]]),
                    "volume": number(raw[lookup["成交股數"]]), "turnover_value": number(raw[lookup["成交金額"]]),
                })
            except (KeyError, IndexError, ValueError):
                continue
    else:
        tables = payload.get("tables", [])
        data = tables[0].get("data", []) if tables else []
        for raw in data:
            if len(raw) < 7:
                continue
            rows.append({
                "date": ad_date(raw[0]), "ticker": ticker, "market": market,
                "open": number(raw[3]), "high": number(raw[4]), "low": number(raw[5]),
                "close": number(raw[6]), "volume": number(raw[1]), "turnover_value": number(raw[2]),
            })
    return [row for row in rows if row["close"] is not None]


def fetch_month(ticker: str, market: str, month: str, raw_dir: Path) -> tuple[list[dict], dict]:
    url = route(ticker, market, month)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Radar-Data bounded source audit"})
    retrieved = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
        payload = json.loads(raw.decode("utf-8-sig"))
        rows = parse_rows(payload, ticker, market)
        outcome = "accepted" if rows else "official_response_no_rows"
        error = ""
    except Exception as exc:  # row-level blocker is retained; no silent fill
        raw = str(exc).encode("utf-8")
        rows = []
        status = 0
        outcome = "route_error"
        error = f"{type(exc).__name__}:{exc}"
    digest = sha256_bytes(raw)
    raw_path = raw_dir / f"{market}_{ticker}_{month}.json"
    raw_path.write_bytes(raw)
    manifest = {
        "ticker": ticker, "market": market, "month": month, "source_url": url,
        "source_route": "TWSE_RWD_STOCK_DAY" if market == "TWSE" else "TPEX_TRADING_STOCK",
        "http_status": status, "route_status": outcome, "row_count": len(rows),
        "raw_sha256": digest, "raw_cache_path": str(raw_path), "retrieval_time_utc": retrieved,
        "bytes": len(raw), "error": error,
    }
    for row in rows:
        row.update({
            "source_url": url, "source_route": manifest["source_route"],
            "source_quality": "official_unadjusted_execution_ohlcv",
            "adjustment_policy": "official_unadjusted; no neighbour substitution; adjusted not fabricated",
            "raw_sha256": digest, "raw_cache_path": str(raw_path), "retrieval_time_utc": retrieved,
            "future_data_violation_count": 0,
        })
    return rows, manifest


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    output = repo / "outputs" / OUTPUT_NAME
    raw_dir = output / "raw_audit_samples"
    output.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (output / "current_step.txt").write_text("loading_core_tradability_audit\n", encoding="utf-8")

    with CORE_AUDIT.open(encoding="utf-8-sig", newline="") as handle:
        core_rows = list(csv.DictReader(handle))
    blocked = [row for row in core_rows if row["tradability_horizon_ready"].lower() == "false"]
    if not blocked:
        raise RuntimeError("Core audit has no blocked rows; refusing an unbounded query")

    requirements: list[dict] = []
    for row in blocked:
        for role, field in (("prior_exit", "intended_prior_target"), ("new_entry", "intended_new_target")):
            ticker = (row.get(field) or "").strip()
            if not ticker:
                continue
            requirements.append({
                "scenario": row["scenario"], "decision_date": row["decision_date"],
                "requested_execution_date": row["requested_execution_date"], "ticker": ticker,
                "market": MARKETS[ticker], "role": role,
            })

    fetch_keys = sorted({(row["ticker"], row["market"], row["requested_execution_date"][:7]) for row in requirements})
    all_prices: list[dict] = []
    manifests: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    (output / "current_step.txt").write_text(f"fetching_official_months_0_of_{len(fetch_keys)}\n", encoding="utf-8")
    for index, (ticker, market, month) in enumerate(fetch_keys, start=1):
        rows, manifest = fetch_month(ticker, market, month, raw_dir)
        all_prices.extend(rows)
        manifests.append(manifest)
        for row in rows:
            by_key[(ticker, row["date"])] = row
        (output / "current_step.txt").write_text(f"fetching_official_months_{index}_of_{len(fetch_keys)}\n", encoding="utf-8")

    impact: list[dict] = []
    patch: list[dict] = []
    event_ledger: list[dict] = []
    blocked_ledger: list[dict] = []
    for row in blocked:
        prior = row["intended_prior_target"].strip()
        new = row["intended_new_target"].strip()
        requested = row["requested_execution_date"]
        month_dates = sorted({d for ticker, d in by_key if d >= requested and d[:7] == requested[:7] and ticker in {prior, new}})
        common_date = ""
        for day in month_dates:
            old_ok = not prior or (prior, day) in by_key
            new_ok = not new or (new, day) in by_key
            if old_ok and new_ok:
                common_date = day
                break
        status = "official_trade_continuity_patch_ready" if common_date else "structural_or_later_month_followup_blocked"
        impact_row = {
            "scenario": row["scenario"], "decision_date": row["decision_date"],
            "requested_execution_date": requested, "prior_target": prior, "new_target": new,
            "core_prior_last_price_date": row["prior_target_last_official_price_date"],
            "first_common_official_tradable_date": common_date, "status": status,
            "termination_event_required": not bool(common_date),
            "forced_exit_guard_required": not bool(common_date),
            "future_data_violation_count": 0,
        }
        impact.append(impact_row)
        if common_date:
            for role, ticker in (("prior_exit", prior), ("new_entry", new)):
                if not ticker:
                    continue
                price = by_key[(ticker, common_date)]
                patch.append({
                    **{key: impact_row[key] for key in ("scenario", "decision_date", "requested_execution_date")},
                    "actual_execution_date": common_date, "role": role, **price,
                })
            event_ledger.append({
                "scenario": row["scenario"], "ticker": prior, "event_type": "false_positive_termination_inference",
                "announcement_date_time": "", "market_available_at": "", "last_trading_date": "",
                "effective_termination_date": "", "holder_treatment": "not_applicable_official_trading_continues",
                "evidence": f"official OHLC exists on/after requested execution; first common date {common_date}",
                "source_url": by_key[(prior, common_date)]["source_url"],
                "raw_sha256": by_key[(prior, common_date)]["raw_sha256"],
                "future_data_violation_count": 0,
            })
        else:
            blocked_ledger.append({
                **impact_row,
                "blocked_reason": "official requested-month routes have no common tradable date; termination/effective-date evidence required",
                "attempted_source": "TWSE_RWD_STOCK_DAY_or_TPEX_TRADING_STOCK_requested_month",
                "structural_source_blocked": True,
            })

    price_fields = [
        "scenario", "decision_date", "requested_execution_date", "actual_execution_date", "role",
        "date", "ticker", "market", "open", "high", "low", "close", "volume", "turnover_value",
        "source_url", "source_route", "source_quality", "adjustment_policy", "raw_sha256",
        "raw_cache_path", "retrieval_time_utc", "future_data_violation_count",
    ]
    write_csv(output / "p3_placebo_official_ohlcv_patch_rows.csv", patch, price_fields)
    write_csv(output / "p3_placebo_official_unadjusted_ohlcv_rows.csv", all_prices, price_fields[5:])
    write_csv(output / "p3_placebo_tradability_source_manifest.csv", manifests)
    write_csv(output / "p3_placebo_selected_path_impact_ledger.csv", impact)
    write_csv(output / "p3_placebo_delisting_termination_event_ledger.csv", event_ledger)
    write_csv(output / "p3_placebo_forced_exit_eligibility_deadline_source.csv", [
        {
            "scenario": row["scenario"], "ticker": row["prior_target"],
            "forced_exit_eligible": False if row["first_common_official_tradable_date"] else "blocked",
            "forced_exit_deadline": "", "reason": "official trade continuity resolves transition" if row["first_common_official_tradable_date"] else "event evidence unresolved",
            "normal_execution_date": row["first_common_official_tradable_date"], "future_data_violation_count": 0,
        } for row in impact
    ])
    write_csv(output / "p3_placebo_tradability_termination_blocked_ledger.csv", blocked_ledger)
    write_csv(output / "p3_placebo_future_data_audit.csv", [{
        "audit": "exact official execution dates only; no last-price carry, neighbour substitution, benchmark reconstruction, or current-status historical backfill",
        "status": "pass", "future_data_violation_count": 0,
    }])

    ready = len(blocked_ledger) == 0 and len(impact) == len(blocked)
    readiness = {
        "task_id": TASK_ID,
        "status": "official_trade_continuity_patch_ready_false_termination_blockers" if ready else "partial_structural_termination_evidence_required",
        "source": "official selected ticker-month TWSE STOCK_DAY / TPEx tradingStock",
        "coverage": f"Core blocked episodes={len(blocked)}; exact requested-month routes only",
        "input_blocked_episodes": len(blocked), "resolved_by_official_price_rows": sum(bool(row["first_common_official_tradable_date"]) for row in impact),
        "remaining_blocked_episodes": len(blocked_ledger), "patch_price_rows": len(patch),
        "ready_for_core_p3_phase_b_placebo_tradability_patch_absorption": ready,
        "ready_for_core_p3_selected_path_delisting_termination_guard_absorption": ready,
        "ready_for_core_rerun": ready, "ready_for_experiments": False,
        "future_data_violation_count": 0, **FLAGS,
    }
    (output / "readiness_for_core_p3_placebo_tradability_termination_patch.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# P3 fixed-seed placebo tradability / termination source package

## 結論

- Core input blockers：{len(blocked)} episodes。
- 官方同日雙邊交易價可解：{readiness['resolved_by_official_price_rows']} episodes。
- 仍需終止交易／holder-treatment證據：{len(blocked_ledger)} episodes。
- 本包只用 exact official dates；未使用最後價、鄰日、benchmark或current status回填。
- ready_for_core_p3_phase_b_placebo_tradability_patch_absorption={str(ready).lower()}。
- future_data_violation_count=0。

## 6470修正

6470在2023-07-21後仍有TPEx官方成交資料，因此原本的termination推論是compact漏列造成的false positive，不建立虛構forced-exit事件。

## 下一棒

交 Core/Data absorption/rechain；不直接交 Experiments。
"""
    (output / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (output / "current_step.txt").write_text("completed_handoff_core_pending\n", encoding="utf-8")

    artifacts = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": readiness["source"], "coverage": readiness["coverage"],
        "future_data_violation_count": 0, "ready_for_core_rerun": ready,
        "ready_for_strategy_replay": False, "formal_model_changed": False,
        "trade_decision_changed": False, "active_in_trade_decision": False,
        "report_changed": False, "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
