from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from html import escape

from .models import Bucket, Report, StockResult


def render_report(report: Report) -> str:
    top_sectors = report.sector_results[:3]
    buckets = _group_stocks(report.stock_results)

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(report.title)}</title>
  <style>{_css()}</style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <p class="eyebrow">被AI研究所 | Rotation Radar</p>
      <h1>股票題材輪動雷達</h1>
      <p class="market-view">{escape(report.market_view)}</p>
      <p class="stamp">產出時間：{escape(report.generated_at)}</p>
    </div>
  </header>

  <main>
    {_rotation_digest(report, top_sectors)}
    {_summary_panel(report, top_sectors, buckets)}
    <section class="section sector-section">
      <div class="section-head">
        <h2>市場題材資金輪動排名</h2>
        <p>主分類採市場題材/供應鏈主題，不採交易所大產業。資金占比以已標記題材股票的成交金額占題材追蹤池成交金額計算。</p>
      </div>
      <div class="sector-grid">
        {''.join(_sector_card(item, index + 1, report) for index, item in enumerate(top_sectors))}
      </div>
    </section>

    <section class="section stock-section">
      <div class="section-head">
        <h2>個股條件分群</h2>
        <p>條件偏好：拉回型態、題材相對低本益比與籌碼轉強；個股題材標籤中，深色代表本期前三大熱門題材，淺色代表同股關聯題材。</p>
      </div>
      {_stock_section(Bucket.ACTIONABLE, buckets, report)}
      {_stock_section(Bucket.WATCH, buckets, report)}
      {_stock_section(Bucket.EXCLUDED, buckets, report)}
    </section>
  </main>
</body>
</html>"""


def render_private_signal_report(report: Report) -> str:
    """Render the consolidated private strategy report."""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>私人策略操作總覽</title>
  <style>{_css()}</style>
</head>
<body class="private-report">
  <header class="hero">
    <div class="hero-inner">
      <p class="eyebrow">被AI研究所 | Private Strategy Desk</p>
      <h1>私人策略操作總覽</h1>
      <p class="market-view">兩套策略的收盤後訊號、模擬持股與隔日動作。僅供私人決策，不公開發布。</p>
      <p class="stamp">產出時間：{escape(report.generated_at)}</p>
    </div>
  </header>
  <main>
    <section class="section private-overview">
      <div class="private-summary">
        <span>第一部分｜今日兩模型總結</span>
        <strong>{escape(report.generated_at)}</strong>
        <p>價格口徑為每日官方未調整收盤價；訊號在收盤後成立，預計於下一個交易日執行。</p>
      </div>
      <div class="private-summary-grid">
        {''.join(_private_strategy_summary(item) for item in report.private_strategies)}
      </div>
      <div class="private-detail-title private-detail-page">
        <span>第二部分</span>
        <h2>兩模型詳細分析</h2>
      </div>
      {''.join(_private_strategy_panel(item) for item in report.private_strategies) if report.private_strategies else _formal_signal_panel(report)}
      <div class="private-footnote">
        <b>執行邊界</b>
        <p>本頁顯示模型模擬狀態，不等同券商實際部位。若資料不足、休市或候選池來源過期，應停止依此交易。</p>
      </div>
    </section>
  </main>
</body>
</html>"""


def _private_strategy_summary(item: dict[str, object]) -> str:
    action = str(item.get("today_action", "stay_flat"))
    action_label = {
        "buy_next_day": "隔日買入",
        "sell_next_day": "隔日賣出",
        "hold": "續抱",
        "cooldown_hold": "CD鎖定續抱",
        "cooldown_wait": "CD鎖定空手",
        "blocked_calendar": "交易日曆待確認",
        "stay_flat": "維持空手",
    }.get(action, "待確認")
    held = str(item.get("held_ticker", "") or "")
    held_name = str(item.get("held_name", "") or "")
    position = f"{held} {held_name}" if held else "空手"
    return f"""
    <article class="private-summary-item">
      <span>{escape(str(item.get("pool_label", "")))}</span>
      <h3>{escape(str(item.get("mode_label", "")))}</h3>
      <strong>{escape(action_label)}</strong>
      <p>目前部位：{escape(position)}</p>
      <em>{escape(str(item.get("action_reason", "")))}</em>
    </article>
    """


def _private_strategy_panel(item: dict[str, object]) -> str:
    action = str(item.get("today_action", "stay_flat"))
    action_label = {
        "buy_next_day": "隔日買入",
        "sell_next_day": "隔日賣出",
        "hold": "續抱",
        "cooldown_hold": "CD鎖定續抱",
        "cooldown_wait": "CD鎖定空手",
        "blocked_calendar": "交易日曆待確認",
        "stay_flat": "維持空手",
    }.get(action, "狀態待確認")
    action_class = (
        "positive"
        if action == "buy_next_day"
        else "negative"
        if action == "sell_next_day"
        else "neutral"
    )
    held = str(item.get("held_ticker", "") or "")
    held_name = str(item.get("held_name", "") or "")
    signal = str(item.get("signal_ticker", "") or "")
    signal_name = str(item.get("signal_name", "") or "")
    focus = dict(item.get("focus_metrics", {}) or {})
    candidates = list(item.get("top_candidates", []) or [])
    candidate_rows = "".join(
        f"<tr><td>{index}</td><td>{escape(str(row.get('ticker', '')))} "
        f"{escape(str(row.get('name', '')))}</td>"
        f"<td>{_formal_number(row.get('close'))}</td>"
        f"<td>{_formal_pct(float(row.get('entry_slope_pct', 0) or 0))}</td></tr>"
        for index, row in enumerate(candidates, start=1)
    )
    if not candidate_rows:
        candidate_rows = '<tr><td colspan="4">今日沒有符合完整進場條件的候選</td></tr>'
    position_text = f"{held} {held_name}" if held else "空手"
    focus_text = f"{signal} {signal_name}" if signal else "無"
    source_date = str(item.get("pool_source_date", "") or "")
    pool_count = int(item.get("pool_size", 0) or 0)
    ready_count = int(item.get("data_ready_count", 0) or 0)
    close_value = focus.get("close")
    entry_ma_value = focus.get("entry_ma")
    exit_ma_value = focus.get("exit_ma")
    entry_slope_value = float(focus.get("entry_slope_pct", 0) or 0)
    exit_slope_value = float(focus.get("exit_slope_pct", 0) or 0)
    entry_ma_days = int(item.get("entry_ma_days", 0) or 0)
    entry_slope_days = int(item.get("entry_slope_days", 0) or 0)
    exit_ma_days = int(item.get("exit_ma_days", 0) or 0)
    exit_slope_days = int(item.get("exit_slope_days", 0) or 0)
    entry_price_pass = bool(
        focus.get("ready") and close_value is not None and entry_ma_value is not None
        and float(close_value) > float(entry_ma_value)
    )
    exit_price_pass = bool(
        focus.get("ready") and close_value is not None and exit_ma_value is not None
        and float(close_value) < float(exit_ma_value)
    )
    next_tradable = str(item.get("cooldown_next_tradable_date", "") or "")
    cooldown_status = str(item.get("cooldown_status", "not_started") or "not_started")
    cooldown_remaining = item.get("cooldown_remaining_trading_days")
    if cooldown_status == "locked":
        cooldown_text = f"尚餘 {int(cooldown_remaining or 0)} TD"
        cooldown_note = f"下次可交易日期＝{_slash_date(next_tradable)}"
    elif cooldown_status == "unlocked":
        cooldown_text = "已解鎖"
        cooldown_note = f"可交易日期＝{_slash_date(next_tradable)}"
    else:
        cooldown_text = "尚未啟動"
        cooldown_note = "正式買入或賣出訊號成立後開始計算"
    return f"""
    <article class="private-strategy-card">
      <div class="private-card-head">
        <div>
          <span>{escape(str(item.get("pool_label", "")))}</span>
          <h2>{escape(str(item.get("mode_label", "")))}</h2>
        </div>
        <strong class="{action_class}">{escape(action_label)}</strong>
      </div>
      <div class="private-status-grid">
        <div><span>目前模擬部位</span><strong>{escape(position_text)}</strong><em>買入日 {escape(str(item.get("buy_date", "") or "無"))}</em></div>
        <div><span>今日判斷標的</span><strong>{escape(focus_text)}</strong><em>{escape(str(item.get("action_reason", "")))}</em></div>
        <div><span>隔日執行日</span><strong>{escape(str(item.get("next_execution_date", "") or "待確認"))}</strong><em>訊號資料日 {escape(str(item.get("signal_data_date", "") or "待確認"))}；報告日 {escape(str(item.get("report_date", "")))}</em></div>
        <div><span>符合買入 / 資料完整</span><strong>{int(item.get("candidate_count", 0) or 0)} / {ready_count}</strong><em>候選池 {pool_count} 檔；來源 {escape(source_date)}</em></div>
      </div>
      <div class="private-metric-groups">
        <section class="private-metric-group price-cd-group">
          <h3>收盤與交易限制</h3>
          <div class="private-metric-pair">
            <div><span>收盤</span><strong>{_formal_number(close_value)}</strong><em>今日訊號判斷價格</em></div>
            <div><span>CD{int(item.get("cooldown", 0) or 0)}</span><strong>{escape(cooldown_text)}</strong><em>{escape(cooldown_note)}</em></div>
          </div>
        </section>
        <section class="private-metric-group entry-group">
          <h3>進場區塊</h3>
          <div class="private-metric-pair">
            <div><span>進場 MA（{entry_ma_days}日）</span><strong>{_formal_number(entry_ma_value)}</strong><em>{'通過：收盤高於 MA' if entry_price_pass else '未通過：收盤需高於 MA'}</em></div>
            <div><span>近{entry_slope_days}日價格漲跌</span><strong>{_formal_pct(entry_slope_value)}</strong><em>今日收盤相對 {max(entry_slope_days - 1, 0)} 個交易日前；{'通過：上漲' if entry_slope_value > 0 else '未通過：需上漲'}</em></div>
          </div>
        </section>
        <section class="private-metric-group exit-group">
          <h3>出場區塊</h3>
          <div class="private-metric-pair">
            <div><span>出場 MA（{exit_ma_days}日）</span><strong>{_formal_number(exit_ma_value)}</strong><em>{'通過：收盤低於 MA' if exit_price_pass else '未通過：收盤需低於 MA'}</em></div>
            <div><span>近{exit_slope_days}日價格漲跌</span><strong>{_formal_pct(exit_slope_value)}</strong><em>今日收盤相對 {max(exit_slope_days - 1, 0)} 個交易日前；{'通過：下跌' if exit_slope_value < 0 else '未通過：需下跌'}</em></div>
          </div>
        </section>
      </div>
      <div class="private-candidates">
        <h3>今日進場候選排序</h3>
        <table><thead><tr><th>#</th><th>股票</th><th>收盤</th><th>近{entry_slope_days}日價格漲跌</th></tr></thead><tbody>{candidate_rows}</tbody></table>
      </div>
    </article>
    """


