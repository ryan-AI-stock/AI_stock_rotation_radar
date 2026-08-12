from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests


TICKERS = """4931 4938 4943 4952 4953 4958 4961 4966 4967 4968 4971 4974 4976 4977 4979 4991 4994 5009 5203 5215 5222 5223 5234 5243 5258 5269 5274 5284 5285 5288 5289 5314 5321 5340 5347 5351 5388 5392 5425 5439 5443 5457 5469 5471 5475 5478 5483 5490 5498 5608 5609 5871 5876 5880 5904 6104 6111 6116 6117 6121 6122 6125 6129 6138 6140 6143 6147 6148 6150 6153 6173 6175 6176 6180 6182 6187 6188 6191 6197 6202 6203 6205 6206 6209 6213 6214 6215 6217 6223 6227 6230 6231 6235 6237 6239 6243 6245 6257 6269 6271 6274 6278 6279 6282 6285 6290 6409 6411 6412 6414 6415 6416 6425 6426 6435 6438 6442 6443 6446 6449 6451 6456 6462 6469 6472 6477 6488 6504 6505 6510 6515 6531 6533 6538 6546 6548 6552 6558 6591 6612 6643 6669 6670 6679 6683 6706 6712 6727 6732 6739 6741 6752 6753 6757 6781 6788 6805 6829 6841 6890 7750 8011 8016 8027 8028 8033 8034 8038 8039 8040 8042 8043 8044 8046 8050 8064 8069 8076 8081 8086 8089 8096 8097 8105 8110 8111 8112 8150 8155 8183 8210 8222 8227 8234 8255 8261 8271 8299 8341 8358 8374 8383 8403 8433 8436 8446 8454 8464 8478 8489 8926 8933 8936 8942 8996 9802 9904 9910 9914 9919 9921 9924 9933 9938 9939 9941 9943 9945 9951 9958""".split()
OUT = Path("institutional_remainder")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "V4DInstitutionalRemainder/1.0"})
    for index, ticker in enumerate(TICKERS, 1):
        path = OUT / f"{ticker}.csv.gz"
        if path.exists():
            continue
        response = session.get(
            "https://api.finmindtrade.com/api/v4/data",
            params={
                "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                "data_id": ticker,
                "start_date": "2015-01-01",
                "end_date": "2026-07-23",
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 200:
            raise RuntimeError(f"{ticker}: {payload.get('status')} {payload.get('msg')}")
        raw = pd.DataFrame(payload.get("data") or [])
        if raw.empty:
            result = pd.DataFrame(columns=["ticker", "date", "institutional_total_net"])
        else:
            raw["date"] = pd.to_datetime(raw["date"])
            raw["net"] = pd.to_numeric(raw["buy"], errors="coerce") - pd.to_numeric(raw["sell"], errors="coerce")
            result = raw.groupby(["stock_id", "date"], as_index=False)["net"].sum().rename(
                columns={"stock_id": "ticker", "net": "institutional_total_net"}
            )
            result["ticker"] = result["ticker"].astype(str).str.zfill(4)
        result.to_csv(path, index=False, compression="gzip")
        if index % 10 == 0:
            print(f"{index}/{len(TICKERS)}", flush=True)
        time.sleep(0.08)


if __name__ == "__main__":
    main()
