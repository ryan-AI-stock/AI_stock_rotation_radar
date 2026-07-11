# P3 最後兩個 date blocker bounded source audit

- 2025-08-01：TWSE/TPEx官方市場檔有交易資料；exact primary80=80。既有adjusted rows=0，新Yahoo adjusted patch=0。Yahoo分類={'provider_null_placeholder_for_official_trading_session': 72, 'provider_session_absent': 2, 'symbol_history_unavailable_chart_result_null': 6}。raw未冒充adjusted。
- 2025-12-26：TWSE正常交易；TAIFEX官方TXF candidate rows=3，外資/OI target rows=1，patch ready=True。
- future_data_violation_count=0。
- formal_model_changed=false；trade_decision_changed=false；active_in_trade_decision=false；report_changed=false。
