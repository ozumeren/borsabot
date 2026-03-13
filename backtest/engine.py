"""
Backtest motoru.
Mevcut TechnicalAnalyzer + TechnicalSignalGenerator kullanır (yeni kod yok).
Sadece teknik sinyal — tarihsel sentiment verisi olmadığı için sentiment atlanır.
"""
from __future__ import annotations

import pandas as pd
import ta
from dataclasses import dataclass, field
from typing import Optional

from indicators.technical import TechnicalAnalyzer, IndicatorValues
from signals.technical_signal import TechnicalSignalGenerator, Direction
from config.constants import (
    RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL_PERIOD,
    EMA_SHORT, EMA_LONG, SMA_LONG, BB_PERIOD, BB_STD, ATR_PERIOD, ADX_PERIOD,
)

FEE_PCT = 0.001  # %0.1 taker fee (her iki taraf)


@dataclass
class BacktestTrade:
    coin: str
    direction: str          # 'long' | 'short'
    entry_time: pd.Timestamp
    entry_price: float
    sl_price: float
    tp_price: float
    quantity: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl_usdt: float = 0.0
    pnl_pct: float = 0.0
    status: str = "OPEN"    # OPEN / CLOSED_TP / CLOSED_SL / CLOSED_END
    max_adverse_excursion: float = 0.0  # en kötü gerçekleşmemiş kayıp (%)
    duration_bars: int = 0


def _precompute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame'e tüm indikatör kolonlarını ekler. Tek pass, O(n)."""
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["volume"]

    df = df.copy()

    df["rsi"]        = ta.momentum.RSIIndicator(close, window=RSI_PERIOD).rsi()
    macd_obj         = ta.trend.MACD(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL_PERIOD)
    df["macd_line"]      = macd_obj.macd()
    df["macd_sig"]       = macd_obj.macd_signal()
    df["macd_hist"]      = macd_obj.macd_diff()
    df["macd_hist_prev"] = df["macd_hist"].shift(1)
    df["ema_short"]  = ta.trend.EMAIndicator(close, window=EMA_SHORT).ema_indicator()
    df["ema_long"]   = ta.trend.EMAIndicator(close, window=EMA_LONG).ema_indicator()
    df["sma_long"]   = ta.trend.SMAIndicator(close, window=min(SMA_LONG, len(df)-1)).sma_indicator()
    bb               = ta.volatility.BollingerBands(close, window=BB_PERIOD, window_dev=BB_STD)
    df["bb_upper"]   = bb.bollinger_hband()
    df["bb_lower"]   = bb.bollinger_lband()
    df["bb_mid"]     = bb.bollinger_mavg()
    df["atr"]        = ta.volatility.AverageTrueRange(high, low, close, window=ATR_PERIOD).average_true_range()
    df["adx"]        = ta.trend.ADXIndicator(high, low, close, window=ADX_PERIOD).adx()
    df["vol_avg20"]  = vol.rolling(20).mean()
    obv_raw          = ta.volume.OnBalanceVolumeIndicator(close, vol).on_balance_volume()
    df["obv_slope"]  = (obv_raw - obv_raw.shift(5)) / (obv_raw.shift(5).abs() + 1)

    return df


def _row_to_indicator_values(row: pd.Series) -> IndicatorValues:
    bb_width = row["bb_upper"] - row["bb_lower"]
    bb_pct   = (row["close"] - row["bb_lower"]) / bb_width if bb_width > 0 else 0.5
    return IndicatorValues(
        rsi=float(row["rsi"]),
        macd_line=float(row["macd_line"]),
        macd_signal=float(row["macd_sig"]),
        macd_hist=float(row["macd_hist"]),
        macd_hist_prev=float(row["macd_hist_prev"]) if not pd.isna(row["macd_hist_prev"]) else 0.0,
        ema_short=float(row["ema_short"]),
        ema_long=float(row["ema_long"]),
        sma_long=float(row["sma_long"]),
        bb_upper=float(row["bb_upper"]),
        bb_mid=float(row["bb_mid"]),
        bb_lower=float(row["bb_lower"]),
        bb_pct=float(bb_pct),
        atr=float(row["atr"]),
        adx=float(row["adx"]) if not pd.isna(row["adx"]) else 0.0,
        close=float(row["close"]),
        volume=float(row["volume"]),
        volume_avg20=float(row["vol_avg20"]) if not pd.isna(row["vol_avg20"]) else float(row["volume"]),
        obv_slope=float(row["obv_slope"]) if not pd.isna(row["obv_slope"]) else 0.0,
        # Price action backtest'te satır bazında hesaplanmıyor (varsayılan sıfır)
        pa_bull_score=0.0,
        pa_bear_score=0.0,
        pa_pattern="",
        pa_structure="UNKNOWN",
    )


