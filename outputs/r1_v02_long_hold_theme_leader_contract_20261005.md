# R1 v0.2 長抱題材龍頭 challenger 契約

日期：2026-10-05

## 定位

R1 v0.2是研究challenger，不取代V4-D或C6，也不直接改變實際交易。目標是最多持有5個AI結構性瓶頸題材的季度龍頭，大部分時間長抱，只在原持股風險與題材同時惡化，且替代龍頭低風險、優勢持續時換倉。

## 題材定義依據

AI工廠採整體系統共同設計，主要限制包含運算、網路、儲存、電源、散熱與系統交付。TSMC另指出AI需求推動CoWoS先進封裝成長，並持續發展SoIC與CPO。因此固定研究結構採9個題材，而不是事先硬定8個：

1. AI運算晶片／ASIC／先進製程。
2. 先進封裝／測試／設備。
3. HBM／記憶體／高速儲存。
4. 高速PCB／CCL／ABF載板。
5. 高速網路／光通訊／CPO。
6. 電源供應／HVDC／BBU。
7. 液冷／高階散熱。
8. AI伺服器／機櫃系統。
9. 關鍵半導體材料／矽晶圓／製程耗材。

題材與成分詳見 `config/r1_v02_themes.json`。這是2026-10-05起的研究分類，不得倒填成歷史PIT題材成分。

## 時間層級

- 每個交易日：累積官方價格、成交、法人、融資融券、可取得營收與事件資料；不因單日排名換股。
- 每週最後交易日：更新估值風險、過熱、題材強弱、替代候選及連續確認週數。
- 每季財報揭露後：於4/1、5/16、8/15、11/15之後第一個週檢查重評各題材Top1，只使用當時已公開資料。
- 每半年：於4/1及8/15之後的季度流程審查題材成分；新增或刪除須保留證據，不回填歷史。

## 題材Top1

季度龍頭分數只比較同題材成員，六項必須全部存在，缺值不補0：

- 瓶頸不可替代性25%。
- 競爭地位20%。
- AI營收與訂單兌現20%。
- 獲利品質15%。
- 財務強度10%。
- 供需與產能能見度10%。

技術指標不決定誰是題材龍頭；它們只決定是否適合現在買進或換入。

## 一般換倉

以下條件必須同時成立：

1. 原持股風險過高。
2. 原公司或題材已由至少兩類獨立證據確認轉弱。
3. 替代題材Top1基本面完整、價格風險較低。
4. 替代龍頭分數優勢至少10分且連續兩週成立。

重大基本面、治理、核心客戶或需求論點破壞可直接退至現金，不等待替代股。

## 12W EPS角色

12W EPS改為中期趨勢與換倉確認，不再單獨阻擋季度題材Top1。1W只作警訊，4W作近期方向，12W用來辨別一週消息與真正的季度趨勢。

## 證據

- NVIDIA Vera Rubin平台：運算、網路、儲存、電源、散熱與機櫃系統共同設計：<https://developer.nvidia.com/blog/inside-the-nvidia-rubin-platform-six-new-chips-one-ai-supercomputer/>
- NVIDIA Spectrum-6：大規模AI工廠的高速網路與光互連：<https://blogs.nvidia.com/blog/nvidia-spectrum-six-arrives-in-gigascale-ai-factories/>
- TSMC 2025年報：CoWoS、SoIC與CPO受AI需求推動：<https://investor.tsmc.com/sites/ir/annual-report/2025/2025%20Annual%20Report_E.pdf>

## 治理狀態

- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
- `report_changed=true`
- 目前題材成員的完整六構面資料尚待建檔；未完成前Top1維持`DATA_MISSING`，不得臆造。
