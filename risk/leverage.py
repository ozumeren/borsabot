"""
Dinamik kaldıraç hesaplama.

Sinyal gücüne, ADX trend gücüne ve volatiliteye göre
base_leverage'dan maksimum max_leverage'a kadar karar verir.

Mantık:
  - Sinyal güçlü (combined_score ≥ 0.80) → +2x
  - Sinyal orta  (combined_score ≥ 0.70) → +1x
  - ADX güçlü trend (≥ 40)              → +1x
  - Volatilite düşük (ATR/price < 0.5%) → +1x
  - Volatilite orta  (ATR/price > 2.0%) → -1x
  - Volatilite yüksek(ATR/price > 3.0%) → -2x
  - Clamp: [min_leverage, max_leverage]
"""
from utils.logger import get_logger

logger = get_logger("risk.leverage")

MIN_LEVERAGE = 2
MAX_LEVERAGE = 10


def calculate_leverage(
    combined_score: float,
    adx: float,
    atr: float,
    price: float,
    base_leverage: int = 5,
    max_leverage: int = MAX_LEVERAGE,
) -> int:
    """
    Dinamik kaldıraç belirler.

    Parametreler
    ------------
    combined_score : FinalSignal.combined_score  (0.0 – 1.0+)
    adx            : IndicatorValues.adx
    atr            : IndicatorValues.atr
    price          : Giriş fiyatı
    base_leverage  : Taban kaldıraç (varsayılan: settings.leverage = 5)
    max_leverage   : Maksimum izin verilen kaldıraç (varsayılan: 10)

    Döndürür
    --------
    int — hesaplanan kaldıraç [MIN_LEVERAGE, max_leverage] aralığında
    """
    lev = base_leverage

    # ── Sinyal gücü bonusu ────────────────────────────────────────────────────
    if combined_score >= 0.80:
        lev += 2
    elif combined_score >= 0.70:
        lev += 1

    # ── ADX güçlü trend bonusu ────────────────────────────────────────────────
    if adx >= 40:
        lev += 1

    # ── Volatilite ayarlaması ─────────────────────────────────────────────────
    if price > 0 and atr > 0:
        vol_pct = atr / price
        if vol_pct > 0.030:
            lev -= 2   # çok yüksek volatilite → kaldıracı düşür
        elif vol_pct > 0.020:
            lev -= 1   # yüksek volatilite
        elif vol_pct < 0.005:
            lev += 1   # çok düşük volatilite → biraz artır

    result = max(MIN_LEVERAGE, min(max_leverage, lev))

    logger.debug(
        "Kaldıraç hesaplandı",
        combined_score=f"{combined_score:.2f}",
        adx=f"{adx:.1f}",
        vol_pct=f"{(atr/price*100) if price > 0 and atr > 0 else 0:.2f}%",
        base=base_leverage,
        result=result,
    )

    return result
