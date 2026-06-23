from __future__ import annotations

import argparse
import json

from .pool2_tw50_public_source_search import build_pool2_tw50_public_source_search


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Pool2 TW50/0050 public-source search audit package.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-metadata", required=True)
    parser.add_argument("--search-queries")
    args = parser.parse_args()

    readiness = build_pool2_tw50_public_source_search(
        output_dir=args.output_dir,
        source_metadata_path=args.source_metadata,
        search_query_path=args.search_queries,
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
