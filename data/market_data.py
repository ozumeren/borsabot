import pandas as pd
import httpx
from typing import Optional
from exchange.client import OKXClient
from data.data_cache import TTLCache
from config.constants import (
    MIN_24H_VOLUME_USDT, MAX_SPREAD_PCT, STABLECOIN_BLACKLIST, MIN_CANDLES
)
from utils.logger import get_logger
from utils.helpers import coin_from_symbol

logger = get_logger("data.market_data")


class MarketDataFetcher:
    """OKX'ten piyasa verisi çekme ve coin tarama."""

    def __init__(self, client: OKXClient):
        self.client = client
        self._cache = TTLCache(default_ttl=300)  # 5 dakika cache

    def scan_top_coins(self, top_n: int = 30) -> list[str]:
        """
        Hacme göre sıralanmış top N USDT-margined perpetual swap döndürür.
        Format: ["BTC/USDT:USDT", "ETH/USDT:USDT", ...]
        """
        cache_key = f"top_coins_{top_n}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            tickers = self.client.fetch_tickers()
        except Exception as e:
            logger.error("Ticker çekme hatası", error=str(e))
            return []

        candidates = []
        for symbol, ticker in tickers.items():
            # Sadece USDT perpetual swap
            if not symbol.endswith("/USDT:USDT"):
                continue

            coin = coin_from_symbol(symbol)

            # Stablecoin filtresi
            if coin.upper() in STABLECOIN_BLACKLIST:
                continue

            # Hacim filtresi — quoteVolume yoksa baseVolume * last ile hesapla
            quote_volume = ticker.get("quoteVolume") or 0
            if not quote_volume:
                base_vol = ticker.get("baseVolume") or 0
                last     = ticker.get("last") or ticker.get("close") or 0
                quote_volume = base_vol * last
            if quote_volume < MIN_24H_VOLUME_USDT:
                continue

            # Spread filtresi
            bid = ticker.get("bid") or 0
            ask = ticker.get("ask") or 0
            if bid > 0 and ask > 0:
                spread_pct = (ask - bid) / bid
                if spread_pct > MAX_SPREAD_PCT:
                    continue

            candidates.append((symbol, quote_volume))

        # Hacme göre sırala
        candidates.sort(key=lambda x: x[1], reverse=True)
        result = [sym for sym, _ in candidates[:top_n]]

        self._cache.set(cache_key, result)
        logger.info("Coin taraması tamamlandı", found=len(result), top_n=top_n)
        return result

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
    ) -> Optional[pd.DataFrame]:
        """OHLCV veri çeker. Yeterli mum yoksa None döner."""
        cache_key = f"ohlcv_{symbol}_{timeframe}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.warning("OHLCV çekme hatası", symbol=symbol, error=str(e))
            return None

        if len(df) < MIN_CANDLES:
            logger.debug("Yetersiz mum sayısı", symbol=symbol, count=len(df))
            return None

        _TF_TTL = {"1m": 30, "3m": 60, "5m": 120, "15m": 300, "30m": 600, "1h": 900, "4h": 1800, "1d": 3600}
        self._cache.set(cache_key, df, ttl=_TF_TTL.get(timeframe, 60))
        return df

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Gerçek piyasa anlık fiyatını döndürür (OKX public API, sandbox değil)."""
        # symbol formatı: "ETH/USDT:USDT" → instId: "ETH-USDT-SWAP"
        try:
            coin = symbol.split("/")[0]
            inst_id = f"{coin}-USDT-SWAP"
            r = httpx.get(
                f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}",
                timeout=5.0,
            )
            data = r.json().get("data", [])
            if data:
                return float(data[0]["last"])
        except Exception as e:
            logger.warning("Fiyat alınamadı", symbol=symbol, error=str(e))
        return None

    def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._cache.delete(f"ohlcv_{symbol}_15m")
        else:
            self._cache.clear()
