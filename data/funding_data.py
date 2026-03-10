"""
Çoklu borsa funding rate, open interest ve long/short oranı.
API key gerekmez — hepsi public endpoint.
Desteklenen: OKX, Binance, Bybit
"""
from __future__ import annotations
import ccxt
from dataclasses import dataclass, field
from typing import Optional
from utils.logger import get_logger

logger = get_logger("data.funding_data")

# Funding rate sinyal eşikleri
FR_STRONG_LONG   = -0.001   # < -0.1% → herkes short, LONG sinyali
FR_WEAK_LONG     = -0.0003  # < -0.03%
FR_WEAK_SHORT    =  0.0003  # > +0.03%
FR_STRONG_SHORT  =  0.001   # > +0.1% → herkes long, SHORT sinyali

# Long/Short oranı eşikleri
LS_RATIO_LONG_SIGNAL  = 0.7   # < 0.7 → herkes short → LONG sinyali
LS_RATIO_SHORT_SIGNAL = 1.5   # > 1.5 → herkes long → SHORT sinyali


@dataclass
class ExchangeFundingRate:
    exchange: str
    rate: float          # ondalık (0.001 = %0.1)
    next_reset_ms: Optional[int] = None


@dataclass
class FundingSnapshot:
    coin: str
    rates: list[ExchangeFundingRate] = field(default_factory=list)
    avg_rate: float = 0.0
    open_interest_usd: float = 0.0
    long_short_ratio: float = 1.0   # 1.0 = eşit

    @property
    def funding_signal(self) -> float:
        """
        Funding rate'i -1..+1 sinyal skoruna çevirir.
        Contrarian: yüksek pozitif rate → SHORT sinyali (-1 yönünde)
        """
        r = self.avg_rate
        if r >= FR_STRONG_SHORT:
            return -1.0
        if r >= FR_WEAK_SHORT:
            return -0.5
        if r <= FR_STRONG_LONG:
            return 1.0
        if r <= FR_WEAK_LONG:
            return 0.5
        return 0.0

    @property
    def ls_signal(self) -> float:
        """Long/Short oranını -1..+1 sinyal skoruna çevirir (contrarian)."""
        r = self.long_short_ratio
        if r >= LS_RATIO_SHORT_SIGNAL:
            return -1.0   # herkes long → potansiyel SHORT
        if r <= LS_RATIO_LONG_SIGNAL:
            return 1.0    # herkes short → potansiyel LONG
        # Lineer interpolasyon
        if r > 1.0:
            return -((r - 1.0) / (LS_RATIO_SHORT_SIGNAL - 1.0))
        else:
            return (1.0 - r) / (1.0 - LS_RATIO_LONG_SIGNAL)

    @property
    def combined_market_signal(self) -> float:
        """Funding + LS oranı birleşik sinyal (0.6/0.4 ağırlık)."""
        return self.funding_signal * 0.6 + self.ls_signal * 0.4

    def rate_pct_str(self) -> str:
        return f"{self.avg_rate * 100:.4f}%"


