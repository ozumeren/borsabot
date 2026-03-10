from dataclasses import dataclass, field
from enum import Enum
from indicators.technical import IndicatorValues
from config.constants import RSI_OVERSOLD, RSI_OVERBOUGHT, EMA_SHORT, EMA_LONG


class Direction(Enum):
    LONG  = "long"
    SHORT = "short"
    NONE  = "none"


@dataclass
class TechnicalSignal:
    direction: Direction
    score: float              # 0.0 – 1.0
    reasons: list[str] = field(default_factory=list)


class TechnicalSignalGenerator:
    """
    İndikatörlerden teknik sinyal üretir.

    Puanlama (her koşul ağırlıklı toplam, max 1.0):
      RSI          : 0.20
      MACD         : 0.20
      EMA trend    : 0.20
      BB bantları  : 0.20
      SMA200 filtre: 0.10
      Hacim spike  : 0.10
    """

    def __init__(self, min_score: float = 0.6):
        self.min_score = min_score

    def generate(self, iv: IndicatorValues) -> TechnicalSignal:
        long_score  = 0.0
        short_score = 0.0
        long_reasons:  list[str] = []
        short_reasons: list[str] = []

        # ── RSI (0.20) ────────────────────────────────────────────────────────
        if iv.rsi < RSI_OVERSOLD:
            long_score += 0.20
            long_reasons.append(f"RSI aşırı satım: {iv.rsi:.1f}")
        elif iv.rsi < 45:
            long_score += 0.10
            long_reasons.append(f"RSI zayıf: {iv.rsi:.1f}")

        if iv.rsi > RSI_OVERBOUGHT:
            short_score += 0.20
            short_reasons.append(f"RSI aşırı alım: {iv.rsi:.1f}")
        elif iv.rsi > 55:
            short_score += 0.10
            short_reasons.append(f"RSI yüksek: {iv.rsi:.1f}")

        # ── MACD histogram crossover (0.20) ───────────────────────────────────
        if iv.macd_hist > 0 and iv.macd_line > iv.macd_signal:
            long_score += 0.20
            long_reasons.append("MACD bullish crossover")
        if iv.macd_hist < 0 and iv.macd_line < iv.macd_signal:
            short_score += 0.20
            short_reasons.append("MACD bearish crossover")

        # ── EMA trend (0.20) ──────────────────────────────────────────────────
        if iv.ema_short > iv.ema_long:
            long_score  += 0.20
            long_reasons.append(f"EMA{EMA_SHORT}>{EMA_LONG} yükselen trend")
        else:
            short_score += 0.20
            short_reasons.append(f"EMA{EMA_SHORT}<{EMA_LONG} düşen trend")

        # ── Bollinger Bands (0.20) ────────────────────────────────────────────
        if iv.bb_pct < 0.05:
            long_score += 0.20
            long_reasons.append(f"Fiyat BB alt bandında (bb_pct={iv.bb_pct:.2f})")
        if iv.bb_pct > 0.95:
            short_score += 0.20
            short_reasons.append(f"Fiyat BB üst bandında (bb_pct={iv.bb_pct:.2f})")

        # ── SMA200 makro filtre (0.10) ────────────────────────────────────────
        if iv.close > iv.sma_long:
            long_score  += 0.10
            long_reasons.append("SMA200 üzerinde (bullish makro)")
        else:
            short_score += 0.10
            short_reasons.append("SMA200 altında (bearish makro)")

        # ── Hacim spike (0.10) ────────────────────────────────────────────────
        if iv.is_volume_spike:
            # Trend onayı için her iki tarafa da ekle
            long_score  += 0.05
            short_score += 0.05
            long_reasons.append("Hacim spike")
            short_reasons.append("Hacim spike")

        # ── Karar ────────────────────────────────────────────────────────────
        # Çakışan sinyal: her iki yön de güçlüyse → NONE
        if long_score >= 0.50 and short_score >= 0.50:
            return TechnicalSignal(Direction.NONE, max(long_score, short_score),
                                   ["Çakışan sinyal - işlem yok"])

        if long_score >= self.min_score and long_score > short_score:
            return TechnicalSignal(Direction.LONG, long_score, long_reasons)

        if short_score >= self.min_score and short_score > long_score:
            return TechnicalSignal(Direction.SHORT, short_score, short_reasons)

        return TechnicalSignal(Direction.NONE, max(long_score, short_score))
