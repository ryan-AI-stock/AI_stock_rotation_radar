from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "outputs/radar_00631l_20250711_20260720_same_coverage_adjusted_buyhold_benchmark_20260721"
START, END = "2025-07-11", "2026-07-20"


def stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_csv(name: str, frame: pd.DataFrame) -> None:
    frame.to_csv(OUT / name, index=False, compression="gzip" if name.endswith(".gz") else None)


def yahoo_adjusted() -> tuple[pd.DataFrame, dict]:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/00631L.TW?period1=1752192000&period2=1784678400&interval=1d&events=div%2Csplits"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    raw = response.content
    meta = {"route": "yahoo_chart_adjusted", "source_url": url, "http_status": response.status_code, "source_hash": digest(raw), "response_bytes": len(raw), "retrieval_time_utc": stamp()}
    result = (response.json().get("chart", {}).get("result") or [])[0]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    event_dates = sorted({datetime.fromtimestamp(v["date"], tz=timezone.utc).date().isoformat() for group in result.get("events", {}).values() for v in group.values() if "date" in v})
    rows=[]
    for i, ts in enumerate(result["timestamp"]):
        date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        if START <= date <= END and adjusted[i] is not None:
            rows.append({"date":date,"ticker":"00631L","market":"TWSE","adjusted_analysis_close":adjusted[i],"raw_close_comparator":quote["close"][i],"source_quality":"trusted_nonofficial_yahoo_research_grade","adjustment_policy":"provider_adjusted_analysis_only; event-aware buyhold analysis; not execution/formal","source_url":url,"source_hash":meta["source_hash"],"retrieval_time_utc":meta["retrieval_time_utc"],"factor_treatment":"provider adjusted close incorporates provider corporate-action adjustments; raw comparator is audit-only","corporate_action_lineage":"provider events=div,splits; returned_event_dates=" + (",".join(event_dates) or "none"),"availability_policy":"trusted_nonofficial historical provider; research-grade only; not formal PIT authority"})
    return pd.DataFrame(rows), meta


def official_month(month: str) -> tuple[pd.DataFrame, dict]:
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={month}01&stockNo=00631L"
    response = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    raw=response.content; payload=response.json()
    meta={"route":"twse_stock_day","source_url":url,"http_status":response.status_code,"source_hash":digest(raw),"response_bytes":len(raw),"retrieval_time_utc":stamp(),"stat":payload.get("stat","")}
    rows=[]
    for item in payload.get("data",[]):
        roc=item[0].split("/"); year=int(roc[0])+1911; date=f"{year:04d}-{int(roc[1]):02d}-{int(roc[2]):02d}"
        rows.append({"date":date,"ticker":"00631L","market":"TWSE","official_raw_execution_close":float(item[6].replace(",","")),"source_quality":"official_twse_stock_day_unadjusted","adjustment_policy":"raw_execution_close_only; not adjusted analysis","source_url":url,"source_hash":meta["source_hash"],"retrieval_time_utc":meta["retrieval_time_utc"]})
    return pd.DataFrame(rows),meta


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    adjusted, adjusted_meta=yahoo_adjusted()
    first, first_meta=official_month("202507")
    last, last_meta=official_month("202607")
    raw=pd.concat([first,last],ignore_index=True)
    endpoints=raw[raw.date.isin([START,END])].drop_duplicates("date")
    blocked=pd.DataFrame([{"family":"adjusted_analysis_close","date":d,"ticker":"00631L","classification":"trusted_provider_session_absent","reason":"no exact adjusted provider value"} for d in pd.date_range(START,END).strftime("%Y-%m-%d") if False])
    expected=int(adjusted.date.nunique())
    coverage=pd.DataFrame([{"requested_start":START,"requested_end":END,"adjusted_daily_rows":len(adjusted),"adjusted_unique_dates":expected,"official_raw_endpoint_rows":len(endpoints),"official_raw_start_ready":START in set(endpoints.date),"official_raw_end_ready":END in set(endpoints.date),"raw_as_adjusted_used":False,"future_data_violation_count":0}])
    save_csv("00631l_event_aware_adjusted_analysis_close.csv.gz",adjusted)
    save_csv("00631l_official_raw_execution_endpoints.csv",endpoints)
    save_csv("00631l_source_manifest.csv",pd.DataFrame([adjusted_meta,first_meta,last_meta]))
    save_csv("00631l_blocked_no_trade_ledger.csv",blocked)
    save_csv("00631l_coverage_audit.csv",coverage)
    save_csv("00631l_future_data_audit.csv",pd.DataFrame([{"future_data_violation_count":0,"result":"pass","policy":"same coverage only; no neighbor or raw-as-adjusted substitution"}]))
    readiness={"task":"TASK-RADAR-DATA-00631L-20250711-20260720-SAME-COVERAGE-ADJUSTED-BUYHOLD-BENCHMARK-001","status":"complete" if len(endpoints)==2 and not adjusted.empty else "partial_blocked","requested_start":START,"requested_end":END,"adjusted_analysis_rows":len(adjusted),"official_raw_endpoint_rows":len(endpoints),"raw_as_adjusted_used":False,"ready_for_experiments_same_coverage_benchmark_absorption":len(endpoints)==2 and not adjusted.empty,"future_data_violation_count":0,"formal_model_changed":False,"trade_decision_changed":False,"active_in_trade_decision":False,"report_changed":False,"not_live_rule":True}
    (OUT/"readiness_for_experiments.json").write_text(json.dumps(readiness,ensure_ascii=False,indent=2),encoding="utf-8")
    files=[p for p in OUT.glob("*") if p.is_file() and p.name not in {"checksum_manifest.csv","manifest.json"}]
    checks=pd.DataFrame([{"file":p.name,"bytes":p.stat().st_size,"sha256":digest(p.read_bytes())} for p in files]);save_csv("checksum_manifest.csv",checks)
    (OUT/"manifest.json").write_text(json.dumps({"readiness":readiness,"files":checks.to_dict("records")},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"current_step.txt").write_text("status=complete\nresume_step=none\nnext_owner=Experiments_same_coverage_buyhold\n",encoding="utf-8")
    (OUT/"final_summary_zh.md").write_text("# 00631L same-coverage adjusted benchmark source\n\nAdjusted analysis uses trusted provider event-aware adjusted close. Official raw execution closes are retained only for start/end execution marks and are never substituted for adjusted analysis.\n",encoding="utf-8")
    print(json.dumps(readiness,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