class MultiExchangeFundingFetcher:
    """
    OKX, Binance, Bybit'ten public funding verisi çeker.
    Hiç API key gerekmez.
    """

    def __init__(self, okx_exchange=None):
        # OKX — zaten bağlı exchange nesnesini al (opsiyonel)
        self._okx = okx_exchange

        # Binance Futures — public, key yok
        self._binance = ccxt.binanceusdm({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

        # Bybit — public, key yok
        self._bybit = ccxt.bybit({
            "enableRateLimit": True,
            "options": {"defaultType": "linear"},
        })

    def fetch(self, coin: str) -> FundingSnapshot:
        """Coin için tüm borsalardan veri çeker ve birleştirir."""
        symbol_perp = f"{coin}/USDT:USDT"   # OKX / Binance perpetual formatı
        symbol_spot = f"{coin}/USDT"          # Bybit formatı (bazı endpoint'ler)

        rates: list[ExchangeFundingRate] = []

        # ── OKX ──────────────────────────────────────────────────────────────
        if self._okx:
            rate = self._fetch_okx_rate(symbol_perp)
            if rate is not None:
                rates.append(ExchangeFundingRate("OKX", rate))

        # ── Binance ───────────────────────────────────────────────────────────
        rate = self._fetch_binance_rate(symbol_perp)
        if rate is not None:
            rates.append(ExchangeFundingRate("Binance", rate))

        # ── Bybit ─────────────────────────────────────────────────────────────
        rate = self._fetch_bybit_rate(symbol_perp)
        if rate is not None:
            rates.append(ExchangeFundingRate("Bybit", rate))

        avg_rate = sum(r.rate for r in rates) / len(rates) if rates else 0.0

        oi_usd = self._fetch_open_interest(symbol_perp)
        ls_ratio = self._fetch_long_short_ratio(coin)

        snap = FundingSnapshot(
            coin=coin,
            rates=rates,
            avg_rate=avg_rate,
            open_interest_usd=oi_usd,
            long_short_ratio=ls_ratio,
        )

        logger.debug(
            "Funding verisi alındı",
            coin=coin,
            avg_rate=snap.rate_pct_str(),
            exchanges=[r.exchange for r in rates],
            ls_ratio=f"{ls_ratio:.2f}",
        )
        return snap

    # ── Private fetch metodları ───────────────────────────────────────────────

    def _fetch_okx_rate(self, symbol: str) -> Optional[float]:
        try:
            data = self._okx.fetch_funding_rate(symbol)
            return float(data["fundingRate"])
        except Exception as e:
            logger.debug("OKX funding rate alınamadı", symbol=symbol, error=str(e))
            return None

    def _fetch_binance_rate(self, symbol: str) -> Optional[float]:
        try:
            data = self._binance.fetch_funding_rate(symbol)
            return float(data["fundingRate"])
        except Exception as e:
            logger.debug("Binance funding rate alınamadı", symbol=symbol, error=str(e))
            return None

    def _fetch_bybit_rate(self, symbol: str) -> Optional[float]:
        try:
            data = self._bybit.fetch_funding_rate(symbol)
            return float(data["fundingRate"])
        except Exception as e:
            logger.debug("Bybit funding rate alınamadı", symbol=symbol, error=str(e))
            return None

    def _fetch_open_interest(self, symbol: str) -> float:
        """Open interest USD cinsinden — Binance'den çeker."""
        for exchange in (self._binance, self._bybit):
            try:
                data = exchange.fetch_open_interest(symbol)
                # ccxt'de info dict içinde ham değer olabilir
                val = (data.get("openInterestValue")
                       or data.get("openInterest")
                       or (data.get("info") or {}).get("openInterestValue")
                       or (data.get("info") or {}).get("openInterest")
                       or 0)
                result = float(val)
                if result > 0:
                    return result
            except Exception:
                pass
        logger.debug("Open interest alınamadı", symbol=symbol)
        return 0.0

    def _fetch_long_short_ratio(self, coin: str) -> float:
        """
        Global long/short oranı — Binance'den çeker.
        1.0 = eşit, >1.0 = longlar fazla, <1.0 = shortlar fazla
        """
        symbol = f"{coin}/USDT:USDT"
        for exchange in (self._binance, self._bybit):
            try:
                # limit parametresi bazı ccxt sürümlerinde desteklenmez
                data = exchange.fetch_long_short_ratio(symbol, "15m")
                if data:
                    latest = data[-1] if isinstance(data, list) else data
                    ratio = latest.get("longShortRatio") or latest.get("info", {}).get("longShortRatio")
                    if ratio:
                        return float(ratio)
            except Exception:
                pass
        logger.debug("Long/short oranı alınamadı", coin=coin)
        return 1.0
