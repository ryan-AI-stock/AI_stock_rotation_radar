# R1 v1.0 Final Architecture & Validation Report

日期：2026-10-25

狀態：Research / Decision Support System

`formal_model_changed=false`

`trade_decision_changed=false`

`active_in_trade_decision=false`
`report_changed=false`

## 1. 最終架構

資料流固定為：Evidence → Context → Thesis → Competing Hypotheses → Relative Opportunity → Portfolio Research State → Decision Memory / Outcome Review → Controlled Learning。

R1 v1.0不是股票分數排行榜、新聞情緒模型或自動交易系統。所有結論保留Evidence、Counter Evidence、Unknown、Invalidation與Next Observation。

## 2. 六大Engine

1. Evidence Foundation：保存Source、Fact、Event、Claim與Audit，不以缺值補零。
2. Context Engine：分離Market、Theme、Company、Valuation與Flow情境。
3. Thesis / Hypothesis Engine：保存可版本化Thesis、因果鏈、競爭假說與反證。
4. Relative Opportunity / Portfolio Research State：只比較CURRENT_HOLDING與CHALLENGER，使用Hysteresis，不輸出交易指令。
5. Decision Memory / Outcome Review：不可覆寫Snapshot，預留5、20、60TD回顧。
6. Controlled Learning：只產生MODEL_CHANGE_PROPOSAL，不會自動改正式規則。

## 3. Schema

- Evidence：`EvidenceSource`、Fact、Event、Claim、Audit。
- Context：`MarketContext`、`ThemeContext`、`CompanyContext`、`ValuationContext`、`FlowContext`、`ContextSnapshot`。
- Reasoning：`ThesisRecord`、`CausalNode`、`CausalEdge`、`HypothesisRecord`、`ExpectationAnalysis`、`DisconfirmationPass`、`ReasoningSnapshot`。
- Opportunity：`DimensionAssessment`、`RelativeOpportunity`、`PortfolioResearchState`。
- Memory：`DecisionSnapshot`、`OutcomeReview`、`BenchmarkSnapshot`。
- Learning：`ModelChangeProposal`。

所有核心紀錄均有穩定ID，JSONL Store採append-only；相同ID不能覆寫。

## 4. 資料流

本次actual coverage：133個來源、52檔Context、52份Reasoning、10組目前設定持股的最佳Pairwise Challenger比較、10份Decision Snapshot、30個Outcome Review槽位、1個Learning readiness紀錄。

資料缺少時輸出Unknown或DATA_INSUFFICIENT。EPS Revision、Earnings Visibility與估值歷史不足時，不會用分數或推估值代替。

## 5. Decision Flow

每個持股只和候選Challenger逐項比較：結構瓶頸、Thesis、獲利能見度、EPS修正、自身歷史估值、價格預期差、催化、風險、市場、題材與價量風險。

比較結果只有：NO_ADVANTAGE、WATCH、MODERATE_ADVANTAGE、STRONG_ADVANTAGE、DATA_INSUFFICIENT。Portfolio Research State只有：HOLD、WATCH、ADD_REVIEW、TRIM_REVIEW、ROTATION_REVIEW、POSSIBLE_MISPRICING、WAIT_FOR_EVIDENCE。

一般ROTATION_REVIEW必須連續三個Snapshot成立；單日排名變化不能切換State。Critical Thesis Break可跳過等待，但仍只進入Review，不形成自動賣出。

## 6. LLM Boundary

允許：Claim抽取、因果鏈整理、競爭假說、反證與Unknown整理、Thesis比較、Reasoning摘要。

禁止：無來源Fact、猜數值、補缺值、修改PIT、把Inference當Fact、修改正式模型、自動下單或虛構來源。新增validator已測試無trace與交易輸出均會被拒絕。

## 7. PIT設計

Source保留published、available、retrieved與pit_valid。稽核確認133個來源均符合available/published不晚於retrieved且pit_valid=true。Phase 4～6只讀既有Snapshot，不回填未來資料。

## 8. Benchmark設計

固定六條獨立序列：0050、00631L、Cash、Candidate Equal Weight、R1 Research Portfolio、Ryan Actual Portfolio。每條有獨立benchmark_id與portfolio_kind，研究帳戶與實際帳戶不可互相回填。

