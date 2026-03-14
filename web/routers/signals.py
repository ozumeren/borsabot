import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException
from web.overview_scanner import get_cache
from config.constants import (
    TECHNICAL_WEIGHT, SENTIMENT_WEIGHT, MARKET_DATA_WEIGHT,
    CRYPTOPANIC_WEIGHT, FEAR_GREED_WEIGHT,
)

router = APIRouter()
_engine: Any = None


@router.get("/signals/scan")
async def get_scan_results():
    state = _engine.state
    results = []
    for item in state.scan_results:
        fs = item[0]
        results.append({
            "coin": getattr(fs, "coin", ""),
            "direction": str(getattr(fs, "direction", "")),
            "combined_score": getattr(fs, "combined_score", 0.0),
            "technical_score": getattr(fs, "technical_score", 0.0),
            "sentiment_score": getattr(fs, "sentiment_score", 0.0),
            "reasons": getattr(fs, "reasons", []),
        })

    best = None
    if state.best_opportunity:
        fs, iv = state.best_opportunity
        best = {
            "coin": getattr(fs, "coin", ""),
            "direction": str(getattr(fs, "direction", "")),
            "combined_score": getattr(fs, "combined_score", 0.0),
            "reasons": getattr(fs, "reasons", []),
        }

    return {
        "btc_regime": state.btc_regime,
        "scan_results": results,
        "best_opportunity": best,
        "count": len(results),
    }


@router.get("/signals/overview")
async def get_overview():
    """Cached top-20 coin overview (refreshes every 60s in background)."""
    return get_cache()


@router.get("/signals/full-scan")
async def full_scan():
    """Scan all market coins for signals (slow, on-demand)."""
    try:
        symbols = await asyncio.to_thread(_engine.market_data.scan_top_coins, 50)

        async def scan_one(symbol: str):
            try:
                coin = symbol.split("/")[0]
                df = await asyncio.to_thread(
                    _engine.market_data.fetch_ohlcv,
                    symbol, _engine.settings.timeframe
                )
                if df is None or df.empty:
                    return None
                iv = await asyncio.to_thread(_engine.tech_analyzer.compute, df)
                signal = _engine.tech_sig_gen.generate(iv)
                score = float(getattr(signal, "score", getattr(signal, "technical_score", 0)) or 0)
                direction = str(getattr(signal, "direction", "NONE"))

                last_price = float(df["close"].iloc[-1])
                change_pct = 0.0
                if len(df) >= 20:
                    prev = float(df["close"].iloc[-20])
                    if prev:
                        change_pct = (last_price - prev) / prev * 100

                rsi = float(getattr(iv, "rsi", 50) or 50)
                macd_hist = float(getattr(iv, "macd_hist", 0) or 0)

                # Kombine skor: yön bağımsız formül
                fg_index = getattr(_engine.state, "fear_greed_index", 50) or 50
                funding_snap = _engine.state.funding_cache.get(coin)
                market_signal = funding_snap.combined_market_signal if funding_snap else 0.0
                fg_raw  = fg_index / 100.0
                fg_norm = max(fg_raw, 1.0 - fg_raw)
                sentiment = 0.5 * CRYPTOPANIC_WEIGHT + fg_norm * FEAR_GREED_WEIGHT
                market_n  = min(1.0, abs(market_signal)) * 0.5 + 0.5
                combined_score = round(
                    score     * TECHNICAL_WEIGHT +
                    sentiment * SENTIMENT_WEIGHT +
                    market_n  * MARKET_DATA_WEIGHT,
                    3,
                )

                if combined_score >= 0.58:
                    status = "entry"
                elif combined_score >= 0.47:
                    status = "watch"
                elif rsi > 72 or rsi < 28:
                    status = "avoid"
                elif combined_score < 0.38:
                    status = "avoid"
                else:
                    status = "neutral"

                return {
                    "coin": coin,
                    "price": last_price,
                    "change_pct": round(change_pct, 2),
                    "score": round(score, 3),
                    "combined_score": round(combined_score, 3),
                    "direction": direction,
                    "rsi": round(rsi, 1),
                    "macd_bullish": macd_hist > 0,
                    "reasons": list(getattr(signal, "reasons", []) or [])[:3],
                    "status": status,
                }
            except Exception:
                return None

        # 10'luk batch'ler halinde tara
        coins = []
        for i in range(0, len(symbols), 10):
            try:
                batch = await asyncio.gather(*[scan_one(s) for s in symbols[i:i+10]])
                coins.extend(r for r in batch if r)
            except Exception:
                pass
            await asyncio.sleep(0.3)
        coins.sort(key=lambda x: x["score"], reverse=True)
        return {
            "coins": coins,
            "count": len(coins),
            "btc_regime": _engine.state.btc_regime,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/{symbol}")
async def get_signal(symbol: str):
    """On-demand signal analysis for a specific coin."""
    coin = symbol.upper()
    try:
        # Attempt to run a quick scan for this coin
        candles = await _engine.market_data.fetch_ohlcv(f"{coin}-USDT-SWAP", _engine.settings.timeframe, limit=200)
        if not candles:
            raise HTTPException(status_code=404, detail=f"No data for {coin}")

        iv = _engine.tech_analyzer.analyze(candles)
        fs = _engine.tech_sig_gen.generate(coin, iv)

        # Funding
        funding = _engine.state.funding_cache.get(coin)

        return {
            "coin": coin,
            "direction": str(getattr(fs, "direction", "")) if fs else None,
            "technical_score": getattr(fs, "technical_score", 0.0) if fs else None,
            "signal_active": fs is not None,
            "indicators": {
                "rsi": getattr(iv, "rsi", None),
                "macd_hist": getattr(iv, "macd_hist", None),
                "bb_pct": getattr(iv, "bb_pct", None),
                "volume_ratio": getattr(iv, "volume_ratio", None),
                "atr_pct": getattr(iv, "atr_pct", None),
                "obv_slope": getattr(iv, "obv_slope", None),
            },
            "funding_rate": getattr(funding, "weighted_rate", None) if funding else None,
            "last_price": _engine.state.last_prices.get(coin),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
