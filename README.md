# AI_stock_rotation_radar

台股題材輪動與 2-6 週波段選股報告產生器。

這個專案的目標是用免費公開資料，追蹤資金目前集中在哪些股票市場題材，例如記憶體、被動元件、CPO/矽光子、PCB/載板。交易所產業分類只作為背景資料；報告排序、候選個股與操作名單都以題材資料庫為主。程式會輸出可在手機、平板、電腦閱讀的 HTML 報告，並把個股分成「可操作名單、觀察名單、排除名單」。

## 第一版功能

- 題材輪動評分：資金、動能、題材趨勢、海外指標、估值、風險。
- 個股波段評分：拉回位置、估值、籌碼、基本面、流動性、風險。
- 名單分類：可操作、觀察、排除。
- 多題材標籤：同一檔股票可屬於多個市場題材；報告用深色膠囊標示本期熱門題材，用淺色膠囊標示其他關聯題材。
- 5 日短趨勢：免費版先呈現當日熱度與近 5 個交易日題材資金變化；資料不足時標示資料累積中。
- HTML 報告：響應式版面，適合付費訂閱文章或內部投研報告。
- 範例資料：先用可替換的 demo data 驗證報告格式與評分模型。

## 預計免費資料來源

- 台股日成交、三大法人、融資融券：TWSE、TPEx 公開資料。
- 月營收、財報、本益比：公開資訊觀測站、TWSE、TPEx。
- 海外指標：Yahoo Finance 可讀公開行情頁、交易所公開頁面或手動 CSV。
- 題材事件：先支援人工維護事件檔，避免新聞來源授權問題。

## 使用方式

使用本地 CSV 資料產生報告：

```powershell
python -m rotation_radar.cli --data-dir data --output reports/latest.html
```

每日更新一鍵流程：

```powershell
python -m rotation_radar.cli --daily-update 2026-05-12 --output reports/daily.html
```

這會依序執行：抓取原始資料、清洗資料、更新個股指標、回推題材指標、產生 HTML 報告。若官方端點暫時連不上，但本地已有同日期原始資料，程式會沿用本地快照繼續產報告。

正式產出最新報告：

```powershell
python -m rotation_radar.cli --update-latest-report --output reports/latest.html
```

這個流程採分層更新：

- 全市場上市/上櫃股票清單快取 30 天。
- 全市場報價掃描快取 3 天。
- 題材排名依題材資料庫內股票的成交金額與資金占比重算。
- 題材短趨勢會更新到 `data/theme_history.generated.csv`，用最近 5 個交易日判斷升溫、降溫或持平。
- GitHub Actions 會快取 `data/theme_history.generated.csv`，讓自動寄信版本也能跨日累積短趨勢。
- 個股候選池只從熱門題材與高成交金額股票中初篩。
- 追蹤股報價會在產報告前刷新。
- 熱門題材前三名會各取成交金額前 40 檔，輸出 `data/hot_sector_symbols.generated.csv`。
- 深度資料會針對熱門題材名單合併法人與融資資料，輸出 `data/hot_stock_deep_metrics.generated.csv`。
- 報告中的觀察名單只保留前 5 名，避免初篩候選過多造成閱讀負擔。

補最近 5 個工作日的法人/融資深度資料：

```powershell
python -m rotation_radar.cli --fetch-recent-depth 2026-05-12 --recent-depth-days 5
```

目前 TPEx 上櫃逐檔融資可完整合併；TWSE 上市法人已可合併，但目前抓到的 TWSE 融資端點是市場總表，不是逐檔融資，因此上市股會標記為 `missing_margin`，避免用錯資料。

強制重抓全市場題材掃描：

```powershell
python -m rotation_radar.cli --update-latest-report --force-sector-scan --output reports/latest.html
```

調整題材掃描快取天數：

```powershell
python -m rotation_radar.cli --update-latest-report --sector-scan-max-age-days 5 --output reports/latest.html
```

使用內建範例資料產生報告：

```powershell
python -m rotation_radar.cli --demo --output reports/latest.html
```

抓取 TWSE/TPEx 原始公開資料快照：

```powershell
python -m rotation_radar.cli --fetch-raw 2026-05-12 --raw-output-dir raw_data
```

這個指令會先保存原始 JSON，後續再由清洗器轉成 `data/*.csv`。這樣可以保留資料來源，也方便重跑報告。

清洗原始 JSON 快照：

```powershell
python -m rotation_radar.cli --normalize-raw 2026-05-12 --raw-input-dir raw_data --processed-output-dir processed_data
```

