# TWSE Capital Stock Full Quarter Sweep + Proxy Contract

## 結論
- 狀態：`completed_twse_capital_stock_full_sweep_proxy_contract_ready`
- TWSE capital stock full sweep ready：`true`
- proxy contract ready：`true`
- accepted capital stock rows：`43705`
- covered periods：`45/45`
- symbols：`1079`
- future_data_violation_count：`0`

## 邊界
- `formal_exact=false`
- `free_float_market_cap_ready=false`
- 本 package 不是 direct official daily market cap。
- 本 package 不是 daily exact issued shares。
- 本 package 只建立 source-backed proxy contract 與 sample proxy rows。

## Proxy Contract
- 使用 MOPS `ajax_t163sb05` 季度 `capital_stock`。
- 以保守法定申報期限作 available_date。
- available_date 後 carry forward 到下一季 available_date 前。
- join TWSE daily close 後可形成 diagnostic/proxy market cap candidate。
- capital_stock 轉 shares 的 par-value normalization policy 需交 Core 決定。
