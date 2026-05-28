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
      <p class="eyebrow">被AI研究社 | Rotation Radar</p>
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
        <h2>短線波段名單</h2>
        <p>策略偏好：拉回找買點，其次是低本益比與籌碼轉強；個股題材標籤中，深色代表本期前三大熱門題材，淺色代表同股關聯題材。</p>
      </div>
      {_stock_section(Bucket.ACTIONABLE, buckets, report)}
      {_stock_section(Bucket.WATCH, buckets, report)}
      {_stock_section(Bucket.EXCLUDED, buckets, report)}
    </section>
    {_next_watch_panel(top_sectors)}
  </main>
</body>
</html>"""


def _group_stocks(stocks: list[StockResult]) -> dict[Bucket, list[StockResult]]:
    grouped: dict[Bucket, list[StockResult]] = defaultdict(list)
    for item in stocks:
        grouped[item.bucket].append(item)
    return grouped


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
                f"{escape(str(trend.get('status', '持平')))}訊號優先觀察是否延續。"
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
    return f"""
    <section class="section brief">
      <div class="brief-head">
        <span>今日輪動訊號</span>
        <strong>{sector_text}</strong>
      </div>
      <div class="brief-grid">
        <div><span>可操作名單</span><strong>{actionable}</strong><em>符合波段條件</em></div>
        <div><span>觀察名單</span><strong>{watch}</strong><em>報告保留前 3 名</em></div>
        <div><span>排除名單</span><strong>{excluded}</strong><em>摘要列出前 3 名</em></div>
        <div><span>核心邏輯</span><strong>資金先行</strong><em>成交金額與題材占比優先</em></div>
        <div><span>報價資料</span><strong>{_quote_date_text(report)}</strong><em>{_quote_time_text(report)}</em></div>
      </div>
    </section>
    """


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
          <div><span>5日短趨勢</span><strong>{escape(str(trend.get("status", "今日觀察")))}</strong><em>{_trend_detail(trend)}</em></div>
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
        body = '<p class="empty">目前沒有符合條件的個股。</p>'
    elif bucket is Bucket.EXCLUDED:
        body = '<div class="excluded-list">' + "".join(_excluded_item(item, index + 1) for index, item in enumerate(rows)) + "</div>"
    else:
        body = '<div class="stock-list">' + "".join(_stock_card(item, report, index + 1) for index, item in enumerate(rows)) + "</div>"
    note = _bucket_note(bucket, total, len(rows))
    return f"""
      <div class="bucket">
        <h3>{bucket.value}</h3>
        <p class="bucket-note">{note}</p>
        {body}
      </div>
    """


def _next_watch_panel(top_sectors) -> str:
    if not top_sectors:
        return ""
    leader = top_sectors[0].metrics
    crowded = max(item.metrics.risk_heat for item in top_sectors)
    breadth = sum(item.metrics.strong_stock_ratio for item in top_sectors) / len(top_sectors)
    return f"""
    <section class="section next-watch">
      <div class="section-head compact">
        <h2>明日觀察重點</h2>
        <p>補足日報最後一段判讀：只作市場觀察與風險提醒，不作買賣建議。</p>
      </div>
      <div class="watch-grid">
        <div><strong>主線延續</strong><span>{escape(leader.name)} 若維持高成交占比，代表資金仍集中在同一題材主線。</span></div>
        <div><strong>擴散程度</strong><span>前三題材平均強勢股比例 {breadth:.0f}/100；若下降，代表行情可能從普漲轉成挑股。</span></div>
        <div><strong>過熱開關</strong><span>最高過熱分數 {crowded:.0f}/100；越高越要留意追價、量縮與隔日換手風險。</span></div>
      </div>
    </section>
    """


def _bucket_note(bucket: Bucket, total: int, shown: int) -> str:
    if bucket is Bucket.ACTIONABLE:
        return f"本區僅列波段條件最完整的前 6 檔，降低雜訊。共 {total} 檔，顯示 {shown} 檔。"
    if bucket is Bucket.WATCH:
        return f"觀察名單僅列前三名，重點看條件接近但尚未完整達標的股票。共 {total} 檔，顯示 {shown} 檔。"
    return f"排除名單保留摘要與主要原因，方便快速掃描風險。共 {total} 檔，顯示 {shown} 檔。"


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
          <span>合理估值推估</span>
          <strong>{_fair_display(fair_low, fair_avg, fair_high)}</strong>
          <em>低檔 / 平均 / 高檔本益比推估</em>
        </div>
        <div class="pe-track" title="{escape(pe_text)}">
          <b>低估</b><i style="left:calc(34px + (100% - 68px) * {pe_position:.1f} / 100)"></i><b>高估</b>
        </div>
        <p class="hint">{escape(pe_text)}</p>
        <div class="chips">
          <span>{_foreign_chip(m)}</span>
          <span>{_trust_chip(m)}</span>
          <span>{_margin_chip(m)}</span>
        </div>
        {chart}
        <ul>{notes}</ul>
        <p class="risk-text">風險：{escape(_risk_text(m.risk_reason))}</p>
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
    return f"本益比位置：題材區間第 {pe_position:.0f} 百分位；越左代表越便宜，越右代表越接近高估。"


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
.brief-head { display: flex; justify-content: space-between; gap: 18px; align-items: baseline; border-bottom: 1px solid #ddd6c8; padding-bottom: 12px; }
.brief-head span { color: #a16207; font-size: .8rem; font-weight: 850; text-transform: uppercase; letter-spacing: .08em; }
.brief-head strong { font-size: clamp(1.15rem, 3vw, 2rem); text-align: right; }
.brief-grid { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 14px; }
.brief-grid > div { flex: 1 1 170px; }
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
.bucket { margin-top: 20px; }
.bucket > h3 { border-left: 5px solid #a16207; padding-left: 10px; }
.bucket-note { margin: -2px 0 10px; color: #6f6a60; font-size: .82rem; }
.stock-list { display: flex; flex-wrap: wrap; gap: 12px; }
.stock-card { flex: 1 1 470px; }
.excluded-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.excluded-item { background: #fffdf8; border: 1px solid #ddd6c8; border-radius: 8px; padding: 12px; }
.excluded-item strong, .excluded-item span, .excluded-item em { display: block; }
.excluded-item span { color: #6f6a60; font-size: .82rem; margin: 4px 0; }
.excluded-item em { color: #b42318; font-size: .82rem; font-style: normal; }
.next-watch { background: #fffdf8; border: 1px solid #ddd6c8; border-radius: 8px; padding: 14px 16px; }
.watch-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.watch-grid div { background: #fff; border: 1px solid #ddd6c8; border-radius: 6px; padding: 10px; }
.watch-grid strong { display: block; color: #0f5f58; margin-bottom: 4px; }
.watch-grid span { color: #4a443d; font-size: .88rem; }
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
  .sector-grid, .digest-grid, .excluded-list, .watch-grid { grid-template-columns: 1fr; }
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
  .sector-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
  .sector-section { break-inside: avoid; page-break-inside: avoid; }
  .sector-card h3 { font-size: 1.12rem; }
  .sector-card p { font-size: .78rem; margin-bottom: 8px; }
  .sector-stats { gap: 6px; margin: 10px 0; }
  .sector-stats > div { flex-basis: 104px; }
  .sector-card ul { font-size: .75rem; }
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
  .stock-main, .metrics, .valuation-box, .pe-track, .hint, .chips, .stock-card ul, .risk-text { grid-column: 1; }
  .stock-card .chart, .stock-card .chart-empty { grid-column: 2; grid-row: 1 / span 8; margin-top: 0; }
  .section-head, .bucket > h3, .bucket-note { break-after: avoid; page-break-after: avoid; }
  .sector-card, .stock-card, .digest, .brief, .chart, .excluded-item, .next-watch { break-inside: avoid; page-break-inside: avoid; }
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