def _slash_date(value: str) -> str:
    if not value:
        return "待確認"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    return f"{parsed.year}/{parsed.month}/{parsed.day}"


def _group_stocks(stocks: list[StockResult]) -> dict[Bucket, list[StockResult]]:
    grouped: dict[Bucket, list[StockResult]] = defaultdict(list)
    for item in stocks:
        grouped[item.bucket].append(item)
    return grouped


def _formal_signal_panel(report: Report) -> str:
    signal = report.formal_signal
    if not signal:
        return ""
    blocked_dates = "、".join(_short_date(str(value)) for value in signal.get("blocked_trading_dates", [])) or "無"
    position = signal.get("actual_position", {}) or {}
    position_text = "持有 00631L" if position.get("asset_type") == "long_00631L" else "空手"
    average_price = position.get("average_price")
    average_text = f"均價 {float(average_price):.3f}" if average_price else "無持倉均價"
    signal_text = {
        "entry": "買入訊號",
        "exit": "賣出訊號",
        "none": "無新交易訊號",
        "conflict_blocked": "訊號衝突，禁止交易",
        "blocked_source": "資料未完成，禁止交易",
    }.get(str(signal.get("today_signal", "")), "狀態待確認")
    action_text = {
        "buy_00631L": "買入 00631L",
        "sell_00631L": "賣出 00631L",
        "hold_00631L": "續抱 00631L",
        "stay_flat": "維持空手",
        "cooldown_blocked_buy_00631L": "CD 封鎖：不得買入",
        "cooldown_blocked_sell_00631L": "CD 封鎖：不得賣出",
        "blocked_source": "資料未完成，禁止動作",
        "blocked_calendar_unavailable": "交易日曆不可用，禁止動作",
        "market_closed_no_signal": "市場休市，不產生動作",
        "blocked_signal": "訊號異常，禁止動作",
    }.get(str(signal.get("model_next_day_execution_action", "")), "狀態待確認")
    actual_trade_date = str(signal.get("actual_trade_date", "") or "無")
    actual_trade_action = str(signal.get("actual_trade_action", "") or "")
    report_date = str(signal.get("report_date", "") or "")
    today_signal = str(signal.get("today_signal", "") or "")
    if actual_trade_date == report_date and actual_trade_action == "buy" and today_signal != "entry":
        trade_alignment = "本日實際買進；不是本日模型買訊"
    elif actual_trade_date == report_date and actual_trade_action == "sell" and today_signal != "exit":
        trade_alignment = "本日實際賣出；不是本日模型賣訊"
    else:
        trade_alignment = "實際成交紀錄與模型訊號分欄"
    model_execution_date = str(signal.get("model_next_day_execution_date", "") or "待確認")
    next_tradable = str(signal.get("next_tradable_date", "") or "未受 CD 限制")
    remaining = int(signal.get("remaining_blocked_trading_days", 0) or 0)
    return f"""
    <section class="section formal-signal">
      <div class="formal-head">
        <div>
          <span>正式 0050 訊號 / 00631L 執行</span>
          <h2>{escape(str(signal.get("mode_label", "")))}</h2>
        </div>
        <strong>{escape(signal_text)}</strong>
      </div>
      <div class="formal-grid">
        <div><span>0050 今日收盤</span><strong>{_formal_number(signal.get("close"))}</strong><em>訊號標的</em></div>
        <div><span>MA4 / MA10</span><strong>{_formal_number(signal.get("ma4"))} / {_formal_number(signal.get("ma10"))}</strong><em>收盤均線</em></div>
        <div><span>7D slope（7筆）</span><strong>{_formal_signed(signal.get("slope_7d_value"))}</strong><em>相對6個交易日前 {_formal_pct(signal.get("slope_7d_pct"))}</em></div>
        <div><span>20D slope（20筆）</span><strong>{_formal_signed(signal.get("slope_20d_value"))}</strong><em>相對19個交易日前 {_formal_pct(signal.get("slope_20d_pct"))}</em></div>
        <div><span>次一交易日模型動作</span><strong>{escape(action_text)}</strong><em>{escape(model_execution_date)}</em></div>
        <div><span>00631L 實際部位</span><strong>{escape(position_text)}</strong><em>{escape(average_text)}，均價不參與訊號</em></div>
      </div>
      <div class="formal-cd">
        <p><b>實際成交日</b>{escape(actual_trade_date)} <small>{escape(trade_alignment)}</small></p>
        <p><b>CD blocked trading dates</b>{escape(blocked_dates)}</p>
        <p><b>Next tradable date</b>{escape(next_tradable)} <small>尚餘 {remaining} 個 blocked trading days</small></p>
        <p><b>Market session</b>{escape(str(signal.get("market_session_status", "unknown")))} <small>{escape(str(signal.get("market_session_source", "")))}</small></p>
      </div>
    </section>
    """


def _formal_number(value) -> str:
    return "資料待補" if value is None else f"{float(value):.2f}"


def _formal_signed(value) -> str:
    return "資料待補" if value is None else f"{float(value):+.2f}"


