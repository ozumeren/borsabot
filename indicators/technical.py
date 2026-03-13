import pandas as pd
import ta
from dataclasses import dataclass
from config.constants import (
    RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL_PERIOD,
    EMA_SHORT, EMA_LONG, SMA_LONG,
    BB_PERIOD, BB_STD, ATR_PERIOD, ADX_PERIOD,
)


@dataclass
class IndicatorValues:
    rsi: float
    macd_line: float
    macd_signal: float
    macd_hist: float
    macd_hist_prev: float   # önceki mumun histogramı — gerçek crossover tespiti için
    ema_short: float
    ema_long: float
    sma_long: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_pct: float       # 0.0 = alt band, 1.0 = üst band
    atr: float
    adx: float
    close: float
    volume: float
    volume_avg20: float
    obv_slope: float = 0.0  # OBV 5-bar eğimi (pozitif=yükselen, negatif=düşen)

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
        macd_line      = macd_obj.macd().iloc[-1]
        macd_signal    = macd_obj.macd_signal().iloc[-1]
        _macd_hist_ser = macd_obj.macd_diff()
        macd_hist      = _macd_hist_ser.iloc[-1]
        macd_hist_prev = _macd_hist_ser.iloc[-2] if len(_macd_hist_ser) >= 2 else 0.0

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

        # ADX
        adx_indicator = ta.trend.ADXIndicator(high, low, close, window=ADX_PERIOD)
        adx = adx_indicator.adx().iloc[-1]

        # Hacim + OBV
        volume = float(vol.iloc[-1])
        volume_avg20 = float(vol.tail(20).mean())
        obv_series = ta.volume.OnBalanceVolumeIndicator(close, vol).on_balance_volume()
        if len(obv_series) >= 5:
            obv_tail = obv_series.tail(5)
            obv_base = abs(obv_tail.iloc[0]) + 1  # sıfıra bölmeyi önle
            obv_slope = float((obv_tail.iloc[-1] - obv_tail.iloc[0]) / obv_base)
        else:
            obv_slope = 0.0

        return IndicatorValues(
            rsi=float(rsi),
            macd_line=float(macd_line),
            macd_signal=float(macd_signal),
            macd_hist=float(macd_hist),
            macd_hist_prev=float(macd_hist_prev) if not pd.isna(macd_hist_prev) else 0.0,
            ema_short=float(ema_short),
            ema_long=float(ema_long),
            sma_long=float(sma_long),
            bb_upper=float(bb_upper),
            bb_mid=float(bb_mid),
            bb_lower=float(bb_lower),
            bb_pct=float(bb_pct),
            atr=float(atr),
            adx=float(adx) if not pd.isna(adx) else 0.0,
            close=float(price),
            volume=volume,
            volume_avg20=volume_avg20,
            obv_slope=obv_slope,
        )
