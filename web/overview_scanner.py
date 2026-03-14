"""Background task: scans top 20 coins every 60s for the web overview."""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from config.constants import (
    TECHNICAL_WEIGHT, SENTIMENT_WEIGHT, MARKET_DATA_WEIGHT,
    CRYPTOPANIC_WEIGHT, FEAR_GREED_WEIGHT,
)

_cache: Dict = {"coins": [], "updated_at": None, "btc_regime": "neutral"}


def get_cache() -> Dict:
    return _cache


async def run_overview_scanner(engine: Any) -> None:
    global _cache
    while True:
        try:
            symbols = await asyncio.to_thread(engine.market_data.scan_top_coins, 20)
            if not symbols:
                await asyncio.sleep(60)
                continue

            async def scan_one(symbol: str):
                try:
                    coin = symbol.split("/")[0]
                    df = await asyncio.to_thread(
                        engine.market_data.fetch_ohlcv,
                        symbol, engine.settings.timeframe
                    )
                    if df is None or df.empty:
                        return None

                    iv = await asyncio.to_thread(engine.tech_analyzer.compute, df)
                    signal = engine.tech_sig_gen.generate(iv)

                    last_price = float(df["close"].iloc[-1])
                    change_pct = 0.0
                    if len(df) >= 20:
                        prev = float(df["close"].iloc[-20])
                        if prev:
                            change_pct = (last_price - prev) / prev * 100

                    score = float(
                        getattr(signal, "score",
                        getattr(signal, "technical_score", 0)) or 0
                    )
                    direction = str(getattr(signal, "direction", "NONE"))
                    rsi = float(getattr(iv, "rsi", 50) or 50)
                    macd_hist = float(getattr(iv, "macd_hist", 0) or 0)

                    # Kombine skor: yön bağımsız formül (NONE yönü olan coinler için)
                    fg_index = getattr(engine.state, "fear_greed_index", 50) or 50
                    funding_snap = engine.state.funding_cache.get(coin)
                    market_signal = funding_snap.combined_market_signal if funding_snap else 0.0

                    fg_raw  = fg_index / 100.0
                    # Ekstrem okumalar (Aşırı Korku veya Aşırı Açgözlülük) sentiment'i artırır
                    fg_norm = max(fg_raw, 1.0 - fg_raw)   # 0.5=nötr, 1.0=ekstrem
                    sentiment = 0.5 * CRYPTOPANIC_WEIGHT + fg_norm * FEAR_GREED_WEIGHT
                    market_n  = min(1.0, abs(market_signal)) * 0.5 + 0.5  # [0.5, 1.0]
                    combined_score = round(
                        score   * TECHNICAL_WEIGHT +
                        sentiment * SENTIMENT_WEIGHT +
                        market_n  * MARKET_DATA_WEIGHT,
                        3,
                    )

                    # Status sınıflandırması (kombine skora göre)
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
                        "rsi": round(rsi, 1),
                        "score": round(score, 3),
                        "combined_score": round(combined_score, 3),
                        "direction": direction,
                        "macd_bullish": macd_hist > 0,
                        "status": status,
                        "reasons": list(getattr(signal, "reasons", []) or [])[:3],
                    }
                except Exception:
                    return None

            raw = await asyncio.gather(*[scan_one(s) for s in symbols[:20]])
            coins = [r for r in raw if r]
            coins.sort(key=lambda x: x["score"], reverse=True)

            _cache = {
                "coins": coins,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "btc_regime": engine.state.btc_regime,
            }

        except Exception:
            pass

        await asyncio.sleep(60)