def _formal_pct(value) -> str:
    return "資料待補" if value is None else f"{float(value):+.2f}%"


def _rotation_digest(report: Report, top_sectors) -> str:
    sector_names = [item.metrics.name for item in top_sectors]
    leader = top_sectors[0] if top_sectors else None
    leader_name = leader.metrics.name if leader else "資料待補"
    top_text = "、".join(escape(name) for name in sector_names) if sector_names else "資料待補"

    flow_text = "今日題材資料仍在補齊，先以成交金額與題材占比觀察資金是否集中。"
    risk_text = "若熱門題材快速擴散到高本益比或高融資個股，短線容易出現追價與換手風險。"
    if leader:
        trend = _theme_trend(leader.metrics.name, report)
        days = int(float(trend.get("days", 0) or 0))
        heat = max(item.metrics.risk_heat for item in top_sectors)
        if days >= 5:
            flow_text = (
                f"近 5 個交易日資金主線以 {escape(leader_name)} 為核心；"
                f"{_rolling_share_sentence(trend, leader.metrics.capital_share, leader.metrics.capital_share_prev)}，"
                f"{_rolling_window_status(trend)}訊號優先觀察是否延續。"
            )
        elif days >= 2:
            flow_text = (
                f"系統正在回補近 5 個交易日資料，目前已取得 {days} 個交易日；"
                f"今日先看 {escape(leader_name)} 的資金占比（{_share_move_sentence(leader.metrics.capital_share, leader.metrics.capital_share_prev)}）與強勢股擴散。"
            )
        elif days == 1:
            flow_text = (
                f"目前只有 1 個交易日樣本，今日先看 {escape(leader_name)} 的成交集中度與強勢股擴散，"
                "不硬判斷五日趨勢。"
            )
        if heat >= 70:
            risk_text = "過熱分數偏高，代表短線交易已較擁擠；追高前要留意隔日量縮、開高走低或籌碼鬆動。"
        elif heat <= 40:
            risk_text = "過熱分數尚未失控，後續重點是成交量能否延續，而不是只看單日漲幅。"

    return f"""
    <section class="section digest">
      <div class="digest-title">
        <span>今日報告摘要</span>
        <strong>{top_text}</strong>
      </div>
      <div class="digest-grid">
        <p><b>資金主線</b>{flow_text}</p>
        <p><b>觀察重點</b>輪動報告看的是題材資金流向與短線活性，不等於買賣建議；若主流題材維持高占比，代表市場共識仍集中。</p>
        <p><b>風險提醒</b>{risk_text}</p>
      </div>
    </section>
    """


def _summary_panel(report: Report, top_sectors, buckets: dict[Bucket, list[StockResult]]) -> str:
    sector_text = " / ".join(escape(item.metrics.name) for item in top_sectors) or "資料待補"
    actionable = len(buckets.get(Bucket.ACTIONABLE, []))
    watch = min(len(buckets.get(Bucket.WATCH, [])), 3)
    excluded = min(len(buckets.get(Bucket.EXCLUDED, [])), 3)
    excluded_text = _excluded_summary_text(buckets.get(Bucket.EXCLUDED, []))
    return f"""
    <section class="section brief">
      <div class="brief-head">
        <span>今日輪動訊號</span>
        <strong>{sector_text}</strong>
      </div>
      <div class="brief-grid">
        <div><span>正向條件名單</span><strong>{actionable}</strong><em>正向條件較完整</em></div>
        <div><span>觀察名單</span><strong>{watch}</strong><em>報告保留前 3 名</em></div>
        <div><span>風險條件名單</span><strong>{excluded}</strong><em>{excluded_text}</em></div>
        <div><span>核心邏輯</span><strong>資金先行</strong><em>成交金額與題材占比優先</em></div>
        <div><span>報價資料</span><strong>{_quote_date_text(report)}</strong><em>{_quote_time_text(report)}</em></div>
        <div class="brief-wide"><span>明日觀察</span><strong>主線延續 / 擴散 / 過熱</strong><em>{_next_watch_summary(top_sectors)}</em></div>
      </div>
    </section>
    """


def _next_watch_summary(top_sectors) -> str:
    if not top_sectors:
        return "資料待補時先看成交金額與題材占比是否恢復穩定。"
    leader = top_sectors[0].metrics.name
    avg_strength = sum(item.metrics.strong_stock_ratio for item in top_sectors) / len(top_sectors)
    max_heat = max(item.metrics.risk_heat for item in top_sectors)
    return (
        f"{escape(leader)} 是否維持高成交占比；前三題材平均強勢股比例 {avg_strength:.0f}/100；"
        f"最高過熱分數 {max_heat:.0f}/100，越高越要留意追價與隔日換手。"
    )


def _excluded_summary_text(rows: list[StockResult]) -> str:
    names = [item.metrics.name for item in rows[:3]]
    if not names:
        return "暫無"
    return "、".join(escape(name) for name in names)


def _sector_card(item, rank: int, report: Report) -> str:
    metrics = item.metrics
    notes = "".join(f"<li>{escape(note)}</li>" for note in item.score.notes)
    catalysts = "".join(f"<span>{escape(text)}</span>" for text in metrics.catalysts)
    risks = "".join(f"<span>{escape(text)}</span>" for text in metrics.risks)
    turnover_delta = _pct_change(metrics.turnover_value, metrics.turnover_value_prev)
    turnover_text = "資料待補" if turnover_delta is None else f"{turnover_delta:+.1f}%"
    trend = _theme_trend(metrics.name, report)
    return f"""
      <article class="sector-card">
        <div class="card-top">
          <span class="card-label">輪動題材</span>
          <span class="rank-badge">第 {rank} 名</span>
        </div>
        <h3>{escape(metrics.name)}</h3>
        <p>{escape(metrics.theme)}</p>
        <div class="sector-stats">
          <div><span>資金占比</span><strong>{metrics.capital_share:.1f}%</strong><em>{_rolling_share_text(trend, metrics.capital_share, metrics.capital_share_prev)}</em></div>
          <div><span>成交金額</span><strong>{metrics.turnover_value:,.0f}百萬</strong><em>{turnover_text}</em></div>
          <div><span>近5日資金</span><strong>{_trend_amount(trend)}</strong><em>{_trend_days(trend)}</em></div>
          <div><span>5日占比趨勢</span><strong>{_rolling_window_status(trend)}</strong><em>{_rolling_window_detail(trend)}</em></div>
          <div><span>強勢股比例</span><strong>{metrics.strong_stock_ratio:.0f}/100</strong><em>越高越強</em></div>
          <div><span>過熱風險</span><strong>{metrics.risk_heat:.0f}/100</strong><em>越高越熱</em></div>
        </div>
        <ul>{notes}</ul>
        <div class="tag-row">{catalysts}</div>
        <div class="risk-row">{risks}</div>
      </article>
    """


def _stock_section(bucket: Bucket, buckets: dict[Bucket, list[StockResult]], report: Report) -> str:
    rows = buckets.get(bucket, [])
    total = len(rows)
    if bucket is Bucket.ACTIONABLE:
        rows = rows[:6]
    elif bucket is Bucket.WATCH:
        rows = rows[:3]
    elif bucket is Bucket.EXCLUDED:
        rows = rows[:3]
    if not rows:
        body = ""
    elif bucket is Bucket.EXCLUDED:
        body = '<div class="excluded-list">' + "".join(_excluded_item(item, index + 1) for index, item in enumerate(rows)) + "</div>"
    else:
        body = '<div class="stock-list">' + "".join(_stock_card(item, report, index + 1) for index, item in enumerate(rows)) + "</div>"
    note = _bucket_note(bucket, total, len(rows))
    bucket_class = _bucket_class(bucket)
    bucket_head = _bucket_header(bucket)
    if not rows:
        return f"""
      <div class="bucket bucket-empty {bucket_class}">
        {bucket_head}
        <p class="bucket-note">{note} 目前沒有符合條件的個股。</p>
      </div>
    """
    return f"""
      <div class="bucket {bucket_class}">
        {bucket_head}
        <p class="bucket-note">{note}</p>
        {body}
      </div>
    """


