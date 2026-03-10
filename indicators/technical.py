import pandas as pd
import ta
from dataclasses import dataclass
from config.constants import (
    RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL_PERIOD,
    EMA_SHORT, EMA_LONG, SMA_LONG,
    BB_PERIOD, BB_STD, ATR_PERIOD,
)


@dataclass
class IndicatorValues:
    rsi: float
    macd_line: float
    macd_signal: float
    macd_hist: float
    ema_short: float
    ema_long: float
    sma_long: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_pct: float       # 0.0 = alt band, 1.0 = üst band
    atr: float
    close: float
    volume: float
    volume_avg20: float

    @property
    def is_volume_spike(self) -> bool:
        return self.volume > self.volume_avg20 * 1.5


class TechnicalAnalyzer:
    """RSI, MACD, EMA/SMA, Bollinger Bands, ATR hesaplar."""

    def compute(self, df: pd.DataFrame) -> IndicatorValues:
        """
        df: OHLCV DataFrame, index datetime, kolonlar: open/high/low/close/volume
        Raises: ValueError — yeterli veri yoksa
        """
        if len(df) < 50:
            raise ValueError(f"Yetersiz veri: {len(df)} mum (minimum 50 gerekli)")

        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        vol   = df["volume"]

        # RSI
        rsi = ta.momentum.RSIIndicator(close, window=RSI_PERIOD).rsi().iloc[-1]

        # MACD
        macd_obj = ta.trend.MACD(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL_PERIOD)
        macd_line   = macd_obj.macd().iloc[-1]
        macd_signal = macd_obj.macd_signal().iloc[-1]
        macd_hist   = macd_obj.macd_diff().iloc[-1]

        # EMA / SMA
        ema_short = ta.trend.EMAIndicator(close, window=EMA_SHORT).ema_indicator().iloc[-1]
        ema_long  = ta.trend.EMAIndicator(close, window=EMA_LONG).ema_indicator().iloc[-1]
        sma_long  = ta.trend.SMAIndicator(close, window=min(SMA_LONG, len(df)-1)).sma_indicator().iloc[-1]

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close, window=BB_PERIOD, window_dev=BB_STD)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_mid   = bb.bollinger_mavg().iloc[-1]
        price    = close.iloc[-1]
        band_width = bb_upper - bb_lower
        bb_pct   = (price - bb_lower) / band_width if band_width > 0 else 0.5

        # ATR
        atr = ta.volatility.AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range().iloc[-1]

        # Hacim
        volume = float(vol.iloc[-1])
        volume_avg20 = float(vol.tail(20).mean())

        return IndicatorValues(
            rsi=float(rsi),
            macd_line=float(macd_line),
            macd_signal=float(macd_signal),
            macd_hist=float(macd_hist),
            ema_short=float(ema_short),
            ema_long=float(ema_long),
            sma_long=float(sma_long),
            bb_upper=float(bb_upper),
            bb_mid=float(bb_mid),
            bb_lower=float(bb_lower),
            bb_pct=float(bb_pct),
            atr=float(atr),
            close=float(price),
            volume=volume,
            volume_avg20=volume_avg20,
        )
