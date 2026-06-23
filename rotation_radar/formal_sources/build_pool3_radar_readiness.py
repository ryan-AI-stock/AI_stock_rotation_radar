from __future__ import annotations

import argparse
import json

from .pool3_radar_readiness import build_pool3_radar_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Pool3 Radar formal readiness package for BACKTEST_LAB Core.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--theme-map", default="data/theme_map.csv")
    parser.add_argument("--formal-universe", default="data/history_replay/formal_grade_2021_2023/formal_universe.csv")
    parser.add_argument("--memory-v1", default="data/formal_sources/date_aware_theme_membership_memory_v1.csv")
    parser.add_argument("--v2-ledger", default="data/formal_sources/theme_membership_evidence_v2.csv")
    parser.add_argument("--v2-readiness", default="data/formal_sources/date_aware_theme_membership_v2_readiness.json")
    parser.add_argument("--price-cache-dir", required=True)
    parser.add_argument("--update-v2-live-files", action="store_true")
    args = parser.parse_args()

    readiness = build_pool3_radar_readiness(
        output_dir=args.output_dir,
        theme_map_path=args.theme_map,
        formal_universe_path=args.formal_universe,
        memory_v1_path=args.memory_v1,
        v2_ledger_path=args.v2_ledger,
        v2_readiness_path=args.v2_readiness,
        price_cache_dir=args.price_cache_dir,
        update_v2_live_files=args.update_v2_live_files,
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
