import ccxt
import pandas as pd
from typing import Optional
from config.settings import BotSettings
from config.constants import OKX_RATE_LIMIT_MARKET, MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY
from exchange.rate_limiter import RateLimiter
from utils.retry import exchange_retry
from utils.logger import get_logger

logger = get_logger("exchange.client")


class OKXClient:
    """OKX API için CCXT wrapper. Rate limiting ve retry dahil."""

    def __init__(self, settings: BotSettings):
        self.settings = settings
        self._rate_limiter = RateLimiter(max_calls=OKX_RATE_LIMIT_MARKET, period=2.0)

        self.exchange = ccxt.okx({
            "apiKey":   settings.okx_api_key,
            "secret":   settings.okx_secret_key,
            "password": settings.okx_passphrase,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
            },
        })

        if settings.okx_sandbox:
            self.exchange.set_sandbox_mode(True)
            logger.info("OKX sandbox (demo) modu aktif")
        else:
            logger.warning("OKX CANLI mod aktif - gerçek para kullanılıyor!")

    @exchange_retry()
    def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> pd.DataFrame:
        with self._rate_limiter:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")
        return df.astype(float)

    @exchange_retry()
    def fetch_tickers(self) -> dict:
        with self._rate_limiter:
            return self.exchange.fetch_tickers(params={"instType": "SWAP"})

    @exchange_retry()
    def fetch_balance(self) -> dict:
        with self._rate_limiter:
            return self.exchange.fetch_balance()

    @exchange_retry()
    def fetch_positions(self) -> list:
        with self._rate_limiter:
            return self.exchange.fetch_positions()

    @exchange_retry()
    def set_leverage(self, symbol: str, leverage: int, direction: str) -> dict:
        """direction: 'long' veya 'short' (isolated margin için)"""
        with self._rate_limiter:
            params = {"mgnMode": "isolated", "posSide": direction}
            return self.exchange.set_leverage(leverage, symbol, params)

    @exchange_retry()
    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        pos_side: str,
        reduce_only: bool = False,
    ) -> dict:
        with self._rate_limiter:
            params = {
                "posSide": pos_side,
                "tdMode": "isolated",
            }
            if reduce_only:
                params["reduceOnly"] = True
            return self.exchange.create_order(symbol, "market", side, amount, params=params)

    @exchange_retry()
    def create_trigger_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        pos_side: str,
        reduce_only: bool = True,
    ) -> dict:
        """Stop-loss / take-profit trigger emri."""
        with self._rate_limiter:
            params = {
                "posSide": pos_side,
                "tdMode": "isolated",
                "ordType": "trigger",
                "triggerPx": str(trigger_price),
                "orderPx": "-1",  # market fiyattan gerçekleştir
            }
            if reduce_only:
                params["reduceOnly"] = True
            return self.exchange.create_order(symbol, "market", side, amount, params=params)

    @exchange_retry()
    def cancel_order(self, order_id: str, symbol: str) -> dict:
        with self._rate_limiter:
            return self.exchange.cancel_order(order_id, symbol)

    @exchange_retry()
    def fetch_order(self, order_id: str, symbol: str) -> dict:
        with self._rate_limiter:
            return self.exchange.fetch_order(order_id, symbol)

    def get_portfolio_value(self) -> float:
        """USDT cinsinden toplam portföy değeri."""
        balance = self.fetch_balance()
        usdt = balance.get("USDT", {})
        return float(usdt.get("total", 0.0))

    def ping(self) -> bool:
        """API bağlantısını test eder."""
        try:
            self.exchange.fetch_time()
            return True
        except Exception as e:
            logger.error("OKX ping başarısız", error=str(e))
            return False
