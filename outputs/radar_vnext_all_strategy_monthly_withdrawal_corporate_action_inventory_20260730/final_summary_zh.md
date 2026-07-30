# 月提領公司行動資料稽核

本封包只做本機 source inventory；沒有計算績效、調整後價格或股利再投入。

- 已從本機 daily holding ledger 識別 8 個 ticker、413 段實際持有區間。
- 00631L buyhold 納入固定策略 authority。
- V4-D、0050 成分股 all、0050 前30 的 exact actual holding interval authority 未在掛載 Core outputs 找到，因此不能把候選事件包裝成完整策略 coverage。
- 舊官方候選包對目前 union 僅有 13 筆現金股利候選與 13 筆公司行動候選；精確除息日、付款日均為 0，且非股利資本事件沒有可接受 exact ledger。
- adjusted factor 未用來推定事件；缺失未填 0。下一步需 Core 匯出三條缺少策略的 frozen actual holding intervals，才可量化並授權歷史官方 event route delta。
