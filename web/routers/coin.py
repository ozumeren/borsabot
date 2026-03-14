"""Coin detay endpoint — çoklu zaman dilimi analizi, 1 saatlik önbellek."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from config.constants import (
    TECHNICAL_WEIGHT, SENTIMENT_WEIGHT, MARKET_DATA_WEIGHT,
    CRYPTOPANIC_WEIGHT, FEAR_GREED_WEIGHT,
)

router = APIRouter()
_engine: Any = None

_cache: dict[str, dict] = {}   # {coin: {"data": {...}, "expires_at": datetime}}
CACHE_TTL = timedelta(hours=1)

# (timeframe_key, label, limit, okx_tf)
TIMEFRAMES = [
    ("1h", "1 Saat",  200, "1h"),
    ("1d", "1 Gün",   200, "1d"),
    ("1w", "1 Hafta", 100, "1w"),
    ("1M", "1 Ay",     60, "1M"),
]


def _display_score(iv) -> float:
    """ADX filtresi olmadan ham teknik skor — sadece gösterim için."""
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
    return round(min(1.0, max(ls, ss)), 3)


async def _analyze_tf(coin: str, okx_tf: str, limit: int) -> Optional[dict]:
    try:
        symbol = f"{coin}-USDT-SWAP"
        df = await asyncio.to_thread(
            _engine.market_data.fetch_ohlcv, symbol, okx_tf, limit=limit
        )
        if df is None or df.empty or len(df) < 20:
            return None

        iv = await asyncio.to_thread(_engine.tech_analyzer.compute, df)
        signal = _engine.tech_sig_gen.generate(iv)
        # ADX filtresi devredeyse score=0 döner — ham skoru kullan
        score = float(getattr(signal, "score", 0) or 0)
        if score == 0.0:
            score = _display_score(iv)

        atr_pct = round(float(iv.atr) / float(iv.close) * 100, 2) if iv.close > 0 else 0.0

        return {
            "rsi":          round(float(iv.rsi), 1),
            "macd_hist":    round(float(iv.macd_hist), 6),
            "macd_bullish": iv.macd_hist > 0,
            "bb_pct":       round(float(iv.bb_pct), 3),
            "bb_width_pct": round(float(iv.bb_width_pct) * 100, 2),
            "adx":          round(float(iv.adx), 1),
            "atr_pct":      atr_pct,
            "obv_slope":    round(float(iv.obv_slope), 4),
            "ema_cross":    "bullish" if iv.ema_short > iv.ema_long else "bearish",
            "above_sma200": bool(iv.close > iv.sma_long),
            "trend":        iv.pa_structure,
            "pa_bull_score": round(float(iv.pa_bull_score), 3),
            "pa_bear_score": round(float(iv.pa_bear_score), 3),
            "pa_pattern":   iv.pa_pattern,
            "score":        round(score, 3),
            "direction":    str(getattr(signal, "direction", "NONE")),
            "reasons":      list(getattr(signal, "reasons", []) or []),
            "close":        round(float(iv.close), 6),
        }
    except Exception:
        return None


async def _build(coin: str) -> dict:
    coin = coin.upper()

    # Tüm timeframe'leri paralel hesapla
    tasks = [_analyze_tf(coin, okx_tf, lim) for _, _, lim, okx_tf in TIMEFRAMES]
    results = await asyncio.gather(*tasks)

    timeframes: dict[str, Any] = {}
    for (tf_key, tf_label, _, _), result in zip(TIMEFRAMES, results):
        timeframes[tf_key] = {"label": tf_label, **(result or {"error": "Yetersiz veri"})}

    # 1h sinyali üzerinden kombine skor hesapla
    fg_index    = getattr(_engine.state, "fear_greed_index", 50) or 50
    funding_snap = _engine.state.funding_cache.get(coin)
    market_signal = funding_snap.combined_market_signal if funding_snap else 0.0
    funding_rate  = round(float(funding_snap.avg_rate), 6) if funding_snap else None

    combined_score  = 0.0
    technical_score = float(timeframes.get("1h", {}).get("score", 0.0))
    sentiment_score = 0.0
    market_score    = 0.0
    direction       = timeframes.get("1h", {}).get("direction", "NONE")
    last_price      = float(_engine.state.last_prices.get(coin, 0.0))

    # 1h verisi zaten _analyze_tf'de çekildi; yeniden çekme maliyetini önlemek için
    # 1h sonucunu doğrudan kullan
    tf1h = timeframes.get("1h", {})
    if "error" not in tf1h:
        technical_score = float(tf1h.get("score", 0.0))
        last_price = last_price or float(tf1h.get("close", 0.0))

    # Yön bağımsız kombine skor (NONE yönlü coinlerde de farklı değer gösterir)
    fg_raw    = fg_index / 100.0
    fg_norm   = max(fg_raw, 1.0 - fg_raw)   # 0.5=nötr, 1.0=ekstrem
    sentiment_score = round(0.5 * CRYPTOPANIC_WEIGHT + fg_norm * FEAR_GREED_WEIGHT, 4)
    market_score    = round(min(1.0, abs(market_signal)) * 0.5 + 0.5, 4)
    combined_score  = round(
        technical_score * TECHNICAL_WEIGHT +
        sentiment_score * SENTIMENT_WEIGHT +
        market_score    * MARKET_DATA_WEIGHT,
        3,
    )

    now = datetime.now(timezone.utc)
    return {
        "coin":          coin,
        "last_price":    last_price,
        "direction":     direction,
        "cached_at":     now.isoformat(),
        "expires_at":    (now + CACHE_TTL).isoformat(),
        "combined_score": combined_score,
        "technical_score": technical_score,
        "sentiment_score": sentiment_score,
        "market_score":    market_score,
        "score_breakdown": {
            "technical": {
                "label": "Teknik Analiz",
                "weight": 0.55,
                "value": technical_score,
                "contribution": round(technical_score * 0.55, 4),
            },
            "sentiment": {
                "label": "Duygu (Fear & Greed)",
                "weight": 0.25,
                "value": sentiment_score,
                "contribution": round(sentiment_score * 0.25, 4),
            },
            "market": {
                "label": "Piyasa (Funding / L-S)",
                "weight": 0.20,
                "value": market_score,
                "contribution": round(market_score * 0.20, 4),
            },
            "fear_greed_index": fg_index,
            "funding_rate":     funding_rate,
        },
        "timeframes": timeframes,
        "reasons": list(timeframes.get("1h", {}).get("reasons", [])),
    }


@router.get("/coin/{symbol}")
async def get_coin_detail(symbol: str):
    coin = symbol.upper()
    now  = datetime.now(timezone.utc)
    cached = _cache.get(coin)
    if cached and now < cached["expires_at"]:
        return cached["data"]
    try:
        data = await _build(coin)
        _cache[coin] = {"data": data, "expires_at": now + CACHE_TTL}
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coin/{symbol}/refresh")
async def refresh_coin_detail(symbol: str):
    coin = symbol.upper()
    _cache.pop(coin, None)
    try:
        now  = datetime.now(timezone.utc)
        data = await _build(coin)
        _cache[coin] = {"data": data, "expires_at": now + CACHE_TTL}
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
