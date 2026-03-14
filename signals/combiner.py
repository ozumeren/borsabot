from typing import Optional
from dataclasses import dataclass, field
from signals.technical_signal import TechnicalSignal, Direction
from config.constants import (
    TECHNICAL_WEIGHT, SENTIMENT_WEIGHT, MARKET_DATA_WEIGHT,
    CRYPTOPANIC_WEIGHT, FEAR_GREED_WEIGHT,
)


@dataclass
class FinalSignal:
    direction: Direction
    combined_score: float
    technical_score: float
    sentiment_score: float
    market_score: float
    coin: str
    entry_price: float
    reasons: list[str] = field(default_factory=list)
    atr: float = 0.0          # volatilite bazlı pozisyon boyutu + trailing stop için
    leverage: int = 5         # dinamik kaldıraç (calculate_leverage tarafından doldurulur)
    adx: float = 0.0          # trend gücü — stop çarpanını etkiler
    bb_width_pct: float = 0.0 # BB bant genişliği / fiyat — squeeze tespiti için

    @property
    def is_actionable(self) -> bool:
        return self.direction != Direction.NONE


class SignalCombiner:
    """
    Teknik (%55) + Sentiment (%25) + Piyasa Verisi (%20) birleştirme.

    Sentiment  = CryptoPanic (%60) + Fear&Greed (%40)
    Piyasa     = Funding Rate (%60) + Long/Short Oranı (%40)

    Funding Rate contrarian: yüksek pozitif → SHORT, yüksek negatif → LONG
    Fear & Greed contrarian: Extreme Fear → LONG, Extreme Greed → SHORT
    """

    def __init__(self, min_combined_score: float = 0.55, trade_logger=None):
        self.min_combined_score = min_combined_score
        self.trade_logger = trade_logger  # dinamik skor için opsiyonel

    def combine(
        self,
        technical: TechnicalSignal,
        cryptopanic_score: float,      # -1.0 → +1.0
        fear_greed_index: int,          # 0 → 100
        market_signal: float = 0.0,    # -1.0 → +1.0 (FundingSnapshot.combined_market_signal)
        coin: str = "",
        entry_price: float = 0.0,
        atr: float = 0.0,
        leverage: int = 5,             # calculate_leverage'dan gelir
    ) -> FinalSignal:

        _none = FinalSignal(Direction.NONE, 0.0, 0.0, 0.0, 0.0, coin, entry_price, atr=atr, leverage=leverage)

        if technical.direction == Direction.NONE:
            return _none

        is_long = (technical.direction == Direction.LONG)

        def norm(raw: float) -> float:
            """[-1,+1] → [0,1] yöne göre."""
            v = (raw + 1.0) / 2.0
            return v if is_long else (1.0 - v)

        # ── Sentiment ─────────────────────────────────────────────────────────
        cp_norm = norm(cryptopanic_score)
        fg_raw  = fear_greed_index / 100.0
        fg_norm = (1.0 - fg_raw) if is_long else fg_raw   # contrarian
        sentiment = cp_norm * CRYPTOPANIC_WEIGHT + fg_norm * FEAR_GREED_WEIGHT

        # ── Piyasa verisi (funding + L/S) ─────────────────────────────────────
        market_norm = norm(market_signal)

        # ── Birleşik skor ─────────────────────────────────────────────────────
        combined = (
            technical.score  * TECHNICAL_WEIGHT +
            sentiment        * SENTIMENT_WEIGHT +
            market_norm      * MARKET_DATA_WEIGHT
        )

        # ── Confluence bonusu ─────────────────────────────────────────────────
        # ≥4 indikatör aynı yönde → +0.05
        if technical.indicator_count >= 4:
            combined += 0.05
        # BB + RSI aynı yönde → +0.03
        if technical.bb_aligned and technical.rsi_aligned:
            combined += 0.03

        # Güçlü CryptoPanic çelişkisi → engelle
        if (is_long and cryptopanic_score < -0.4) or \
           (not is_long and cryptopanic_score > 0.4):
            return FinalSignal(
                Direction.NONE, combined, technical.score,
                sentiment, market_norm, coin, entry_price,
                ["Sentiment teknik sinyalle çelişiyor"], atr=atr, leverage=leverage,
            )

        # ── Dinamik minimum skor ──────────────────────────────────────────────
        min_score = self.min_combined_score
        if self.trade_logger is not None:
            win_rate = self.trade_logger.get_recent_win_rate(last_n=20)
            if win_rate is not None:
                if win_rate < 0.40:
                    min_score = 0.65   # düşük win rate → daha seçici
                elif win_rate > 0.65:
                    min_score = 0.52   # yüksek win rate → biraz gevşet

        if combined >= min_score:
            reasons = technical.reasons + [
                f"Sentiment: {sentiment:.2f}",
                f"Fear&Greed: {fear_greed_index}",
                f"Piyasa (funding/LS): {market_norm:.2f}",
                f"Kaldıraç: {leverage}x",
            ]
            if technical.indicator_count >= 4:
                reasons.append(f"Confluence bonusu: {technical.indicator_count} indikatör")
            return FinalSignal(
                direction=technical.direction,
                combined_score=combined,
                technical_score=technical.score,
                sentiment_score=sentiment,
                market_score=market_norm,
                coin=coin,
                entry_price=entry_price,
                reasons=reasons,
                atr=atr,
                leverage=leverage,
            )

        return FinalSignal(Direction.NONE, combined, technical.score,
                           sentiment, market_norm, coin, entry_price, atr=atr, leverage=leverage)
