from __future__ import annotations

from .models import Bucket, ScoreBreakdown, SectorMetrics, SectorResult, StockMetrics, StockResult


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def score_sector(metrics: SectorMetrics) -> SectorResult:
    capital = clamp(metrics.capital_inflow_rank * 0.65 + metrics.turnover_share_change * 0.35)
    momentum = clamp(metrics.momentum_20d * 0.55 + metrics.strong_stock_ratio * 0.45)
    trend = clamp(metrics.industry_trend)
    overseas = clamp(metrics.overseas_signal)
    valuation = clamp(100 - abs(metrics.pe_percentile - 45) * 1.35)
    risk = clamp(100 - metrics.risk_heat)

    parts = {
        "資金流入": capital * 0.45,
        "價格動能": momentum * 0.15,
        "題材趨勢": trend * 0.10,
        "海外行情": overseas * 0.10,
        "估值合理": valuation * 0.10,
        "風險控管": risk * 0.10,
    }
    total = round(sum(parts.values()), 1)

    notes: list[str] = []
    if capital >= 75:
        notes.append(_capital_note(metrics))
    if trend >= 80:
        notes.append(f"題材趨勢分數 {trend:.0f}/100，主線具中期延續性")
    if overseas >= 75:
        notes.append(f"海外行情同步分數 {overseas:.0f}/100，對應指標偏強")
    if metrics.risk_heat >= 70:
        notes.append(f"短線過熱風險 {metrics.risk_heat:.0f}/100，追價風險升高")
    if not notes:
        notes.append("題材條件中性，等待資金或基本面訊號放大")

    return SectorResult(metrics=metrics, score=ScoreBreakdown(total=total, parts=parts, notes=notes))


def _capital_note(metrics: SectorMetrics) -> str:
    share_delta = metrics.capital_share - metrics.capital_share_prev
    turnover_delta = _pct_change(metrics.turnover_value, metrics.turnover_value_prev)
    if metrics.capital_share > 0 and metrics.capital_share_prev > 0 and turnover_delta is not None:
        return (
            f"資金占比 {metrics.capital_share:.1f}%（前期 {metrics.capital_share_prev:.1f}%，"
            f"變化 {share_delta:+.1f} 個百分點），成交金額 {metrics.turnover_value:,.0f} 百萬元"
            f"（前期 {metrics.turnover_value_prev:,.0f} 百萬元，{turnover_delta:+.1f}%）"
        )
    return f"資金流入分數 {metrics.capital_inflow_rank:.0f}/100，成交活性分數 {metrics.turnover_share_change:.0f}/100"


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def score_stock(metrics: StockMetrics) -> StockResult:
    valuation_position = _valuation_position_score(metrics)
    chip = clamp(metrics.chip_cleanliness)
    pullback = clamp(metrics.pullback_quality)
    fundamental = clamp(_fundamental_score(metrics.revenue_yoy, metrics.revenue_mom))
    technical = clamp(metrics.technical_setup)
    liquidity = clamp(metrics.liquidity)
    risk_penalty = _risk_penalty(metrics)

    parts = {
        "拉回買點": pullback * 0.20,
        "籌碼乾淨": chip * 0.20,
        "估值位置": valuation_position * 0.20,
        "基本面": fundamental * 0.15,
        "技術結構": technical * 0.15,
        "流動性": liquidity * 0.10,
    }
    total = round(clamp(sum(parts.values()) - risk_penalty), 1)
    notes = _stock_notes(metrics, valuation_position, risk_penalty)
    bucket = classify_stock(total, metrics, valuation_position)

    return StockResult(
        metrics=metrics,
        score=ScoreBreakdown(total=total, parts=parts, notes=notes),
        bucket=bucket,
    )


def classify_stock(total: float, metrics: StockMetrics, valuation_position: float) -> Bucket:
    if metrics.risk_heat >= 82 or metrics.liquidity < 45:
        return Bucket.EXCLUDED
    if valuation_position < 25 and metrics.pullback_quality < 72:
        return Bucket.EXCLUDED
    if total >= 72 and metrics.pullback_quality >= 70 and metrics.chip_cleanliness >= 68:
        return Bucket.ACTIONABLE
    if total >= 58:
        return Bucket.WATCH
    return Bucket.EXCLUDED


def _valuation_position_score(metrics: StockMetrics) -> float:
    if metrics.pe <= 0 or metrics.sector_pe_high <= metrics.sector_pe_low:
        return 45.0

    span = metrics.sector_pe_high - metrics.sector_pe_low
    percentile = (metrics.pe - metrics.sector_pe_low) / span * 100
    relative_to_avg = metrics.pe / metrics.sector_pe_avg if metrics.sector_pe_avg else 1.0

    low_range_bonus = 100 - percentile
    avg_discount_bonus = clamp((1.25 - relative_to_avg) * 100)
    return clamp(low_range_bonus * 0.65 + avg_discount_bonus * 0.35)


def _fundamental_score(revenue_yoy: float, revenue_mom: float) -> float:
    yoy_score = clamp(50 + revenue_yoy * 1.2)
    mom_score = clamp(50 + revenue_mom * 2.0)
    return yoy_score * 0.7 + mom_score * 0.3


def _risk_penalty(metrics: StockMetrics) -> float:
    penalty = 0.0
    if metrics.risk_heat > 65:
        penalty += (metrics.risk_heat - 65) * 0.35
    if metrics.margin_change_5d > 12:
        penalty += min(10, (metrics.margin_change_5d - 12) * 0.8)
    if metrics.pe > metrics.sector_pe_high * 0.95:
        penalty += 7
    return penalty


def _stock_notes(metrics: StockMetrics, valuation_position: float, risk_penalty: float) -> list[str]:
    notes: list[str] = []
    if metrics.pullback_quality >= 70:
        notes.append("拉回位置相對健康，符合波段找買點方向")
    if metrics.chip_cleanliness >= 70:
        notes.append("籌碼條件偏乾淨")
    if valuation_position >= 70:
        notes.append("本益比位於題材相對低檔")
    elif valuation_position < 45:
        notes.append("估值已不便宜")
    if metrics.foreign_5d > 0 and metrics.trust_5d > 0:
        notes.append("外資與投信近五日同步買超")
    if metrics.margin_change_5d > 12:
        notes.append("融資增加偏快，籌碼風險上升")
    if risk_penalty > 0:
        notes.append("已因短線過熱或籌碼風險扣分")
    if not notes:
        notes.append("條件中性，等待更明確的量價或籌碼訊號")
    return notes


def build_results(sectors: list[SectorMetrics], stocks: list[StockMetrics]) -> tuple[list[SectorResult], list[StockResult]]:
    sector_results = sorted((score_sector(item) for item in sectors), key=lambda item: item.score.total, reverse=True)
    stock_results = sorted((score_stock(item) for item in stocks), key=lambda item: item.score.total, reverse=True)
    return sector_results, stock_results