清洗器會把非空表格攤平成 CSV，輸出到 `processed_data/YYYYMMDD/`。若官方端點回傳空表，程式會略過該表。

用清洗後資料更新個股指標：

```powershell
python -m rotation_radar.cli --build-stock-metrics --stock-metrics-input data/stock_metrics.csv --stock-metrics-output data/stock_metrics.generated.csv --processed-input-dir processed_data
```

用個股指標回推題材指標：

```powershell
python -m rotation_radar.cli --build-sector-metrics --sector-metrics-input data/sector_metrics.csv --stock-metrics-input data/stock_metrics.generated.csv --sector-metrics-output data/sector_metrics.generated.csv
```

用產生出的指標檔輸出報告：

```powershell
python -m rotation_radar.cli --sector-metrics-file data/sector_metrics.generated.csv --stock-metrics-file data/stock_metrics.generated.csv --output reports/generated.html
```

輸出檔案：

```text
reports/latest.html
```

## 資料檔案

目前資料層先採 CSV，之後 TWSE/TPEx 抓取器會把公開資料整理成同樣格式。

- `data/theme_map.csv`：市場題材資料庫，定義題材、股票、角色、信心等級與是否納入主要統計。
- `data/theme_universe.csv`：題材項目總庫；目前先建立 21 個題材，後續可持續新增。
- `data/sector_map.csv`：交易所產業分類映射，主要供全市場報價抓取與背景參考使用，不作為報告主排名。
- `data/sector_universe.csv`：候選題材宇宙。報告不會永久鎖定記憶體、PCB、CPO、被動元件；未來玻璃基板、重電、航運、機器人等題材若加入資料庫且分數提高，也會進入排名。
- `data/sector_metrics.csv`：題材評分需要的資金、動能、趨勢、海外、估值與風險指標。
- `data/stock_metrics.csv`：個股評分需要的籌碼、估值、營收、技術與流動性指標。
- `data/price_history.csv`：個股近一月 OHLC、5 日、20 日、60 日均線，用於技術走勢圖。

### sector_metrics.csv 欄位

- `capital_inflow_rank`：題材資金流入分數，0-100。
- `turnover_share_change`：題材成交占比變化分數，0-100。
- `capital_share`、`capital_share_prev`：目前與前期題材熱度池占比，單位為 %；同一檔股票可屬於多個題材，因此這是題材相對熱度，不是交易所唯一產業分類占比。
- `turnover_value`、`turnover_value_prev`：目前與前期成交金額，單位為百萬元。
- `momentum_20d`：20 日價格動能分數，0-100。
- `strong_stock_ratio`：題材內強勢股比例分數，0-100。
- `industry_trend`：題材趨勢分數，0-100。
- `overseas_signal`：海外行情同步分數，0-100。
- `pe_percentile`：題材估值分位，0 代表低估，100 代表偏貴。
- `risk_heat`：短線過熱風險，0 代表低風險，100 代表高風險。

### stock_metrics.csv 欄位

- `pullback_quality`：拉回買點品質，0-100。
- `chip_cleanliness`：籌碼乾淨度，0-100。
- `foreign_5d`、`trust_5d`：外資與投信近五日買賣超。
- `margin_change_5d`：融資近五日變化率。
- `pe`：個股本益比。
- `sector_pe_low`、`sector_pe_avg`、`sector_pe_high`：題材本益比區間與平均。
- `fair_value_low`、`fair_value_avg`、`fair_value_high`：用個股 EPS 乘上題材低檔、平均、高檔本益比推估的合理估值；若空白，報告會即時計算。
- `revenue_yoy`、`revenue_mom`：月營收年增率與月增率。
- `technical_setup`：技術結構分數，0-100。
- `liquidity`：流動性分數，0-100。
- `risk_heat`：個股過熱風險，0-100。

## 評分原則

題材分數滿分 100：

- 資金流入 25%
- 價格動能 15%
- 題材趨勢 20%
- 海外行情 15%
- 估值合理性 15%
- 風險控管 10%

個股分數滿分 100：

- 拉回買點品質 20%
- 籌碼乾淨度 20%
- 估值相對位置 20%
- 基本面確認 15%
- 短線技術結構 15%
- 流動性 10%

分類規則：

- 可操作名單：分數高、風險低、拉回或轉強條件成立。
- 觀察名單：題材與分數不差，但買點、籌碼或風險尚未完全到位。
- 排除名單：籌碼過熱、估值過高、流動性不足、技術轉弱或風險過大。

## 重要限制

這個工具是研究與報告產生器，不是投資建議或自動交易系統。所有輸出都需要使用者自行判斷與承擔風險。
