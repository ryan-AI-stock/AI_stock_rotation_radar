# 月提領官方公司行動 delta

- Core exact held authority：5367 ticker-date、157 ticker、274 holding intervals。
- MOPS bounded query：1025 ticker-month routes，2065 official list/detail responses，1040 event candidates。
- 可入帳現金事件：7 筆，皆同時具 exact ex-date、payment date、cash per share，且除息日落在實際持有日。
- 可接受 holder-scale 資本事件：0 筆。
- blocked held-date candidates：25 筆；包含缺付款日、子公司公告、限制員工新股註銷或缺 holder-scale effective terms。
- 沒有 MOPS 候選資料不等於 no-event proof；沒有使用 adjusted factor 推定事件或將缺失填零。
