"""Shared display-score helper — ADX filtresi bypass edilmiş gösterim skoru."""
from __future__ import annotations


def display_score(iv) -> float:
    """ADX filtresi olmadan ham teknik skor — sadece gösterim için."""
    ls, ss = display_scores(iv)
    return max(ls, ss)


def display_scores(iv) -> tuple[float, float]:
    """ADX filtresi olmadan ham LONG/SHORT teknik skorlar."""
    ls = ss = 0.0
    # RSI
    if iv.rsi < 25:    ls += 0.20
    elif iv.rsi < 45:  ls += 0.10
    if iv.rsi > 75:    ss += 0.20
    elif iv.rsi > 55:  ss += 0.10
    # MACD crossover
    if iv.macd_hist_prev <= 0 and iv.macd_hist > 0:   ls += 0.20
    elif iv.macd_hist > 0:                             ls += 0.08
    if iv.macd_hist_prev >= 0 and iv.macd_hist < 0:   ss += 0.20
    elif iv.macd_hist < 0:                             ss += 0.08
    # EMA çapraz
    if iv.ema_short > iv.ema_long:   ls += 0.15
    else:                            ss += 0.15
    # Bollinger
    if iv.bb_pct < 0.20:    ls += 0.15
    elif iv.bb_pct > 0.80:  ss += 0.15
    # SMA200
    if iv.close > iv.sma_long:   ls += 0.08
    else:                        ss += 0.08
    # Hacim
    if iv.is_volume_spike:   ls += 0.05; ss += 0.05  # noqa: E702
    # Price Action
    ls += iv.pa_bull_score * 0.20
    ss += iv.pa_bear_score * 0.20
    return round(min(1.0, ls), 3), round(min(1.0, ss), 3)