def _bucket_class(bucket: Bucket) -> str:
    if bucket is Bucket.ACTIONABLE:
        return "bucket-actionable"
    if bucket is Bucket.WATCH:
        return "bucket-watch"
    return "bucket-excluded"


def _bucket_header(bucket: Bucket) -> str:
    if bucket is Bucket.ACTIONABLE:
        kicker = "分類 1 / 條件最完整"
    elif bucket is Bucket.WATCH:
        kicker = "分類 2 / 接近條件"
    else:
        kicker = "分類 3 / 風險條件較多"
    return f"""
        <div class="bucket-head">
          <span>{kicker}</span>
          <h3>{bucket.value}</h3>
        </div>
    """


def _bucket_note(bucket: Bucket, total: int, shown: int) -> str:
    if bucket is Bucket.ACTIONABLE:
        return f"本區僅列正向條件較完整的前 6 檔，僅供觀察排序。共 {total} 檔，顯示 {shown} 檔。"
    if bucket is Bucket.WATCH:
        return f"觀察名單僅列前三名，重點看條件接近但尚未完整達標的股票。共 {total} 檔，顯示 {shown} 檔。"
    return f"風險條件名單保留摘要與主要原因，方便快速掃描風險。共 {total} 檔，顯示 {shown} 檔。"


def _excluded_item(item: StockResult, rank: int) -> str:
    m = item.metrics
    reason = item.score.notes[0] if item.score.notes else _risk_text(m.risk_reason)
    return f"""
      <div class="excluded-item">
        <strong>{rank}. {escape(m.name)} <small>{escape(m.symbol)}</small></strong>
        <span>收盤 {m.close:.1f} 元 / 本益比 {_pe_display(m.pe)}</span>
        <em>{escape(reason)}</em>
      </div>
    """


def _stock_card(item: StockResult, report: Report, rank: int) -> str:
    m = item.metrics
    notes = "".join(f"<li>{escape(note)}</li>" for note in item.score.notes[:2])
    pe_position = _pe_position(m.pe, m.sector_pe_low, m.sector_pe_high)
    fair_low, fair_avg, fair_high = _fair_values(m)
    chart = _chart_svg(report.price_history.get(m.symbol, []))
    pe_text = _pe_text(m, pe_position)
    theme_pills = _stock_theme_pills(item, report)
    return f"""
      <article class="stock-card">
        <div class="stock-left">
          <div class="stock-main">
            <div>
              <h4>{escape(m.name)} <small>{escape(m.symbol)}</small></h4>
              {theme_pills}
              <p>{escape(m.thesis)}</p>
            </div>
            <div class="rank-badge">第 {rank} 名</div>
          </div>
          <div class="metrics">
            <div><span>收盤價</span><strong>{m.close:.1f} 元</strong></div>
            <div><span>本益比</span><strong>{_pe_display(m.pe)}</strong></div>
            <div><span>題材本益比區間</span><strong>{_pe_range_display(m)}</strong></div>
            <div><span>題材平均本益比</span><strong>{_pe_display(m.sector_pe_avg)}</strong></div>
          </div>
          <div class="valuation-box">
            <span>題材本益比情境試算</span>
            <strong>{_fair_display(fair_low, fair_avg, fair_high)}</strong>
            <em>低檔 / 平均 / 高檔本益比情境</em>
          </div>
          <div class="pe-track" title="{escape(pe_text)}">
            <b>區間低檔</b><i style="left:calc(34px + (100% - 68px) * {pe_position:.1f} / 100)"></i><b>區間高檔</b>
          </div>
          <p class="hint">{escape(pe_text)}</p>
        </div>
        <div class="stock-side">
          {chart}
          <div class="chips">
            <span>{_foreign_chip(m)}</span>
            <span>{_trust_chip(m)}</span>
            <span>{_margin_chip(m)}</span>
          </div>
          <div class="side-notes">
            <ul>{notes}</ul>
            <p class="risk-text">風險：{escape(_risk_text(m.risk_reason))}</p>
          </div>
        </div>
      </article>
    """


def _stock_theme_pills(item: StockResult, report: Report) -> str:
    m = item.metrics
    hot_themes = {result.metrics.name for result in report.sector_results[:3]}
    themes = list(report.stock_themes.get(m.symbol, []))
    if m.sector and m.sector not in themes:
        themes.insert(0, m.sector)
    if not themes:
        themes = [m.sector]

    ordered = sorted(
        dict.fromkeys(theme for theme in themes if theme),
        key=lambda theme: (theme not in hot_themes, theme != m.sector, theme),
    )
    pills = []
    for theme in ordered[:6]:
        cls = "hot" if theme in hot_themes else "related"
        label = "熱門題材" if theme in hot_themes else "關聯題材"
        pills.append(f'<span class="theme-pill {cls}" title="{label}：{escape(theme)}">{escape(theme)}</span>')
    return f"""
            <div class="theme-pills" aria-label="題材標籤">
              {''.join(pills)}
            </div>
            <p class="theme-note">深色為本期熱門題材；淺色為這檔股票的其他關聯題材。</p>
    """


def _theme_trend(theme: str, report: Report) -> dict[str, float | str]:
    return report.theme_trends.get(theme, {"days": 0, "status": "資料待補"})


def _share_move_sentence(current: float, previous: float) -> str:
    if previous <= 0:
        return f"{current:.1f}%"
    return f"由前一交易日 {previous:.1f}% 變成今日 {current:.1f}%（{_relative_change_text(current, previous)}）"


def _share_change_text(current: float, previous: float) -> str:
    if previous <= 0:
        return "前一交易日資料待補"
    return f"前一交易日 {previous:.1f}% → 今日 {current:.1f}%"


def _rolling_share_sentence(trend: dict[str, float | str], current: float, previous: float) -> str:
    current_avg = float(trend.get("avg_share", 0) or 0)
    previous_avg = float(trend.get("previous_avg_share", 0) or 0)
    current_range = _trend_range_text(trend, "start_date", "latest_date")
    previous_range = _trend_range_text(trend, "previous_start_date", "previous_latest_date")
    if current_avg > 0 and previous_avg > 0 and current_range and previous_range:
        return (
            f"本期5日窗口（{current_range}）平均資金占比 {current_avg:.1f}%，"
            f"前一日窗口（{previous_range}）為 {previous_avg:.1f}%（{_relative_change_text(current_avg, previous_avg)}）"
        )
    return f"今日資金占比 {_share_move_sentence(current, previous)}"


def _rolling_share_text(trend: dict[str, float | str], current: float, previous: float) -> str:
    current_avg = float(trend.get("avg_share", 0) or 0)
    previous_avg = float(trend.get("previous_avg_share", 0) or 0)
    if current_avg > 0 and previous_avg > 0:
        return f"前一日5日窗 {previous_avg:.1f}% → 本期 {current_avg:.1f}%"
    return _share_change_text(current, previous)


def _rolling_window_status(trend: dict[str, float | str]) -> str:
    current_avg = float(trend.get("avg_share", 0) or 0)
    previous_avg = float(trend.get("previous_avg_share", 0) or 0)
    if current_avg <= 0 or previous_avg <= 0:
        return escape(str(trend.get("status", "今日觀察")))
    change = (current_avg - previous_avg) / previous_avg * 100
    if change >= 1:
        return "升溫"
    if change <= -1:
        return "降溫"
    return "持平"


def _rolling_window_detail(trend: dict[str, float | str]) -> str:
    current_avg = float(trend.get("avg_share", 0) or 0)
    previous_avg = float(trend.get("previous_avg_share", 0) or 0)
    if current_avg > 0 and previous_avg > 0:
        return f"5日窗{_relative_change_text(current_avg, previous_avg)}"
    return _trend_detail(trend)


def _trend_range_text(trend: dict[str, float | str], start_key: str, latest_key: str) -> str:
    start = str(trend.get(start_key, "") or "")
    latest = str(trend.get(latest_key, "") or "")
    if not start or not latest:
        return ""
    return f"{_short_date(start)}-{_short_date(latest)}"


