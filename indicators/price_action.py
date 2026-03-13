"""
Price Action analiz motoru.

Tespit edilen formasyonlar (tek/çift/üç mum):
  Tek mum : Hammer, Shooting Star, Pin Bar (bull/bear), Doji (standard/dragonfly/gravestone),
            Marubozu (bull/bear)
  Çift mum: Bullish/Bearish Engulfing, Inside Bar, Tweezer Top/Bottom
  Üç mum  : Morning Star, Evening Star, Three White Soldiers, Three Black Crows

Market Structure:
  - Swing High / Swing Low tespiti (N-bar lookback)
  - HH/HL/LH/LL sınıflandırması
  - UPTREND / DOWNTREND / RANGING / UNKNOWN

Skor: bull_score ve bear_score 0.0–1.0 arasında.
  - ATR filtresi: gürültüyü eler (küçük mum = ağırlık yok)
  - S/R yakınlığı: formasyon kritik seviyede olunca x1.3 çarpanı
  - Yapı uyumu:   trend doğrultusundaki formasyon +0.10 bonus
  - Hacim teyidi: hacim >1.5× ortalama → +0.08 bonus
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class PriceActionResult:
    bull_score: float = 0.0       # 0.0–1.0 yükseliş formasyon gücü
    bear_score: float = 0.0       # 0.0–1.0 düşüş formasyon gücü
    top_pattern: str = ""         # en güçlü tespit edilen formasyon adı
    market_structure: str = "UNKNOWN"  # UPTREND | DOWNTREND | RANGING | UNKNOWN
    at_support: bool = False      # son kapanış bilinen destek yakınında mı
    at_resistance: bool = False   # son kapanış bilinen direnç yakınında mı
    swing_high: float = 0.0       # son tespit edilen swing high
    swing_low: float = 0.0        # son tespit edilen swing low


class PriceActionAnalyzer:
    """
    OHLCV DataFrame → PriceActionResult.
    Minimum veri: 10 mum (önerilir: 30+).
    """

    # Her formasyonun maksimum katkısı (toplam > 1.0 olursa min(1.0) ile kırpılır)
    BULL_WEIGHTS: dict[str, float] = {
        "pin_bar_bull":     0.22,
        "bull_engulfing":   0.20,
        "morning_star":     0.18,
        "three_white_sol":  0.15,
        "hammer":           0.15,
        "dragonfly_doji":   0.12,
        "tweezer_bottom":   0.12,
        "marubozu_bull":    0.10,
        "inside_bar_bull":  0.07,
    }
    BEAR_WEIGHTS: dict[str, float] = {
        "pin_bar_bear":      0.22,
        "bear_engulfing":    0.20,
        "evening_star":      0.18,
        "three_black_crows": 0.15,
        "shooting_star":     0.15,
        "gravestone_doji":   0.12,
        "tweezer_top":       0.12,
        "marubozu_bear":     0.10,
        "inside_bar_bear":   0.07,
    }

    # ─────────────────────────────────────────────────────────────────────
    def analyze(self, df: pd.DataFrame) -> PriceActionResult:
        if len(df) < 10:
            return PriceActionResult()

        close  = df["close"]
        open_  = df["open"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]

        # ATR (son 14 bar — gürültü filtresi için)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if pd.isna(atr) or atr <= 0:
            atr = float(high.iloc[-1] - low.iloc[-1]) or 1.0

        # ── Temel vektörler ───────────────────────────────────────────────
        body       = (close - open_).abs()
        rng        = high - low
        upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
        lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low
        body_ratio = body / (rng + 1e-9)

        patterns: dict[str, bool] = {}

        # ── Tek mum formasyonları (son bar: iloc[-1]) ─────────────────────
        b   = float(body.iloc[-1])
        rg  = float(rng.iloc[-1])
        uw  = float(upper_wick.iloc[-1])
        lw  = float(lower_wick.iloc[-1])
        br  = float(body_ratio.iloc[-1])
        c_  = float(close.iloc[-1])
        o_  = float(open_.iloc[-1])

        # Hammer (alt fitilli, küçük gövde, neredeyse üst fitil yok)
        patterns["hammer"] = (
            rg > 2.5 * b and
            lw / (rg + 1e-9) > 0.60 and
            uw / (rg + 1e-9) < 0.15 and
            b > 0.05 * rg and
            lw > 0.80 * atr   # ATR filtresi
        )

        # Shooting Star (üst fitilli, küçük gövde)
        patterns["shooting_star"] = (
            rg > 2.5 * b and
            uw / (rg + 1e-9) > 0.60 and
            lw / (rg + 1e-9) < 0.15 and
            b > 0.05 * rg and
            uw > 0.80 * atr
        )

        # Pin Bar Yükseliş (güçlü alt fitilin fiyat reddini göstermesi)
        patterns["pin_bar_bull"] = (
            lw > 2.0 * b and
            uw < 0.5 * b and
            b > 0.05 * rg and
            lw > 1.0 * atr
        )

        # Pin Bar Düşüş (güçlü üst fitilin fiyat reddini göstermesi)
        patterns["pin_bar_bear"] = (
            uw > 2.0 * b and
            lw < 0.5 * b and
            b > 0.05 * rg and
            uw > 1.0 * atr
        )

        # Standart Doji
        patterns["doji"] = br < 0.10 and uw > 3 * b and lw > 3 * b

        # Dragonfly Doji (yükseliş reversal)
        patterns["dragonfly_doji"] = (
            br < 0.10 and
            lw / (rg + 1e-9) > 0.60 and
            uw / (rg + 1e-9) < 0.10
        )

        # Gravestone Doji (düşüş reversal)
        patterns["gravestone_doji"] = (
            br < 0.10 and
            uw / (rg + 1e-9) > 0.60 and
            lw / (rg + 1e-9) < 0.10
        )

        # Marubozu (tam gövde, neredeyse fitil yok)
        patterns["marubozu_bull"] = (
            br >= 0.80 and
            uw < 0.05 * b and
            lw < 0.05 * b and
            c_ > o_
        )
        patterns["marubozu_bear"] = (
            br >= 0.80 and
            uw < 0.05 * b and
            lw < 0.05 * b and
            c_ < o_
        )

        # ── Çift mum formasyonları ────────────────────────────────────────
        if len(df) >= 2:
            p0 = df.iloc[-1]
            p1 = df.iloc[-2]
            p0b = abs(float(p0["close"]) - float(p0["open"]))
            p1b = abs(float(p1["close"]) - float(p1["open"]))
            p0_bull = p0["close"] > p0["open"]
            p0_bear = p0["close"] < p0["open"]
            p1_bull = p1["close"] > p1["open"]
            p1_bear = p1["close"] < p1["open"]
            p1_rng  = float(p1["high"] - p1["low"]) + 1e-9
            p0_rng  = float(p0["high"] - p0["low"]) + 1e-9

            # Bullish Engulfing
            patterns["bull_engulfing"] = bool(
                p1_bear and p0_bull and
                p0["open"]  < p1["close"] and
                p0["close"] > p1["open"]  and
                p0b >= 1.3 * p1b
            )

            # Bearish Engulfing
            patterns["bear_engulfing"] = bool(
                p1_bull and p0_bear and
                p0["open"]  > p1["close"] and
                p0["close"] < p1["open"]  and
                p0b >= 1.3 * p1b
            )

            # Inside Bar (mevcut bar tamamen önceki barın içinde)
            is_inside = (
                float(p0["high"]) < float(p1["high"]) and
                float(p0["low"])  > float(p1["low"])  and
                float(p1b) / p1_rng > 0.30   # güçlü anne mum
            )
            # Inside bar: kırılma yönünde bonus (şimdilik trend yönünde)
            patterns["inside_bar_bull"] = bool(is_inside and p1_bull)
            patterns["inside_bar_bear"] = bool(is_inside and p1_bear)

            # Tweezer Bottom
            low_diff = abs(float(p0["low"]) - float(p1["low"])) / (float(p0["low"]) + 1e-9)
            patterns["tweezer_bottom"] = bool(
                low_diff < 0.002 and
                p1_bear and p0_bull and
                float(p1b) / p1_rng > 0.20 and
                float(p0b) / p0_rng > 0.20
            )

            # Tweezer Top
            high_diff = abs(float(p0["high"]) - float(p1["high"])) / (float(p0["high"]) + 1e-9)
            patterns["tweezer_top"] = bool(
                high_diff < 0.002 and
                p1_bull and p0_bear and
                float(p1b) / p1_rng > 0.20 and
                float(p0b) / p0_rng > 0.20
            )

        # ── Üç mum formasyonları ──────────────────────────────────────────
        if len(df) >= 3:
            c0 = df.iloc[-1]
            c1 = df.iloc[-2]
            c2 = df.iloc[-3]

            def _body_ratio(c: pd.Series) -> float:
                return abs(float(c["close"]) - float(c["open"])) / (float(c["high"]) - float(c["low"]) + 1e-9)

            def _small_uw(c: pd.Series) -> bool:
                b_  = abs(float(c["close"]) - float(c["open"]))
                uw_ = float(c["high"]) - max(float(c["open"]), float(c["close"]))
                return uw_ < b_

            def _small_lw(c: pd.Series) -> bool:
                b_  = abs(float(c["close"]) - float(c["open"]))
                lw_ = min(float(c["open"]), float(c["close"])) - float(c["low"])
                return lw_ < b_

            # Morning Star
            patterns["morning_star"] = bool(
                c2["close"] < c2["open"] and _body_ratio(c2) >= 0.50 and
                _body_ratio(c1) < 0.15 and
                c0["close"] > c0["open"] and _body_ratio(c0) >= 0.50 and
                float(c0["close"]) > (float(c2["open"]) + float(c2["close"])) / 2
            )

            # Evening Star
            patterns["evening_star"] = bool(
                c2["close"] > c2["open"] and _body_ratio(c2) >= 0.50 and
                _body_ratio(c1) < 0.15 and
                c0["close"] < c0["open"] and _body_ratio(c0) >= 0.50 and
                float(c0["close"]) < (float(c2["open"]) + float(c2["close"])) / 2
            )

            # Three White Soldiers
            patterns["three_white_sol"] = bool(
                c0["close"] > c0["open"] and
                c1["close"] > c1["open"] and
                c2["close"] > c2["open"] and
                float(c0["open"]) > float(c1["open"]) and float(c0["open"]) < float(c1["close"]) and
                float(c1["open"]) > float(c2["open"]) and float(c1["open"]) < float(c2["close"]) and
                float(c0["close"]) > float(c1["high"]) and
                float(c1["close"]) > float(c2["high"]) and
                _small_uw(c0) and _small_uw(c1)
            )

            # Three Black Crows
            patterns["three_black_crows"] = bool(
                c0["close"] < c0["open"] and
                c1["close"] < c1["open"] and
                c2["close"] < c2["open"] and
                float(c0["open"]) < float(c1["open"]) and float(c0["open"]) > float(c1["close"]) and
                float(c1["open"]) < float(c2["open"]) and float(c1["open"]) > float(c2["close"]) and
                float(c0["close"]) < float(c1["low"]) and
                float(c1["close"]) < float(c2["low"]) and
                _small_lw(c0) and _small_lw(c1)
            )

        # ── Market structure ──────────────────────────────────────────────
        market_structure, swing_high_val, swing_low_val = self._detect_structure(df)

        # ── Skorları topla ────────────────────────────────────────────────
        bull_score = 0.0
        bear_score = 0.0
        top_bull   = ""
        top_bear   = ""

        for p, w in self.BULL_WEIGHTS.items():
            if patterns.get(p, False):
                bull_score += w
                if not top_bull:
                    top_bull = p

        for p, w in self.BEAR_WEIGHTS.items():
            if patterns.get(p, False):
                bear_score += w
                if not top_bear:
                    top_bear = p

        # ── S/R yakınlığı ─────────────────────────────────────────────────
        current_price = float(close.iloc[-1])
        sr_zone = atr * 1.5
        at_support    = swing_low_val > 0  and abs(current_price - swing_low_val)  < sr_zone
        at_resistance = swing_high_val > 0 and abs(current_price - swing_high_val) < sr_zone

        # S/R yakınlığı → skor x1.3 (formasyon güvenilirliği artar)
        if at_support    and bull_score > 0:
            bull_score = min(1.0, bull_score * 1.3)
        if at_resistance and bear_score > 0:
            bear_score = min(1.0, bear_score * 1.3)

        # ── Yapı uyumu bonusu ─────────────────────────────────────────────
        if market_structure == "UPTREND"   and bull_score > 0:
            bull_score = min(1.0, bull_score + 0.10)
        elif market_structure == "DOWNTREND" and bear_score > 0:
            bear_score = min(1.0, bear_score + 0.10)

        # ── Hacim teyidi bonusu ───────────────────────────────────────────
        if len(df) >= 20:
            vol_avg = float(volume.tail(20).mean())
            vol_now = float(volume.iloc[-1])
            if vol_avg > 0 and vol_now > 1.5 * vol_avg:
                if bull_score > 0:
                    bull_score = min(1.0, bull_score + 0.08)
                if bear_score > 0:
                    bear_score = min(1.0, bear_score + 0.08)

        top_pattern = top_bull if bull_score >= bear_score else top_bear

        return PriceActionResult(
            bull_score=round(min(bull_score, 1.0), 3),
            bear_score=round(min(bear_score, 1.0), 3),
            top_pattern=top_pattern,
            market_structure=market_structure,
            at_support=at_support,
            at_resistance=at_resistance,
            swing_high=swing_high_val,
            swing_low=swing_low_val,
        )

    # ─────────────────────────────────────────────────────────────────────
    def _detect_structure(
        self, df: pd.DataFrame, window: int = 10
    ) -> tuple[str, float, float]:
        """
        Swing H/L tespiti → HH/HL/LH/LL → trend sınıflandırması.
        Döndürür: (market_structure, son_swing_high, son_swing_low)
        """
        if len(df) < window * 2 + 5:
            return "UNKNOWN", 0.0, 0.0

        highs = df["high"].values
        lows  = df["low"].values
        n     = len(df)

        swing_highs: list[float] = []
        swing_lows:  list[float] = []

        for i in range(window, n - window):
            lh = highs[i - window : i]
            rh = highs[i + 1     : i + window + 1]
            if highs[i] > lh.max() and highs[i] > rh.max():
                swing_highs.append(float(highs[i]))

            ll = lows[i - window : i]
            rl = lows[i + 1      : i + window + 1]
            if lows[i] < ll.min() and lows[i] < rl.min():
                swing_lows.append(float(lows[i]))

        sh_val = swing_highs[-1] if swing_highs else 0.0
        sl_val = swing_lows[-1]  if swing_lows  else 0.0

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]
            hl = swing_lows[-1]  > swing_lows[-2]
            lh = swing_highs[-1] < swing_highs[-2]
            ll = swing_lows[-1]  < swing_lows[-2]

            if hh and hl:
                structure = "UPTREND"
            elif lh and ll:
                structure = "DOWNTREND"
            else:
                structure = "RANGING"
        else:
            structure = "UNKNOWN"

        return structure, sh_val, sl_val
