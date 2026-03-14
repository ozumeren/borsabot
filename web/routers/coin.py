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
from web.score_utils import display_scores as _display_scores_util, display_score as _display_score_util

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


def _display_scores(iv) -> tuple[float, float]:
    return _display_scores_util(iv)


def _display_score(iv) -> float:
    return _display_score_util(iv)


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

    tf1h = timeframes.get("1h", {})
    if "error" not in tf1h:
        technical_score = float(tf1h.get("score", 0.0))
        last_price = last_price or float(tf1h.get("close", 0.0))

    fg_raw    = fg_index / 100.0

    # ── Gerçek bot LONG/SHORT kombine skorları ────────────────────────────────
    # Bot tam formülü: yöne bağlı sentiment + market, confluence bonusu yok
    def _bot_combined(tech_score: float, is_long: bool) -> float:
        def norm(raw: float) -> float:
            v = (raw + 1.0) / 2.0
            return v if is_long else (1.0 - v)
        fg_s = (1.0 - fg_raw) if is_long else fg_raw
        sentiment = 0.5 * CRYPTOPANIC_WEIGHT + fg_s * FEAR_GREED_WEIGHT
        market_n  = norm(market_signal)
        return round(
            tech_score  * TECHNICAL_WEIGHT +
            sentiment   * SENTIMENT_WEIGHT +
            market_n    * MARKET_DATA_WEIGHT,
            3,
        )

    # 1h teknik long/short skorlarını (ADX bypass) al
    long_tech_score  = float(tf1h.get("pa_bull_score", 0.0))  # placeholder
    short_tech_score = float(tf1h.get("pa_bear_score", 0.0))  # placeholder
    try:
        _df = await asyncio.to_thread(
            _engine.market_data.fetch_ohlcv, f"{coin}-USDT-SWAP", "1h", limit=200
        )
        if _df is not None and not _df.empty and len(_df) >= 20:
            _iv = await asyncio.to_thread(_engine.tech_analyzer.compute, _df)
            long_tech_score, short_tech_score = _display_scores(_iv)
    except Exception:
        long_tech_score = short_tech_score = technical_score

    long_combined_score  = _bot_combined(long_tech_score,  is_long=True)
    short_combined_score = _bot_combined(short_tech_score, is_long=False)
    min_combined_score   = getattr(_engine.sig_combiner, "min_combined_score", 0.55)

    # Gösterim için yön bağımsız skor (mevcut uyumluluk)
    fg_norm   = max(fg_raw, 1.0 - fg_raw)
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
        "bot_scores": {
            "long_combined":  long_combined_score,
            "short_combined": short_combined_score,
            "long_tech":      long_tech_score,
            "short_tech":     short_tech_score,
            "threshold":      min_combined_score,
            "long_eligible":  long_combined_score  >= min_combined_score,
            "short_eligible": short_combined_score >= min_combined_score,
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