def _relative_change_text(current: float, previous: float) -> str:
    change = (current - previous) / previous * 100
    if abs(change) < 0.05:
        return "幾乎持平"
    direction = "增加" if change > 0 else "減少"
    return f"{direction} {abs(change):.1f}%"


def _trend_amount(trend: dict[str, float | str]) -> str:
    days = float(trend.get("days", 0) or 0)
    if days <= 0:
        return "資料待補"
    amount = float(trend.get("amount_5d", 0) or 0)
    return f"{amount:,.0f}百萬"


def _trend_days(trend: dict[str, float | str]) -> str:
    days = int(float(trend.get("days", 0) or 0))
    if days <= 0:
        return "尚無可用交易日"
    latest = str(trend.get("latest_date", "") or "")
    suffix = f" 至 {_short_date(latest)}" if latest else ""
    if days >= 5:
        return f"近 5 個交易日{suffix}"
    return f"已回補 {days}/5 個交易日{suffix}"


def _trend_detail(trend: dict[str, float | str]) -> str:
    days = float(trend.get("days", 0) or 0)
    if days <= 0:
        return "等待歷史資料"
    if days < 2:
        return "單日樣本，先看集中度"
    rank_change = float(trend.get("rank_change", 0) or 0)
    amount_change = float(trend.get("amount_change_pct", 0) or 0)
    if rank_change > 0:
        rank_text = f"排名升{rank_change:.0f}"
    elif rank_change < 0:
        rank_text = f"排名降{abs(rank_change):.0f}"
    else:
        rank_text = "排名持平"
    return f"{rank_text}，金額{amount_change:+.0f}%"


def _quote_date_text(report: Report) -> str:
    if not report.quote_date:
        return "資料待補"
    raw = str(report.quote_date)
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return escape(raw)


def _quote_time_text(report: Report) -> str:
    return escape(report.quote_time or "請以此欄確認是否最新")


def _foreign_chip(m) -> str:
    if _institutional_missing(m):
        return "外資近5日：資料待補"
    return f"外資近5日：{_net_text(m.foreign_5d)}"


def _trust_chip(m) -> str:
    if _institutional_missing(m):
        return "投信近5日：資料待補"
    return f"投信近5日：{_net_text(m.trust_5d)}"


def _margin_chip(m) -> str:
    if _margin_missing(m):
        return "融資餘額近5日變化：資料待補"
    return f"融資餘額近5日變化：{m.margin_change_5d:+.1f}%"


def _institutional_missing(m) -> bool:
    return "missing_deep_data" in m.risk_reason or "missing_institutional" in m.risk_reason


def _margin_missing(m) -> bool:
    return "missing_deep_data" in m.risk_reason or "missing_margin" in m.risk_reason


def _chart_svg(rows: list[dict[str, float | str]]) -> str:
    rows = _recent_trading_window(_valid_chart_rows(rows), window_days=5)

    if not rows:
        return '<div class="chart-empty">最近 5 個可用交易日 K 線資料待補；接上每日 OHLC 後會顯示股價與 5/20/60 日均線。</div>'

    width, height = 360, 160
    left_pad, right_pad, top_pad, bottom_pad = 44, 14, 16, 36
    prices: list[float] = []
    for row in rows:
        prices.extend([float(row["high"]), float(row["low"]), _chart_number(row, "ma5"), _chart_number(row, "ma20"), _chart_number(row, "ma60")])
    low, high = min(prices), max(prices)
    padding = (high - low) * 0.08 or max(high * 0.03, 1)
    low -= padding
    high += padding
    span = high - low or 1

    def y(value: float) -> float:
        return top_pad + (high - value) / span * (height - top_pad - bottom_pad)

    chart_width = width - left_pad - right_pad
    chart_height = height - top_pad - bottom_pad
    step = chart_width / max(1, len(rows) - 1)
    candles = []
    ma5, ma20, ma60 = [], [], []
    for index, row in enumerate(rows):
        x = left_pad + index * step
        open_, close = float(row["open"]), float(row["close"])
        high_, low_ = float(row["high"]), float(row["low"])
        color = "#c0392b" if close >= open_ else "#177245"
        body_y = min(y(open_), y(close))
        body_h = max(2, abs(y(open_) - y(close)))
        candles.append(
            f'<line x1="{x:.1f}" y1="{y(high_):.1f}" x2="{x:.1f}" y2="{y(low_):.1f}" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{x - 3:.1f}" y="{body_y:.1f}" width="6" height="{body_h:.1f}" fill="{color}"/>'
        )
        ma5.append(f"{x:.1f},{y(_chart_number(row, 'ma5')):.1f}")
        ma20.append(f"{x:.1f},{y(_chart_number(row, 'ma20')):.1f}")
        ma60.append(f"{x:.1f},{y(_chart_number(row, 'ma60')):.1f}")

    y_ticks = [high - span * ratio for ratio in (0, 0.5, 1)]
    y_axis = "".join(
        f'<line x1="{left_pad}" y1="{y(value):.1f}" x2="{width - right_pad}" y2="{y(value):.1f}" stroke="#eef1f5"/>'
        f'<text x="{left_pad - 6}" y="{y(value) + 4:.1f}" text-anchor="end" font-size="10" fill="#667085">{value:.1f}</text>'
        for value in y_ticks
    )
    x_axis = "".join(
        f'<text x="{left_pad + index * step:.1f}" y="{height - 12}" text-anchor="middle" font-size="9" fill="#667085">{_short_date(str(row["date"]))}</text>'
        for index, row in enumerate(rows)
    )
    first_close = float(rows[0]["close"])
    last_close = float(rows[-1]["close"])
    change = (last_close - first_close) / first_close * 100 if first_close else 0.0
    latest = rows[-1]
    latest_date = _short_date(str(latest["date"]))
    first_date = _short_date(str(rows[0]["date"]))
    chart_title = f"近 5 個交易日 K（{first_date} 至 {latest_date}）"
    missing_note = _missing_trading_days_note(rows, window_days=5)

    return f"""
      <div class="chart">
        <div class="chart-head">
          <span>{chart_title} <small>{change:+.1f}%</small></span>
          <em>MA5 <strong>{_ma_value(latest, "ma5")}</strong></em>
          <em>MA20 <strong>{_ma_value(latest, "ma20")}</strong></em>
          <em>MA60 <strong>{_ma_value(latest, "ma60")}</strong></em>
        </div>
        {missing_note}
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="{chart_title}與均線">
          {y_axis}
          <line x1="{left_pad}" y1="{height - bottom_pad}" x2="{width - right_pad}" y2="{height - bottom_pad}" stroke="#d9dee7"/>
          <line x1="{left_pad}" y1="{top_pad}" x2="{left_pad}" y2="{height - bottom_pad}" stroke="#d9dee7"/>
          {''.join(candles)}
          <polyline points="{' '.join(ma5)}" fill="none" stroke="#e0a100" stroke-width="1.6"/>
          <polyline points="{' '.join(ma20)}" fill="none" stroke="#2673c9" stroke-width="1.6"/>
          <polyline points="{' '.join(ma60)}" fill="none" stroke="#7a4cc2" stroke-width="1.6"/>
          {x_axis}
        </svg>
      </div>
    """


