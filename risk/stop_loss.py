from __future__ import annotations
from typing import Optional
from signals.technical_signal import Direction
from config.constants import DEFAULT_RISK_REWARD, MIN_STOP_DISTANCE_PCT


class StopLossCalculator:
    """
    Volatilite-adaptif stop-loss ve take-profit hesaplar.

    Stop mesafesi üç katmanlı dinamik mantıkla belirlenir:

    1. ATR çarpanı (ADX'e göre):
       ADX < 20  → ×1.2  (yatay piyasa, dar stop — gereksiz kayıptan kaçın)
       ADX 20-40 → ×1.5  (normal trend)
       ADX ≥ 40  → ×2.0  (güçlü trend, stop hunting'e karşı geniş stop)

    2. BB squeeze düzeltmesi:
       BB genişliği < %3 (squeeze) → çarpanı en fazla ×1.2'ye indir.
       Patlama öncesi aşama: stop zaten ATR-bazlı olarak dar kalır.

    3. Dinamik tavan:
       max(ATR × 2.0, %4) — sabit %4 tavan yerine ATR'a bağlı tavan.
       Yüksek volatilite coinlerde (DOGE, PEPE vb.) stopun %4'te kırpılıp
       stop hunting'e maruz kalmasını önler.
    """

    def __init__(self, default_stop_pct: float = 0.015):
        self.default_stop_pct = default_stop_pct

    def calculate_stop_loss(
        self,
        direction: Direction,
        entry_price: float,
        atr: Optional[float] = None,
        adx: float = 0.0,
        bb_width_pct: float = 0.0,
    ) -> float:
        pct = self._resolve_stop_pct(entry_price, atr, adx, bb_width_pct)
        if direction == Direction.LONG:
            return entry_price * (1.0 - pct)
        else:
            return entry_price * (1.0 + pct)

    def calculate_take_profit(
        self,
        direction: Direction,
        entry_price: float,
        stop_loss_price: float,
        rr_ratio: float = DEFAULT_RISK_REWARD,
    ) -> float:
        stop_dist = abs(entry_price - stop_loss_price)
        tp_dist   = stop_dist * rr_ratio
        if direction == Direction.LONG:
            return entry_price + tp_dist
        else:
            return entry_price - tp_dist

    def _resolve_stop_pct(
        self,
        entry_price: float,
        atr: Optional[float],
        adx: float = 0.0,
        bb_width_pct: float = 0.0,
    ) -> float:
        if atr is None or entry_price <= 0:
            return self.default_stop_pct

        atr_pct = atr / entry_price

        # 1. ADX bazlı çarpan
        if adx >= 40:
            multiplier = 2.0   # güçlü trend → stop hunting'e karşı geniş mesafe
        elif adx >= 20:
            multiplier = 1.5   # normal trend
        else:
            multiplier = 1.2   # yatay piyasa → dar stop, gereksiz risk alma

        # 2. BB squeeze düzeltmesi: bant %3'ten darsa, henüz patlama olmamış
        #    çarpanı kısıtla — stop çok geniş açılmasın
        if 0 < bb_width_pct < 0.03:
            multiplier = min(multiplier, 1.2)

        dynamic = max(atr_pct * multiplier, self.default_stop_pct)

        # 3. Dinamik tavan: ATR × 2.0 veya %4 (hangisi büyükse)
        #    Sabit %4 tavan yüksek-vol coinlerde stop hunting'e davetiye çıkarır.
        ceiling = max(atr_pct * 2.0, 0.04)
        return min(dynamic, ceiling)
