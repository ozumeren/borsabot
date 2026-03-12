from __future__ import annotations
from typing import Optional
from signals.technical_signal import Direction
from config.constants import DEFAULT_RISK_REWARD, MIN_STOP_DISTANCE_PCT


class StopLossCalculator:
    """
    5x kaldıraç için stop-loss ve take-profit hesaplar.

    Önemli: 5x kaldıraçta %20 fiyat hareketi = %100 margin kaybı (likidite).
    %1.5 stop → marginin %7.5'i kayıp → güvenli mesafe.
    ATR kullanılabiliyorsa dinamik stop üretir.
    """

    def __init__(self, default_stop_pct: float = 0.015):
        self.default_stop_pct = default_stop_pct

    def calculate_stop_loss(
        self,
        direction: Direction,
        entry_price: float,
        atr: Optional[float] = None,
    ) -> float:
        pct = self._resolve_stop_pct(entry_price, atr)

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

    def _resolve_stop_pct(self, entry_price: float, atr: Optional[float]) -> float:
        if atr is not None and entry_price > 0:
            atr_pct = atr / entry_price
            # ATR × 1.5 kullan; default_stop_pct alt taban, %4 üst tavan
            dynamic = max(atr_pct * 1.5, self.default_stop_pct)
            return min(dynamic, 0.04)
        return self.default_stop_pct