def _valid_chart_rows(rows: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    valid_rows = []
    for row in rows:
        if not str(row.get("date", "")).strip():
            continue
        values = []
        for key in ("open", "high", "low", "close"):
            try:
                values.append(float(row.get(key, 0) or 0))
            except (TypeError, ValueError):
                values = []
                break
        if len(values) != 4 or any(value <= 0 for value in values):
            continue
        low = float(row["low"])
        high = float(row["high"])
        if low > min(float(row["open"]), float(row["close"])) or high < max(float(row["open"]), float(row["close"])):
            continue
        valid_rows.append(row)
    valid_rows.sort(key=lambda row: str(row.get("date", "")))
    return valid_rows


def _recent_trading_window(rows: list[dict[str, float | str]], window_days: int) -> list[dict[str, float | str]]:
    if not rows:
        return []
    latest_date = _parse_date(str(rows[-1].get("date", "")))
    if latest_date is None:
        return rows[-window_days:]
    expected = {_date_text(day) for day in _recent_weekdays(latest_date, window_days)}
    window_rows = [row for row in rows if str(row.get("date", "")) in expected]
    return window_rows[-window_days:]


def _missing_trading_days_note(rows: list[dict[str, float | str]], window_days: int) -> str:
    if not rows:
        return ""
    latest_date = _parse_date(str(rows[-1].get("date", "")))
    if latest_date is None:
        return ""
    expected = [_date_text(day) for day in _recent_weekdays(latest_date, window_days)]
    actual = {str(row.get("date", "")) for row in rows}
    missing = [date for date in expected if date not in actual]
    if not missing:
        return ""
    readable = "、".join(_short_date(date) for date in missing)
    return f'<small class="chart-note">缺少 {readable} 交易資料；系統會在後續產報時嘗試回補，不以更舊日期硬湊。</small>'


def _recent_weekdays(latest_date, window_days: int):
    days = []
    current = latest_date
    while len(days) < window_days:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return sorted(days)


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _date_text(value) -> str:
    return value.strftime("%Y-%m-%d")


def _ma_value(row: dict[str, float | str], key: str) -> str:
    value = _chart_number(row, key)
    return f"{value:.1f}" if value else "待補"


def _chart_number(row: dict[str, float | str], key: str) -> float:
    value = float(row.get(key, 0) or 0)
    if value > 0:
        return value
    return float(row.get("close", 0) or 0)


def _fair_values(m) -> tuple[float, float, float]:
    if m.fair_value_low and m.fair_value_avg and m.fair_value_high:
        return m.fair_value_low, m.fair_value_avg, m.fair_value_high
    if m.pe <= 0:
        return 0.0, 0.0, 0.0
    eps = m.close / m.pe
    return eps * m.sector_pe_low, eps * m.sector_pe_avg, eps * m.sector_pe_high


def _risk_text(value: str) -> str:
    cleaned = value
    replacements = {
        "深度資料狀態：missing_deep_data。": "法人與融資深度資料尚未完整接入。",
        "深度資料狀態：missing_margin。": "融資資料尚未完整接入。",
        "深度資料狀態：missing_institutional。": "法人買賣超資料尚未完整接入。",
    }
    for raw, readable in replacements.items():
        cleaned = cleaned.replace(raw, readable)
    cleaned = cleaned.replace("missing_deep_data", "法人與融資深度資料待補")
    cleaned = cleaned.replace("missing_margin", "融資資料待補")
    cleaned = cleaned.replace("missing_institutional", "法人資料待補")
    return " ".join(cleaned.split()) or "暫無重大風險註記"


def _pe_text(m, pe_position: float) -> str:
    if m.pe <= 0 or m.sector_pe_high <= 0:
        return "本益比位置：資料待補；此股目前是全市場初篩候選，尚未接入完整估值資料。"
    return f"本益比位置：題材區間第 {pe_position:.0f} 百分位；越左越接近區間低檔，越右越接近區間高檔。"


def _pe_display(value: float) -> str:
    if value <= 0:
        return "待補"
    return f"{value:.1f}x"


def _pe_range_display(m) -> str:
    if m.sector_pe_low <= 0 or m.sector_pe_high <= 0:
        return "待補"
    return f"{m.sector_pe_low:.1f}-{m.sector_pe_high:.1f}x"


def _fair_display(low: float, avg: float, high: float) -> str:
    if low <= 0 or avg <= 0 or high <= 0:
        return "估值資料待補"
    return f"{low:.1f} / {avg:.1f} / {high:.1f} 元"


def _net_text(value: float) -> str:
    if value > 0:
        return f"買超 {value:,.0f} 張"
    if value < 0:
        return f"賣超 {abs(value):,.0f} 張"
    return "0 張"


def _pe_position(pe: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (pe - low) / (high - low) * 100))


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def _short_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}/{int(parts[2])}"
    return value[-5:]


