# vNext Layer1 Remaining Fields Bounded Parser / Sample Unlock

Status: partial_parser_sample_unlocked_current_ratio_cashflow_still_blocked

結論：
- t163sb05 balance-sheet sample parser 成功，已從本機 response sample 解析 current_assets / current_liabilities，current_ratio 可衍生。
- t163sb05 sample contract rows: 9，sample parsed rows: 2992。
- inventory / receivable risk 尚未 unlock：標準 t163sb05 summary sample 沒有一般製造業 inventory / receivables 欄位；只在部分金融/保險 profile 可見應收款項類欄位，不能作 universal Layer1 欄位。
- cash-flow quality 尚未 unlock：本機只有 t164sb05 現金流量表 route asset，沒有 response sample；t163sb06 已確認是營益分析，不可作 cash-flow route。

Readiness:
- ready_for_core_layer1_remaining_parser_ingest=false
- ready_for_core_contract_design_current_ratio_only=true
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true
- future_data_violation_count=0

下一棒：
- 如果 Strategy/Core 只需要 current_ratio，可交 Core/Data 設計 current_ratio-only bounded contract。
- 若要補 cash-flow quality，Radar/Data 下一步需要 bounded fetch/sample parse `t164sb05` 現金流量表，不是 t163sb06。
- 若要補 inventory/receivable risk，Radar/Data 需要找更細的 balance-sheet detail route；目前 t163sb05 summary 不足。
