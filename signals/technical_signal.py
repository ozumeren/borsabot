from dataclasses import dataclass, field
from enum import Enum
from indicators.technical import IndicatorValues
from config.constants import RSI_OVERSOLD, RSI_OVERBOUGHT, EMA_SHORT, EMA_LONG, ADX_TREND_THRESHOLD, ADX_STRONG_TREND


class Direction(Enum):
    LONG  = "long"
    SHORT = "short"
    NONE  = "none"


@dataclass
class TechnicalSignal:
    direction: Direction
    score: float              # 0.0 – 1.0
    reasons: list[str] = field(default_factory=list)
    indicator_count: int = 0  # Kazanan yönde tam puan veren indikatör sayısı
    rsi_aligned: bool = False  # RSI kendi yönünde tam sinyal verdi mi
    bb_aligned: bool = False   # BB kendi yönünde tam sinyal verdi mi


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
        # ── ADX Trend Güç Filtresi ────────────────────────────────────────────
        if iv.adx > 0 and iv.adx < ADX_TREND_THRESHOLD:
            return TechnicalSignal(
                Direction.NONE, 0.0,
                [f"ADX {iv.adx:.1f} < {ADX_TREND_THRESHOLD} — yatay piyasa, sinyal geçersiz"]
            )

        adx_bonus = 0.05 if iv.adx >= ADX_STRONG_TREND else 0.0

        long_score  = 0.0
        short_score = 0.0
        long_reasons:  list[str] = []
        short_reasons: list[str] = []
        long_count  = 0   # tam sinyal veren indikatör sayısı
        short_count = 0

        # ── RSI (0.20) ────────────────────────────────────────────────────────
        rsi_long = rsi_short = False
        if iv.rsi < RSI_OVERSOLD:
            long_score += 0.20; long_count += 1; rsi_long = True
            long_reasons.append(f"RSI aşırı satım: {iv.rsi:.1f}")
        elif iv.rsi < 45:
            long_score += 0.10
            long_reasons.append(f"RSI zayıf: {iv.rsi:.1f}")

        if iv.rsi > RSI_OVERBOUGHT:
            short_score += 0.20; short_count += 1; rsi_short = True
            short_reasons.append(f"RSI aşırı alım: {iv.rsi:.1f}")
        elif iv.rsi > 55:
            short_score += 0.10
            short_reasons.append(f"RSI yüksek: {iv.rsi:.1f}")

        # ── MACD histogram crossover (0.20) ───────────────────────────────────
        # Gerçek crossover: önceki mum negatif, şimdiki pozitif (veya tersi)
        if iv.macd_hist_prev <= 0 and iv.macd_hist > 0:
            long_score += 0.20; long_count += 1
            long_reasons.append("MACD bullish crossover")
        elif iv.macd_hist > 0:
            long_score += 0.08   # momentum devam ediyor ama crossover değil
            long_reasons.append(f"MACD pozitif momentum ({iv.macd_hist:.4f})")

        if iv.macd_hist_prev >= 0 and iv.macd_hist < 0:
            short_score += 0.20; short_count += 1
            short_reasons.append("MACD bearish crossover")
        elif iv.macd_hist < 0:
            short_score += 0.08
            short_reasons.append(f"MACD negatif momentum ({iv.macd_hist:.4f})")

        # ── EMA trend (0.20) ──────────────────────────────────────────────────
        ema_spread = abs(iv.ema_short - iv.ema_long) / iv.ema_long if iv.ema_long > 0 else 0.0
        if iv.ema_short > iv.ema_long:
            if ema_spread >= 0.003:  # EMA'lar ayrışmış → güçlü trend
                long_score  += 0.20; long_count += 1
                long_reasons.append(f"EMA{EMA_SHORT}>{EMA_LONG} yükselen trend ({ema_spread:.2%})")
            else:  # EMA'lar çok yakın → zayıf trend, kısmi puan
                long_score  += 0.08
                long_reasons.append(f"EMA{EMA_SHORT}>{EMA_LONG} (zayıf spread: {ema_spread:.2%})")
        else:
            if ema_spread >= 0.003:
                short_score += 0.20; short_count += 1
                short_reasons.append(f"EMA{EMA_SHORT}<{EMA_LONG} düşen trend ({ema_spread:.2%})")
            else:
                short_score += 0.08
                short_reasons.append(f"EMA{EMA_SHORT}<{EMA_LONG} (zayıf spread: {ema_spread:.2%})")

        # ── Bollinger Bands (0.20) ────────────────────────────────────────────
        bb_long = bb_short = False
        if iv.bb_pct < 0.05:
            long_score += 0.20; long_count += 1; bb_long = True
            long_reasons.append(f"Fiyat BB alt bandında (bb_pct={iv.bb_pct:.2f})")
        if iv.bb_pct > 0.95:
            short_score += 0.20; short_count += 1; bb_short = True
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
            long_score  += 0.05
            short_score += 0.05
            long_reasons.append("Hacim spike")
            short_reasons.append("Hacim spike")

        # ── OBV teyidi / ıraksaması ────────────────────────────────────────────
        # OBV yön teyidi: +0.05 bonus; ıraksama (zıt yön): -0.05 ceza
        if iv.obv_slope > 0.01:
            long_score  += 0.05
            short_score -= 0.03
            long_reasons.append(f"OBV yükselen trend ({iv.obv_slope:.2f})")
        elif iv.obv_slope < -0.01:
            short_score += 0.05
            long_score  -= 0.03
            short_reasons.append(f"OBV düşen trend ({iv.obv_slope:.2f})")

        # ── ADX güçlü trend bonusu — yalnızca baskın yöne ────────────────────
        if adx_bonus:
            if long_score >= short_score:
                long_score  += adx_bonus
                long_reasons.append(f"ADX güçlü trend: {iv.adx:.1f}")
            else:
                short_score += adx_bonus
                short_reasons.append(f"ADX güçlü trend: {iv.adx:.1f}")

        # ── Karar ────────────────────────────────────────────────────────────
        if long_score >= 0.50 and short_score >= 0.50:
            return TechnicalSignal(Direction.NONE, max(long_score, short_score),
                                   ["Çakışan sinyal - işlem yok"])

        if long_score >= self.min_score and long_score > short_score:
            return TechnicalSignal(
                Direction.LONG, long_score, long_reasons,
                indicator_count=long_count,
                rsi_aligned=rsi_long,
                bb_aligned=bb_long,
            )

        if short_score >= self.min_score and short_score > long_score:
            return TechnicalSignal(
                Direction.SHORT, short_score, short_reasons,
                indicator_count=short_count,
                rsi_aligned=rsi_short,
                bb_aligned=bb_short,
            )

        return TechnicalSignal(Direction.NONE, max(long_score, short_score))