def _css() -> str:
    return """
:root {
  --bg: #f3f1ea;
  --paper: #fffdf8;
  --panel: #ffffff;
  --ink: #171717;
  --muted: #6f6a60;
  --line: #ddd6c8;
  --accent: #0f766e;
  --accent-2: #a16207;
  --risk: #b42318;
  --soft: #eef7f4;
  --warm: #fff5df;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; color: #171717; background: #f3f1ea; line-height: 1.58; }
.private-report { font-family: "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif; }
.hero { padding: 34px max(18px, 5vw) 20px; background: #171717; color: #fffdf8; border-bottom: 5px solid #d6a642; }
.hero-inner { max-width: 1120px; margin: 0 auto; }
.eyebrow { margin: 0 0 10px; color: #d6a642; font-size: .78rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }
h1 { margin: 0 0 12px; font-size: clamp(2rem, 5vw, 4.2rem); line-height: 1.04; letter-spacing: 0; }
.market-view { max-width: 880px; margin: 0; color: #e8e0cf; font-size: clamp(1rem, 2vw, 1.2rem); }
.stamp { margin: 14px 0 0; color: #bfb6a5; font-size: .9rem; }
main { padding: 22px max(14px, 4vw) 54px; }
.section { max-width: 1120px; margin: 0 auto 26px; }
.digest { background: #fffdf8; border: 1px solid #ddd6c8; border-radius: 8px; padding: 16px 18px; box-shadow: 0 10px 24px rgba(41, 32, 18, .07); }
.digest-title { display: flex; justify-content: space-between; gap: 18px; align-items: baseline; margin-bottom: 10px; }
.digest-title span { color: #a16207; font-size: .8rem; font-weight: 850; text-transform: uppercase; letter-spacing: .08em; }
.digest-title strong { font-size: 1.1rem; text-align: right; }
.digest-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.digest-grid p { margin: 0; color: #4a443d; font-size: .9rem; line-height: 1.55; }
.digest-grid b { display: block; color: #0f5f58; margin-bottom: 3px; }
.brief { margin-top: -8px; background: #fffdf8; border: 1px solid #ddd6c8; border-radius: 8px; padding: 18px; box-shadow: 0 10px 24px rgba(41, 32, 18, .07); }
.formal-signal { background: #132f2c; color: #fffdf8; border-left: 5px solid #d6a642; padding: 18px 20px; }
.formal-head { display: flex; justify-content: space-between; gap: 20px; align-items: end; border-bottom: 1px solid rgba(255,255,255,.2); padding-bottom: 12px; }
.formal-head span { color: #d6a642; font-size: .78rem; font-weight: 850; }
.formal-head h2 { margin-top: 4px; }
.formal-head > strong { color: #132f2c; background: #fff5df; padding: 7px 10px; font-size: 1rem; }
.formal-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 18px; }
.formal-grid > div { padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,.14); }
.formal-grid span, .formal-grid em { display: block; color: #c8d9d6; font-size: .76rem; font-style: normal; }
.formal-grid strong { display: block; font-size: 1.03rem; }
.formal-cd { padding-top: 10px; }
.formal-cd p { display: grid; grid-template-columns: 170px 1fr; gap: 8px; margin: 5px 0; font-size: .82rem; }
.formal-cd b { color: #d6a642; }
.formal-cd small { color: #c8d9d6; margin-left: 8px; }
.private-overview { max-width: 920px; }
.private-summary { background: #fffdf8; border: 1px solid #ddd6c8; border-left: 5px solid #d6a642; border-radius: 6px; padding: 14px 18px; margin-bottom: 14px; }
.private-summary span { color: #a16207; font-size: .78rem; font-weight: 850; }
.private-summary strong { display: block; font-size: 1.35rem; }
.private-summary p { margin: 4px 0 0; color: #6f6a60; }
.private-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.private-summary-item { background: #fffdf8; border: 1px solid #d8d3c8; border-top: 4px solid #0f5f58; border-radius: 6px; padding: 12px; }
.private-summary-item span { color: #a16207; font-size: .74rem; font-weight: 850; }
.private-summary-item h3 { margin: 4px 0 8px; font-size: .88rem; line-height: 1.35; }
.private-summary-item strong { display: block; color: #0f5f58; font-size: 1rem; }
.private-summary-item p, .private-summary-item em { display: block; margin: 3px 0 0; color: #6f6a60; font-size: .74rem; font-style: normal; }
.private-detail-title { margin: 4px 0 10px; }
.private-detail-page { break-before: page; page-break-before: always; padding-top: 4px; }
.private-detail-title span { color: #a16207; font-size: .78rem; font-weight: 850; }
.private-detail-title h2 { margin: 2px 0 0; font-size: 1.25rem; }
.private-strategy-card { background: #fffdf8; border: 1px solid #d8d3c8; border-radius: 7px; margin-bottom: 16px; overflow: hidden; break-inside: avoid; page-break-inside: avoid; }
.private-card-head { display: flex; justify-content: space-between; gap: 18px; align-items: center; padding: 16px 18px; background: #162a3a; color: #fff; border-bottom: 4px solid #d6a642; }
.private-card-head span { color: #d6a642; font-size: .8rem; font-weight: 850; }
.private-card-head h2 { margin-top: 4px; font-size: 1.16rem; }
.private-card-head > strong { min-width: 96px; text-align: center; padding: 7px 9px; border-radius: 4px; font-size: .94rem; }
.private-card-head .positive { color: #0f5f58; background: #dff5ee; }
.private-card-head .negative { color: #9f1d17; background: #ffe5e1; }
.private-card-head .neutral { color: #514b42; background: #f3eee4; }
.private-status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; padding: 0 18px; }
.private-status-grid > div { padding: 12px 10px 12px 0; border-bottom: 1px solid #e2ddd3; }
.private-status-grid span, .private-status-grid em { display: block; color: #6f6a60; font-size: .76rem; font-style: normal; }
.private-status-grid strong { display: block; font-size: 1.04rem; }
.private-metric-groups { display: grid; grid-template-columns: .95fr 1.25fr 1.25fr; gap: 10px; padding: 12px 18px; background: #f4f6f7; }
.private-metric-group { border: 1px solid #d8dfe3; border-top: 4px solid #6b7280; border-radius: 6px; padding: 9px; background: #fff; }
.private-metric-group h3 { margin: 0 0 7px; font-size: .82rem; }
.private-metric-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.private-metric-pair > div { border: 1px solid #e1e5e8; border-radius: 5px; padding: 7px; min-width: 0; }
.private-metric-pair span, .private-metric-pair em { display: block; color: #6f6a60; font-size: .67rem; font-style: normal; line-height: 1.35; }
.private-metric-pair strong { display: block; font-size: .87rem; line-height: 1.35; overflow-wrap: anywhere; }
.entry-group { border-color: #e2aaa6; border-top-color: #b42318; background: #fff8f7; }
.entry-group h3, .entry-group strong { color: #9f1d17; }
.exit-group { border-color: #9bd4c2; border-top-color: #0f766e; background: #f5fcf9; }
.exit-group h3, .exit-group strong { color: #0f5f58; }
.price-cd-group { background: #fbfbfa; }
.private-candidates { padding: 0 18px 16px; }
.private-candidates h3 { font-size: .96rem; margin: 12px 0 6px; }
.private-candidates table { width: 100%; font-size: .8rem; border-collapse: collapse; }
.private-candidates th, .private-candidates td { padding: 6px 8px; border-bottom: 1px solid #e2ddd3; text-align: left; }
.private-candidates th { color: #6f6a60; font-weight: 750; }
.private-footnote { color: #6f6a60; background: #fff; border: 1px solid #ddd6c8; border-radius: 6px; padding: 12px 16px; font-size: .78rem; }
.private-footnote b { color: #171717; }
.private-footnote p { margin: 3px 0 0; }
.brief-head { display: flex; justify-content: space-between; gap: 18px; align-items: baseline; border-bottom: 1px solid #ddd6c8; padding-bottom: 12px; }
.brief-head span { color: #a16207; font-size: .8rem; font-weight: 850; text-transform: uppercase; letter-spacing: .08em; }
.brief-head strong { font-size: clamp(1.15rem, 3vw, 2rem); text-align: right; }
.brief-grid { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 14px; }
.brief-grid > div { flex: 1 1 170px; }
.brief-grid .brief-wide { flex-basis: 350px; }
.brief-grid div, .sector-stats div, .metrics div, .valuation-box { background: #fff; border: 1px solid #ddd6c8; border-radius: 6px; padding: 10px; }
.brief-grid span, .sector-stats span, .metrics span, .valuation-box span { display: block; color: #6f6a60; font-size: .78rem; }
.brief-grid strong, .sector-stats strong, .metrics strong, .valuation-box strong { display: block; font-size: 1.05rem; }
.brief-grid em, .sector-stats em, .valuation-box em { display: block; color: #6f6a60; font-size: .76rem; font-style: normal; }
.section-head { display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 14px; padding-top: 4px; break-after: avoid; page-break-after: avoid; }
.section-head.compact { margin-bottom: 10px; }
h2 { margin: 0; font-size: 1.35rem; }
.section-head p, .hint { margin: 0; color: #6f6a60; max-width: 700px; }
.sector-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
.sector-card, .stock-card, .method-grid div { background: #fffdf8; border: 1px solid #ddd6c8; border-radius: 8px; box-shadow: 0 8px 20px rgba(41, 32, 18, .055); }
.sector-card, .stock-card { padding: 15px; }
.sector-card { min-width: 0; }
.card-top, .stock-main { display: flex; justify-content: space-between; gap: 14px; align-items: start; }
.card-label { font-weight: 800; color: #a16207; font-size: .78rem; letter-spacing: .05em; }
.rank-badge { white-space: nowrap; color: #0d4f49; background: #eef7f4; border: 1px solid #c9e7e1; border-radius: 999px; padding: 5px 10px; font-weight: 850; font-size: .86rem; }
h3, h4 { margin: 8px 0 6px; }
h3 { font-size: 1.34rem; }
h4 { font-size: 1.16rem; }
small { color: #6f6a60; font-size: .85rem; }
.sector-card p, .stock-card p { color: #6f6a60; margin: 0 0 12px; }
.sector-stats, .metrics { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.sector-stats > div, .metrics > div { flex: 1 1 145px; }
ul { padding-left: 18px; margin: 12px 0; color: #38332c; }
.tag-row, .risk-row, .chips, .theme-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-row span, .chips span, .sector-pill { background: #eef7f4; color: #0f5f58; border-radius: 999px; padding: 4px 8px; font-size: .82rem; font-weight: 700; }
.theme-pills { margin: 2px 0 6px; }
.theme-pill { border-radius: 999px; padding: 4px 9px; font-size: .78rem; font-weight: 850; line-height: 1.35; border: 1px solid transparent; }
.theme-pill.hot { background: #0f5f58; color: #fffdf8; border-color: #0f5f58; }
.theme-pill.related { background: #fff; color: #6f6a60; border-color: #ddd6c8; }
.stock-card .theme-note { margin: 0 0 10px; color: #6f6a60; font-size: .76rem; line-height: 1.45; }
.risk-row { margin-top: 8px; }
.risk-row span { color: #b42318; background: #fff0ee; border-radius: 999px; padding: 4px 8px; font-size: .82rem; }
.bucket { margin-top: 22px; padding: 0 14px 14px; border-radius: 12px; border: 1px solid #ddd6c8; overflow: hidden; background: #fffdf8; }
.bucket-actionable { border-color: #d8b56f; }
.bucket-watch { border-color: #a9d4cb; }
.bucket-excluded { border-color: #e0aaa1; }
.bucket-head { margin: 0 -14px 12px; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.bucket-head span { font-size: .76rem; font-weight: 850; letter-spacing: .06em; }
.bucket-head h3 { margin: 0; font-size: 1.34rem; line-height: 1.2; }
.bucket-actionable .bucket-head { background: #a16207; color: #fffdf8; }
.bucket-watch .bucket-head { background: #0f766e; color: #fffdf8; }
.bucket-excluded .bucket-head { background: #b42318; color: #fffdf8; }
.bucket-note { margin: 0 0 10px; color: #6f6a60; font-size: .82rem; }
.stock-list { display: flex; flex-wrap: wrap; gap: 12px; }
.stock-card { flex: 1 1 470px; }
.excluded-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.excluded-item { background: #fffdf8; border: 1px solid #e2c8c2; border-radius: 8px; padding: 12px; }
.excluded-item strong, .excluded-item span, .excluded-item em { display: block; }
.excluded-item span { color: #6f6a60; font-size: .82rem; margin: 4px 0; }
.excluded-item em { color: #b42318; font-size: .82rem; font-style: normal; }
.valuation-box { margin-bottom: 12px; background: #fffaf0; }
.pe-track { height: 18px; position: relative; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; color: #6f6a60; font-size: .76rem; }
.pe-track:before { content: ""; position: absolute; left: 34px; right: 34px; top: 8px; height: 6px; border-radius: 999px; background: linear-gradient(90deg, #18886f, #d6a642, #c2410c); }
.pe-track i { position: absolute; top: 2px; width: 4px; height: 18px; background: #111; border-radius: 2px; transform: translateX(-2px); }
.hint { font-size: .78rem; margin: 4px 0 10px; }
.chart, .chart-empty { margin-top: 12px; border: 1px solid #ddd6c8; border-radius: 6px; padding: 8px; background: #fff; }
.chart svg { width: 100%; height: auto; display: block; }
.chart-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: .78rem; color: #6f6a60; }
.chart-head span { font-weight: 800; color: #171717; margin-right: auto; }
.chart-head em { font-style: normal; }
.chart-head em strong { font-weight: 850; }
.chart-head em:nth-child(2) { color: #d69b00; }
.chart-head em:nth-child(3) { color: #2563eb; }
.chart-head em:nth-child(4) { color: #7c3aed; }
.chart-note { display: block; margin-top: 4px; color: #6f6a60; font-size: .74rem; }
.chart-empty { color: #6f6a60; font-size: .86rem; }
.risk-text { color: #b42318 !important; font-weight: 700; }
.method-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.method-grid div { padding: 14px; }
.method-grid div { flex: 1 1 230px; }
.method-grid strong { display: block; margin-bottom: 6px; }
.method-grid span { color: #6f6a60; }
.empty { color: #6f6a60; }
@media (max-width: 980px) {
  .sector-grid, .digest-grid, .excluded-list, .formal-grid, .private-status-grid, .private-summary-grid { grid-template-columns: 1fr; }
  .section-head { display: block; }
  .section-head p { margin-top: 6px; }
}
@media (max-width: 620px) {
  .hero { padding: 28px 16px 18px; }
  main { padding: 16px 10px 38px; }
  .digest-title { display: block; }
  .digest-title strong { display: block; text-align: left; margin-top: 6px; }
  .brief-head { display: block; }
  .brief-head strong { display: block; text-align: left; margin-top: 6px; }
  .formal-head { display: block; }
  .formal-head > strong { display: inline-block; margin-top: 8px; }
  .formal-cd p { display: block; }
  .private-card-head { display: block; }
  .private-card-head > strong { display: inline-block; margin-top: 8px; }
  .private-metric-groups { grid-template-columns: 1fr; }
  .stock-main { align-items: start; }
  .metrics, .sector-stats { grid-template-columns: 1fr 1fr; }
}
@media print {
  @page { size: A4; margin: 9mm; }
  body { background: #fffdf8; line-height: 1.45; }
  .hero { padding: 22px 28px 14px; }
  h1 { font-size: 2.8rem; margin-bottom: 8px; }
  .market-view { font-size: 1rem; max-width: 940px; }
  main { padding: 14px 18px 26px; }
  .section { margin-bottom: 16px; }
  .digest, .brief { padding: 13px 14px; }
  .brief-grid div, .sector-stats div, .metrics div, .valuation-box { padding: 8px; }
  .sector-card, .stock-card { padding: 12px; }
  .brief-grid .brief-wide { flex-basis: 340px; }
  .sector-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
  .sector-section { break-before: page; page-break-before: always; }
  .stock-section { break-before: page; page-break-before: always; }
  .sector-section .section-head { display: block; margin-bottom: 8px; break-inside: avoid; page-break-inside: avoid; }
  .sector-section .section-head p { margin-top: 4px; max-width: none; font-size: .76rem; line-height: 1.35; }
  .sector-card { padding: 9px; }
  .sector-card h3 { font-size: 1rem; margin: 4px 0; }
  .sector-card p { font-size: .68rem; line-height: 1.28; margin-bottom: 5px; }
  .sector-stats { gap: 5px; margin: 7px 0; }
  .sector-stats > div { flex-basis: 92px; padding: 6px; }
  .sector-stats span, .sector-stats em { font-size: .62rem; }
  .sector-stats strong { font-size: .86rem; }
  .sector-card ul { font-size: .66rem; line-height: 1.28; margin: 6px 0; }
  .sector-card .tag-row, .sector-card .risk-row { gap: 4px; }
  .tag-row span, .risk-row span { font-size: .72rem; padding: 3px 6px; }
  .stock-list { display: block; }
  .stock-card {
    width: 100%;
    margin-bottom: 10px;
    display: grid;
    grid-template-columns: minmax(0, 1.08fr) minmax(260px, .92fr);
    gap: 7px 12px;
    align-items: start;
  }
  .stock-left { grid-column: 1; }
  .stock-side { grid-column: 2; }
  .stock-card .chart, .stock-card .chart-empty { margin-top: 0; }
  .stock-card .chips { margin-top: 5px; }
  .stock-card .side-notes { margin-top: 5px; }
  .stock-card .side-notes ul { margin: 4px 0; padding-left: 15px; }
  .stock-card h4 { font-size: 1.02rem; margin: 4px 0; }
  .stock-card p, .stock-card ul { font-size: .72rem; line-height: 1.32; }
  .stock-card small, .stock-card .theme-pill, .stock-card .rank-badge, .stock-card .chips span { font-size: .7rem; }
  .stock-card .metrics > div { flex-basis: 118px; }
  .stock-card .valuation-box, .stock-card .hint { font-size: .7rem; line-height: 1.32; }
  .stock-card .pe-track { height: 14px; margin-top: 4px; font-size: .66rem; }
  .stock-card .pe-track, .stock-card .hint, .stock-card .valuation-box em { display: none; }
  .stock-card .chart svg { height: 92px; }
  .stock-card .chart-note { display: none; }
  .section-head, .bucket-head, .bucket-note { break-after: avoid; page-break-after: avoid; }
  .sector-card, .stock-card, .digest, .brief, .chart, .excluded-item { break-inside: avoid; page-break-inside: avoid; }
  .bucket { break-inside: auto; page-break-inside: auto; margin-top: 12px; padding: 0 10px 9px; }
  .bucket-empty { margin-top: 8px; }
  .bucket-head { margin: 0 -10px 7px; padding: 7px 10px; }
  .bucket-head h3, .bucket-empty .bucket-head h3 { font-size: 1.12rem; }
  .bucket-head span { font-size: .66rem; }
  .bucket-empty .bucket-note { margin-bottom: 4px; }
  .excluded-list { gap: 7px; }
  .excluded-item { padding: 8px; font-size: .72rem; }
  .excluded-item span, .excluded-item em { font-size: .68rem; }
  .stock-card .theme-note { display: none; }
  .stock-card p { margin-bottom: 8px; }
  .metrics, .sector-stats { margin: 9px 0; }
  .valuation-box { margin-bottom: 8px; }
  .chart { margin-top: 8px; padding: 6px; }
  .chart-head { font-size: .72rem; gap: 7px; }
  .hint, .bucket-note { font-size: .72rem; }
  ul { margin: 8px 0; }
  .risk-text { margin-bottom: 0 !important; }
}
"""
