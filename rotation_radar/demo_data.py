from __future__ import annotations

from .models import SectorMetrics, StockMetrics


def demo_sectors() -> list[SectorMetrics]:
    return [
        SectorMetrics(
            name="記憶體",
            theme="HBM、DDR4/DDR5 報價與 AI 伺服器需求",
            capital_inflow_rank=88,
            turnover_share_change=82,
            momentum_20d=80,
            strong_stock_ratio=76,
            industry_trend=90,
            overseas_signal=92,
            pe_percentile=58,
            risk_heat=64,
            catalysts=["SK hynix、Micron 等海外記憶體指標偏強", "HBM 與 DDR 報價循環仍是主線"],
            risks=["短線漲幅已大，利多鈍化時容易震盪", "部分模組股籌碼可能轉熱"],
        ),
        SectorMetrics(
            name="PCB/載板",
            theme="AI 伺服器、高階板材、ABF 載板與 CCL",
            capital_inflow_rank=84,
            turnover_share_change=79,
            momentum_20d=78,
            strong_stock_ratio=73,
            industry_trend=88,
            overseas_signal=80,
            pe_percentile=52,
            risk_heat=58,
            catalysts=["AI 伺服器層數提升帶動高階 PCB 需求", "載板與材料缺口支撐報價"],
            risks=["原物料價格與良率影響毛利", "高位階個股需等拉回"],
        ),
        SectorMetrics(
            name="CPO/矽光子",
            theme="800G/1.6T 光通訊與資料中心升級",
            capital_inflow_rank=73,
            turnover_share_change=70,
            momentum_20d=74,
            strong_stock_ratio=68,
            industry_trend=86,
            overseas_signal=84,
            pe_percentile=70,
            risk_heat=72,
            catalysts=["AI 資料中心高速傳輸需求提升", "美股光通訊鏈仍具題材"],
            risks=["估值較高且題材股波動大", "營收實現時間差需追蹤"],
        ),
        SectorMetrics(
            name="被動元件",
            theme="AI 電源規格升級、車用與高階 MLCC",
            capital_inflow_rank=66,
            turnover_share_change=64,
            momentum_20d=62,
            strong_stock_ratio=58,
            industry_trend=74,
            overseas_signal=61,
            pe_percentile=44,
            risk_heat=46,
            catalysts=["高階應用推升產品組合", "若漲價題材延續，資金有補漲空間"],
            risks=["族群整齊度尚不如記憶體與 PCB", "需確認月營收與報價趨勢"],
        ),
    ]


def demo_stocks() -> list[StockMetrics]:
    return [
        StockMetrics("2408", "南亞科", "記憶體", 138.0, 62, 68, 12000, 1800, 9.5, 24.0, 18.0, 31.0, 46.0, 42.0, 8.0, 66, 95, 70, "DRAM 報價循環受惠，但需等拉回確認", "短線漲幅偏大，追價風險較高"),
        StockMetrics("2344", "華邦電", "記憶體", 35.2, 74, 72, 8500, 2400, 5.2, 21.0, 18.0, 31.0, 46.0, 28.0, 6.5, 73, 92, 54, "利基型記憶體與報價循環受惠，拉回後較適合觀察", "需追蹤毛利率修復速度"),
        StockMetrics("8299", "群聯", "記憶體", 812.0, 67, 76, 2600, 900, 3.5, 17.5, 12.0, 24.0, 36.0, 34.0, 7.0, 70, 84, 48, "控制 IC 與 NAND 循環受惠，估值位置相對不貴", "高價股波動較大"),
        StockMetrics("3037", "欣興", "PCB/載板", 238.5, 72, 70, 6200, 3100, 6.0, 19.0, 15.0, 25.0, 39.0, 21.0, 5.0, 75, 98, 50, "ABF 與 AI 載板需求提供中期支撐", "若量能異常，風險條件增加"),
        StockMetrics("8046", "南電", "PCB/載板", 318.0, 70, 66, 3300, 1800, 8.0, 22.0, 15.0, 25.0, 39.0, 18.0, 4.2, 71, 82, 52, "載板修復與 AI 題材並行", "融資增加需持續觀察"),
        StockMetrics("2368", "金像電", "PCB/載板", 410.0, 58, 62, 2800, 1200, 13.8, 31.0, 15.0, 25.0, 39.0, 26.0, 9.0, 64, 91, 75, "AI 伺服器 PCB 長線邏輯佳", "估值與融資熱度偏高，風險條件較多"),
        StockMetrics("3163", "波若威", "CPO/矽光子", 198.0, 55, 57, 1400, 400, 16.0, 48.0, 28.0, 43.0, 70.0, 20.0, 3.5, 62, 74, 82, "CPO 題材強，但需要營收落地與籌碼降溫", "題材波動大且短線過熱"),
        StockMetrics("2327", "國巨", "被動元件", 302.0, 76, 73, 3900, 2500, 2.0, 16.0, 13.0, 21.0, 32.0, 12.0, 2.5, 69, 99, 40, "被動元件龍頭，估值與籌碼條件相對穩定", "題材資金強度仍需放大"),
        StockMetrics("2492", "華新科", "被動元件", 158.5, 69, 64, 1800, 900, 7.0, 18.5, 13.0, 21.0, 32.0, 10.0, 1.8, 66, 72, 48, "若被動元件補漲，具持續觀察價值", "營收動能尚未完全確認"),
    ]
