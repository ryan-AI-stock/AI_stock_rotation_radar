from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_AUDIT_FIELDS = [
    "source_id",
    "source_url",
    "download_status",
    "http_status",
    "date_covered",
    "publish_date",
    "source_title",
    "source_type",
    "exact_or_proxy",
    "license_or_usage_note",
    "parse_status",
    "future_data_violation_check",
    "notes",
]

SEARCH_QUERY_FIELDS = [
    "query_or_source",
    "source_url",
    "search_status",
    "result_count",
    "exact_candidate_count",
    "proxy_candidate_count",
    "failure_or_gap",
]

TIP_EXACT_TITLE_MARKERS = [
    "臺灣證券交易所與富時國際有限公司合編之臺灣指數系列",
    "FTSE TWSE Taiwan Index Series",
    "TSEC Taiwan 50 Index Review",
    "Taiwan 50 Index Review",
]

TIP_RELEVANT_TITLE_MARKERS = TIP_EXACT_TITLE_MARKERS + [
    "臺灣50",
    "台灣50",
    "Taiwan 50",
    "元大台灣卓越50",
    "元大台灣50",
    "0050",
]


def build_pool2_tw50_public_source_search(
    *,
    output_dir: str | Path,
    source_metadata_path: str | Path,
    search_query_path: str | Path | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    audit_rows = _normalize_audit_rows(_read_rows(Path(source_metadata_path)))
    query_rows = _read_rows(Path(search_query_path)) if search_query_path else []

    exact_candidates = [row for row in audit_rows if row["exact_or_proxy"] == "exact_candidate"]
    proxy_candidates = [row for row in audit_rows if row["exact_or_proxy"] == "proxy_candidate"]
    accepted_rows = [
        row
        for row in audit_rows
        if row["parse_status"] in {"accepted_pit_rows", "accepted_proxy_rows"}
    ]
    future_violations = [
        row
        for row in audit_rows
        if row["future_data_violation_check"] not in {"pass", "not_applicable", "requires_notice_parse"}
    ]
    exact_candidates_by_year = _count_by_year(exact_candidates)
    download_status_counts = _count_values(audit_rows, "download_status")

    if accepted_rows and not future_violations:
        status = "partial_source_rows_found_requires_core_validator"
    elif exact_candidates:
        status = "partial_exact_public_sources_found_parse_pending"
    elif proxy_candidates:
        status = "partial_proxy_public_sources_found_parse_pending"
    else:
        status = "blocked_public_source_exhausted"

    public_source_exhausted = not exact_candidates and not proxy_candidates
    readiness = {
        "generated_at": _utc_now_iso(),
        "task_id": "TASK-BACKTEST-CORE-POOL2-PIT-REPLAY-COVERAGE-20260623",
        "status": status,
        "ready": False,
        "formal_ready": False,
        "public_source_exhausted": public_source_exhausted,
        "exact_candidate_count": len(exact_candidates),
        "exact_candidates_by_year": exact_candidates_by_year,
        "proxy_candidate_count": len(proxy_candidates),
        "accepted_rows": len(accepted_rows),
        "blocked_or_parse_pending_rows": len(audit_rows) - len(accepted_rows),
        "future_data_violation_count": len(future_violations),
        "download_status_counts": download_status_counts,
        "source_modes_observed": sorted({row["exact_or_proxy"] for row in audit_rows if row["exact_or_proxy"]}),
        "outputs": {
            "readiness": str(output / "pool2_tw50_public_source_search_readiness.json"),
            "source_search_audit": str(output / "source_search_audit.csv"),
            "public_search_queries": str(output / "public_search_queries.csv"),
            "manifest": str(output / "manifest.md"),
        },
        "next_actions": _next_actions(status),
    }

    _write_rows(output / "source_search_audit.csv", SOURCE_AUDIT_FIELDS, audit_rows)
    _write_rows(output / "public_search_queries.csv", SEARCH_QUERY_FIELDS, _normalize_query_rows(query_rows))
    _write_json(output / "pool2_tw50_public_source_search_readiness.json", readiness)
    _write_manifest(output / "manifest.md", readiness, audit_rows)
    return readiness


def parse_tip_technical_notice_html(html_text: str) -> list[dict[str, str]]:
    """Parse Taiwan Index technical notice rows from the public Nuxt HTML payload."""
    value_map = _extract_nuxt_value_map(html_text)
    data_match = re.search(r"pagination:\{data:\[(?P<data>.*?)\],links:", html_text, re.S)
    if not data_match:
        return []

    rows: list[dict[str, str]] = []
    item_re = re.compile(
        r"\{category:(?P<category>[^,{}]+),title:(?P<title>\"(?:\\.|[^\"])*\"|[^,{}]+),"
        r"url:(?P<url>\"(?:\\.|[^\"])*\"|[^,{}]+),publish_date:(?P<publish_date>\"(?:\\.|[^\"])*\"|[^,{}]+)\}",
        re.S,
    )
    for match in item_re.finditer(data_match.group("data")):
        title = _resolve_nuxt_token(match.group("title"), value_map)
        rows.append(
            {
                "category": _resolve_nuxt_token(match.group("category"), value_map),
                "title": _clean_html_text(title),
                "url": _resolve_nuxt_token(match.group("url"), value_map),
                "publish_date": _resolve_nuxt_token(match.group("publish_date"), value_map),
            }
        )
    return rows


def tip_notice_to_audit_row(row: dict[str, str]) -> dict[str, str]:
    title = row.get("title", "")
    source_id = _source_id_from_url(row.get("url", ""))
    exact_or_proxy = "exact_candidate" if _contains_any(title, TIP_EXACT_TITLE_MARKERS) else _classify_source(title, "taiwanindex_technical_notice")
    parse_status = "notice_pdf_download_pending"
    if exact_or_proxy == "cross_check_only":
        parse_status = "metadata_only_cross_check"
    return {
        "source_id": source_id,
        "source_url": row.get("url", ""),
        "download_status": "metadata_found",
        "http_status": "",
        "date_covered": _date_to_iso(row.get("publish_date", "")),
        "publish_date": row.get("publish_date", ""),
        "source_title": title,
        "source_type": "taiwanindex_technical_notice",
        "exact_or_proxy": exact_or_proxy,
        "license_or_usage_note": "official Taiwan Index public technical notice metadata; verify PDF redistribution/license before publishing raw files",
        "parse_status": parse_status,
        "future_data_violation_check": "requires_notice_parse",
        "notes": "Candidate was discovered from Taiwan Index public technical notice page metadata.",
    }


def _normalize_audit_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        normalized = {field: row.get(field, "").strip() for field in SOURCE_AUDIT_FIELDS}
        title = normalized["source_title"]
        source_type = normalized["source_type"]
        if not normalized["exact_or_proxy"]:
            normalized["exact_or_proxy"] = _classify_source(title, source_type)
        if not normalized["future_data_violation_check"]:
            normalized["future_data_violation_check"] = "requires_notice_parse"
        if not normalized["download_status"]:
            normalized["download_status"] = "metadata_found"
        if not normalized["parse_status"]:
            normalized["parse_status"] = "parse_pending"
        output.append(normalized)
    return output


def _classify_source(title: str, source_type: str) -> str:
    proxy_markers = [
        "元大台灣卓越50基金",
        "元大台灣50",
        "0050",
        "Yuanta 0050",
    ]
    if _contains_any(title, TIP_EXACT_TITLE_MARKERS):
        return "exact_candidate"
    if source_type in {"yuanta_monthly_report", "yuanta_quarterly_holdings"}:
        return "proxy_candidate"
    if any(marker.lower() in title.lower() for marker in proxy_markers):
        return "proxy_candidate"
    return "cross_check_only"


def _contains_any(value: str, markers: list[str]) -> bool:
    lower = value.lower()
    return any(marker.lower() in lower for marker in markers)


def _extract_nuxt_value_map(html_text: str) -> dict[str, str]:
    match = re.search(
        r"window\.__NUXT__=\(function\((?P<params>.*?)\)\{return .*?\}\((?P<args>.*?)\)\);\s*</script><script",
        html_text,
        re.S,
    )
    if not match:
        return {}
    params = [item.strip() for item in match.group("params").split(",") if item.strip()]
    args = _split_js_args(match.group("args"))
    return {param: _decode_js_value(arg) for param, arg in zip(params, args)}


def _split_js_args(args: str) -> list[str]:
    output: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for char in args:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == '"':
            current.append(char)
            in_string = not in_string
            continue
        if char == "," and not in_string:
            output.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        output.append("".join(current).strip())
    return output


def _decode_js_value(token: str) -> str:
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        try:
            return json.loads(token)
        except json.JSONDecodeError:
            return token.strip('"')
    if token == "null":
        return ""
    return token


def _resolve_nuxt_token(token: str, value_map: dict[str, str]) -> str:
    token = token.strip()
    value = _decode_js_value(token) if token.startswith('"') else value_map.get(token, token)
    return html.unescape(value.replace("\\u002F", "/"))


def _clean_html_text(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _source_id_from_url(url: str) -> str:
    match = re.search(r"TechnicalNotices/(\d+)/(tw|en)", url)
    if not match:
        return url.rsplit("/", 1)[-1]
    return f"tip_{match.group(1)}_{match.group(2)}"


def _date_to_iso(value: str) -> str:
    value = value.strip()
    match = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", value)
    if not match:
        return value
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _normalize_query_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{field: row.get(field, "").strip() for field in SEARCH_QUERY_FIELDS} for row in rows]


def _next_actions(status: str) -> list[str]:
    if status == "partial_exact_public_sources_found_parse_pending":
        return [
            "Download the exact_candidate technical notices and parse constituent add/delete/effective-date events.",
            "Build point-in-time TW50 constituent intervals from accepted official events only.",
            "Run Core tw50 constituent coverage validator before marking ready.",
        ]
    if status == "partial_proxy_public_sources_found_parse_pending":
        return [
            "Download proxy_candidate Yuanta 0050 holdings reports and parse/review holdings rows.",
            "Keep proxy rows under proxy-specific readiness; do not pass them as exact TW50 constituents.",
        ]
    if status == "blocked_public_source_exhausted":
        return [
            "Ask user whether to accept manual PDF acquisition or non-official public sources after the recorded public-source audit.",
        ]
    return [
        "Run Core validator against accepted rows and keep formal_ready=false until coverage and future-data checks pass.",
    ]


def _count_by_year(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        year = row.get("publish_date", "")[:4]
        if year:
            counts[year] = counts.get(year, 0) + 1
    return dict(sorted(counts.items()))


def _count_values(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field, "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: str(value or "") for key, value in row.items()} for row in csv.DictReader(handle)]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest(path: Path, readiness: dict[str, Any], rows: list[dict[str, str]]) -> None:
    sample_rows = rows[:10]
    lines = [
        "# Pool2 TW50/0050 Public Source Search",
        "",
        f"Status: `{readiness['status']}`",
        f"Ready: `{readiness['ready']}`",
        f"Public source exhausted: `{readiness['public_source_exhausted']}`",
        f"Exact candidate count: `{readiness['exact_candidate_count']}`",
        f"Proxy candidate count: `{readiness['proxy_candidate_count']}`",
        f"Accepted rows: `{readiness['accepted_rows']}`",
        f"Future data violation count: `{readiness['future_data_violation_count']}`",
        f"Exact candidates by year: `{readiness['exact_candidates_by_year']}`",
        f"Download status counts: `{readiness['download_status_counts']}`",
        "",
        "## Boundary",
        "",
        "- `exact_candidate` means the source may support official Taiwan 50/TWSE-FTSE PIT events after parsing and review.",
        "- `proxy_candidate` means Yuanta 0050 holdings proxy only; it must not be treated as exact TW50 official constituents.",
        "- This package is a source-search/readiness audit. It does not make Pool2 ready by itself.",
        "",
        "## Sample Audit Rows",
        "",
        _markdown_table(sample_rows),
        "",
        "## Next Actions",
        "",
        *[f"- {item}" for item in readiness["next_actions"]],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _markdown_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    columns = ["source_id", "publish_date", "source_title", "exact_or_proxy", "parse_status"]
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(output)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