class BacktestEngine:
    """
    Tarihsel veri üzerinde teknik sinyal tabanlı backtest.

    stop_atr_mult : SL mesafesi = ATR × bu katsayı
    tp_rr         : TP = SL mesafesi × risk/reward
    min_tech_score: teknik sinyal eşiği
    """

    def __init__(
        self,
        stop_atr_mult: float = 1.5,
        tp_rr: float = 2.0,
        min_tech_score: float = 0.60,
        max_open_positions: int = 5,
        position_pct: float = 0.10,
    ):
        self.stop_atr_mult = stop_atr_mult
        self.tp_rr = tp_rr
        self.sig_gen = TechnicalSignalGenerator(min_score=min_tech_score)
        self.max_open_positions = max_open_positions
        self.position_pct = position_pct

    def run(self, coin: str, df: pd.DataFrame, initial_capital: float = 1000.0) -> list[BacktestTrade]:
        """
        df: OHLCV DataFrame (index=datetime, colonlar: open/high/low/close/volume)
        Döndürür: kapalı trade listesi
        """
        df = _precompute_indicators(df)

        capital = initial_capital
        trades: list[BacktestTrade] = []
        open_trade: Optional[BacktestTrade] = None
        warmup = 50  # indikatörler için minimum bar

        rows = df.iloc[warmup:]

        for i, (ts, row) in enumerate(rows.iterrows()):
            price = float(row["close"])

            # ── Açık trade kontrolü ──────────────────────────────────────────
            if open_trade is not None:
                open_trade.duration_bars += 1
                # MAE takibi
                if open_trade.direction == "long":
                    adverse = (open_trade.entry_price - price) / open_trade.entry_price
                else:
                    adverse = (price - open_trade.entry_price) / open_trade.entry_price
                if adverse > open_trade.max_adverse_excursion:
                    open_trade.max_adverse_excursion = adverse

                # SL/TP kontrolü
                sl_hit = (
                    (open_trade.direction == "long"  and price <= open_trade.sl_price) or
                    (open_trade.direction == "short" and price >= open_trade.sl_price)
                )
                tp_hit = (
                    (open_trade.direction == "long"  and price >= open_trade.tp_price) or
                    (open_trade.direction == "short" and price <= open_trade.tp_price)
                )

                if sl_hit or tp_hit:
                    exit_price = open_trade.sl_price if sl_hit else open_trade.tp_price
                    open_trade = _close_trade(open_trade, ts, exit_price, capital,
                                              "CLOSED_SL" if sl_hit else "CLOSED_TP")
                    capital += open_trade.pnl_usdt
                    trades.append(open_trade)
                    open_trade = None
                    continue

            # ── NaN kontrolü ─────────────────────────────────────────────────
            if row.isnull().any():
                continue

            # ── Yeni sinyal üret ─────────────────────────────────────────────
            if open_trade is not None:
                continue  # tek pozisyon modeli

            iv = _row_to_indicator_values(row)
            tech_signal = self.sig_gen.generate(iv)
            if tech_signal.direction == Direction.NONE:
                continue

            # Pozisyon büyüklüğü
            atr = float(row["atr"])
            sl_dist = atr * self.stop_atr_mult
            if sl_dist <= 0:
                continue

            if tech_signal.direction == Direction.LONG:
                sl_price = price - sl_dist
                tp_price = price + sl_dist * self.tp_rr
                direction = "long"
            else:
                sl_price = price + sl_dist
                tp_price = price - sl_dist * self.tp_rr
                direction = "short"

            margin    = capital * self.position_pct
            quantity  = (margin * 1.0) / price  # 1x leverage for simplicity in backtest
            fee_entry = quantity * price * FEE_PCT

            open_trade = BacktestTrade(
                coin=coin,
                direction=direction,
                entry_time=ts,
                entry_price=price,
                sl_price=sl_price,
                tp_price=tp_price,
                quantity=quantity,
            )
            open_trade.pnl_usdt = -fee_entry  # giriş fee'si

        # Backtest sonu — açık pozisyonu kapat
        if open_trade is not None:
            last_price = float(df.iloc[-1]["close"])
            open_trade = _close_trade(open_trade, df.index[-1], last_price, capital, "CLOSED_END")
            capital += open_trade.pnl_usdt
            trades.append(open_trade)

        return trades


def _close_trade(
    trade: BacktestTrade,
    exit_time: pd.Timestamp,
    exit_price: float,
    capital: float,
    status: str,
) -> BacktestTrade:
    fee_exit = trade.quantity * exit_price * FEE_PCT
    if trade.direction == "long":
        gross = (exit_price - trade.entry_price) * trade.quantity
    else:
        gross = (trade.entry_price - exit_price) * trade.quantity

    pnl = gross - fee_exit + trade.pnl_usdt  # pnl_usdt already has entry fee as negative
    margin_approx = trade.quantity * trade.entry_price
    pnl_pct = pnl / margin_approx if margin_approx > 0 else 0.0

    trade.exit_time = exit_time
    trade.exit_price = exit_price
    trade.pnl_usdt = pnl
    trade.pnl_pct = pnl_pct
    trade.status = status
    return trade