目前v1 registry已建立，但六條v1每日NAV尚未完整materialize；未取得的值保持Unknown，不宣稱已完成績效比較。

## 9. Research Portfolio設計

R1 Research Portfolio只保存R1研究判斷與State。Ryan Actual Portfolio只作外部觀察，不影響R1研究績效。此次Phase 4以既有`config/r1.json`持股設定作為Pairwise研究起點；該設定仍含已知可能過期持股，因此不作Ryan最新持倉或績效事實。

## 10. Outcome Review

每份Decision Snapshot建立5／20／60TD回顧。結果分類為THESIS_CORRECT_TIMING_CORRECT、THESIS_CORRECT_TIMING_WRONG、THESIS_WRONG、DATA_INSUFFICIENT、UNRESOLVED。

判斷同時需要Thesis Evidence與Timing Evidence；即使股價上漲，只要Thesis被反證，仍分類THESIS_WRONG。未到期禁止回顧。

## 11. Learning機制

Error Taxonomy包含Source、Event Classification、Causal Chain、Expectation、Valuation、Timing、Thesis、Data Gap與Market Regime。

只有至少20個完成Review且跨至少5個日期，才可提出一般模型改動；錯誤類型還須跨過預先註冊的30%門檻。任何Proposal仍需Historical Validation、Out-of-Sample Validation與Stability Check，`auto_apply=false`永久保留。

## 12. 測試結果

- Phase 4～6新增測試：16項通過。
- 全部R1測試：323項通過。
- Model Audit：10／10通過。
- 驗證範圍包含Pairwise、Unknown、Hysteresis、Snapshot不可覆寫、未到期禁止回顧、非單看價格、Benchmark分離、Learning不自動套用、LLM邊界、PIT與formal flags。

## 13. Known Limitations

- v1 Context目前只有2026-10-22單日截面，無法真正完成5／20／60TD結果回顧。
- EPS Revision、Earnings Visibility、4W／12W估值與法人資料仍不完整。
- Pairwise可運作，但多數結論因核心證據不足會是DATA_INSUFFICIENT。
- 尚未接入現有正式R1每日排程，避免未核准地修改正式Dashboard與交易決策。
- 目前無法證明Research Portfolio具穩定超額報酬。

## 14. Remaining Data Gaps

1. 歷史PIT法人EPS修正與具名目標價。
2. 可比較的Earnings Visibility。
3. 連續Context Snapshot與Theme歷史。
4. 六條Benchmark同口徑每日NAV。
5. 最新Ryan實際持倉的單一權威來源；目前設定檔可能落後實際成交。

## 15. 典型案例

本次10個Configured Holding均產生Holding-vs-Challenger研究。由於Thesis信心低且Earnings Visibility／EPS Revision缺口存在，正確結果以WAIT_FOR_EVIDENCE為主。這不是程式失敗，而是Stop Gate在阻止模型把資訊不足誤寫成輪動優勢。

## 16. 與舊R1差異

舊R1核心是多構面分數與換倉顧問。v1改為可追溯Evidence、Context分解、可證偽Thesis、多假說競爭、Holding-vs-Challenger、不可覆寫Memory與受控Learning。分數不再是首頁或結論核心。

## 17. Production Research能力

架構與本機Shadow Materialization已完成，具備Research-system skeleton與資料治理能力；但尚未達到可宣稱「production research成熟」的程度。主因不是程式未建，而是連續時間資料、Outcome樣本、Benchmark NAV及最新實際持倉權威來源仍不足。

## 18. 仍不應視為成熟的功能

- 自動Rotation或交易決策：禁止。
- 5／20／60TD學習結論：尚未到期。
- 模型自我調權重：禁止。
- 法人預估與目標價完整覆蓋：未完成。
- 超額報酬與穩定性證明：未完成。
- 正式Google Dashboard替換：未執行，也不在本次授權內。

## 最終結論

R1 v1.0六階段架構已完成實作與Shadow驗證；已能蒐集、分解、提出競爭假說、比較持股與挑戰者、保存當時判斷並建立受控學習閘門。現階段最正確的定位仍是Research / Decision Support System，不是自動交易系統，也尚不能把資料不足的研究狀態宣稱為成熟投資建議。
