# R1 法人共識資料源申請 memo（2026-10-19）

## 結論

免費公開來源已足以讓 R1 公開核心五構面完成 52／52，但無法讓法人 EPS／目標價信心層達到全池覆蓋。若要繼續補齊，優先詢問 CMoney 資料表或數據貓頭鷹；若無法提供真正 point-in-time 歷史，再詢價 LSEG I/B/E/S 或 FactSet PIT Consensus。

## 申請前必須書面確認

1. 是否覆蓋台灣上市、上櫃股票，並可先提供 R1 52 檔覆蓋清單。
2. 是否提供 FY1、FY2 EPS 的平均、中位數、最高、最低與納入分析師數。
3. 是否提供 12 個月目標價的平均、中位數、最高、最低與具名券商／機構數。
4. 是否保留每個歷史日期當時可見的 PIT 快照，而不是用今天資料回填歷史。
5. 每筆資料是否有發布時間、進庫時間、修正時間與幣別。
6. 是否允許 CSV、Excel 或 API 匯出，以及個人研究用途的授權範圍。
7. 能否先用 2492、3338、3532、6182、6230、6282、3357 做試用覆蓋驗證。

## 選擇順序

1. CMoney／數據貓頭鷹：先詢價與試用；台股欄位最貼近需求，但必須確認 PIT 歷史與匯出權限。
2. LSEG I/B/E/S Point-in-Time：全球覆蓋、歷史長、欄位完整；若成本可接受，最符合正式 PIT 研究。
3. FactSet Estimates PIT Consensus：日頻 PIT 與十年以上歷史完整；同樣屬機構級方案。

## 不接受的替代

- 只有今天共識、沒有歷史快照。
- 只有單一分析師預估卻標成市場共識。
- 沒有 available_at／timestamp 的事後整理值。
- 網頁可看但授權禁止自動匯出。
- 用實際 EPS、近四季 EPS 或自行推估 EPS 代替法人預估。

## 模型邊界

- 公開核心排名維持正常運作，不因法人資料缺漏停止。
- 法人資料仍只作信心加減項；未經另行核准，不改成硬性買賣門檻。
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`

## 已備妥的匯入驗證

- 範本：`data/r1/consensus/provider_import_template.csv`
- 驗證器：`python -m r1.provider_consensus_import`
- 目標價範本：`data/r1/target_prices/provider_import_template.csv`
- 目標價驗證器：`python -m r1.provider_target_price_import`
- 安全併入工具：`python -m r1.provider_bundle_promote`；預設只預覽，明確加上 `--apply` 才會寫入正式CSV。
- 必要欄位包含 FY、EPS 統計、分析師數、來源、發布／可用／擷取時間與品質狀態。
- 池外股票、缺欄位、未來資料、重複觀測與不合法來源層級會被拒絕，並在 audit 結果留下原因。
- 驗證器只產生隔離的標準化檔案，不會自行併入正式評分；取得供應商試用檔後仍須先核對 coverage 與 PIT。
- 目標價另要求具名機構、12個月目標、正數價格及90日內資料；正式快照仍須至少三家獨立機構才可評分。
- 併入採append-only與自然鍵去重；預覽會先計算目標價READY覆蓋變化，任何future-data拒絕都不會寫入正式資料。
