from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from .pool3_radar_readiness import PERIODS, _cache_covers


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill Pool3 Radar price cache using BACKTEST_LAB yfinance helper.")
    parser.add_argument("--core-root", required=True)
    parser.add_argument("--theme-map", default="data/theme_map.csv")
    parser.add_argument("--price-cache-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--download-start-date", default="2020-01-01")
    parser.add_argument("--download-end-date", default="2026-05-26")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    core_src = Path(args.core_root) / "src"
    if str(core_src) not in sys.path:
        sys.path.insert(0, str(core_src))

    from backtest_lab.data import download_yfinance_prices  # noqa: PLC0415

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_log_path = output_dir / "run_log.csv"
    run_log = _read_run_log(run_log_path)
    processed = {row["symbol"] for row in run_log if row["status"] in {"covered_existing", "downloaded", "failed"}}
    completed = {row["symbol"] for row in run_log if row["status"] in {"covered_existing", "downloaded"}}
    attempted = 0

    for member in _read_theme_members(Path(args.theme_map)):
        if member["symbol"] in processed:
            continue
        if _member_cache_covers(member["symbol"], Path(args.price_cache_dir)):
            run_log.append(_log_row(member, "covered_existing", "cache already covers all required periods"))
            _write_run_log(run_log_path, run_log)
            completed.add(member["symbol"])
            processed.add(member["symbol"])
            continue
        if args.limit and attempted >= args.limit:
            break
        attempted += 1
        _write_step(output_dir, f"downloading_{member['symbol']}")
        status, message = _download_member(
            member,
            cache_dir=Path(args.price_cache_dir),
            start_date=args.download_start_date,
            end_date=args.download_end_date,
            download_yfinance_prices=download_yfinance_prices,
        )
        run_log.append(_log_row(member, status, message))
        _write_run_log(run_log_path, run_log)
        processed.add(member["symbol"])
        if status == "downloaded":
            completed.add(member["symbol"])

    _write_step(output_dir, "completed" if attempted == 0 else f"completed_batch_attempted_{attempted}")
    print(f"attempted={attempted}")
    print(f"completed_or_existing={len(completed)}")
    print(f"run_log={run_log_path}")


def _download_member(
    member: dict[str, str],
    *,
    cache_dir: Path,
    start_date: str,
    end_date: str,
    download_yfinance_prices: Any,
) -> tuple[str, str]:
    errors = []
    for ticker in _ticker_candidates(member["symbol"]):
        try:
            download_yfinance_prices([ticker], start_date=start_date, end_date=end_date, cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001 - try alternate exchange suffix before failing.
            errors.append(f"{ticker}: {exc}")
            continue
        cache_path = cache_dir / f"{ticker.replace('.', '_')}.csv"
        if _member_cache_covers(member["symbol"], cache_dir):
            return "downloaded", str(cache_path)
        errors.append(f"{ticker}: downloaded_but_range_not_covered")
    return "failed", "; ".join(errors)


def _member_cache_covers(symbol: str, cache_dir: Path) -> bool:
    for period in PERIODS:
        if not any(
            _cache_covers(cache_dir / f"{ticker.replace('.', '_')}.csv", period["start_date"], period["end_date"])
            for ticker in _ticker_candidates(symbol)
        ):
            return False
    return True


def _ticker_candidates(symbol: str) -> list[str]:
    return [f"{symbol}.TW", f"{symbol}.TWO"]


def _read_theme_members(path: Path) -> list[dict[str, str]]:
    rows = []
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "name": row.get("name", "").strip(),
                    "theme": row.get("theme", "").strip(),
                }
            )
    return rows


def _read_run_log(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_run_log(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["symbol", "name", "theme", "status", "message"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _log_row(member: dict[str, str], status: str, message: str) -> dict[str, str]:
    return {
        "symbol": member["symbol"],
        "name": member.get("name", ""),
        "theme": member.get("theme", ""),
        "status": status,
        "message": message,
    }


def _write_step(output_dir: Path, step: str) -> None:
    (output_dir / "current_step.txt").write_text(step + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
