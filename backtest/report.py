"""
Backtest raporu oluşturucu.

Hesaplanan metrikler:
  - Toplam PnL, Win Rate, Profit Factor
  - Max Drawdown (%), Sharpe Ratio (yıllıklaştırılmış)
  - Ortalama kazanç / ortalama kayıp
  - En uzun kayıp serisi
"""
from __future__ import annotations

import math
from typing import List

from backtest.engine import BacktestTrade


def generate_report(trades: List[BacktestTrade], initial_capital: float = 1000.0) -> dict:
    """
    Trade listesinden performans metriklerini hesaplar.
    Döndürür: metrik dict
    """
    closed = [t for t in trades if t.status != "OPEN"]
    if not closed:
        return {"error": "Hiç tamamlanmış trade yok"}

    # ── Temel metrikler ───────────────────────────────────────────────────────
    total_pnl = sum(t.pnl_usdt for t in closed)
    wins  = [t for t in closed if t.pnl_usdt > 0]
    loses = [t for t in closed if t.pnl_usdt <= 0]

    win_rate    = len(wins) / len(closed) if closed else 0.0
    avg_win     = sum(t.pnl_usdt for t in wins) / len(wins) if wins else 0.0
    avg_loss    = sum(t.pnl_usdt for t in loses) / len(loses) if loses else 0.0

    gross_profit = sum(t.pnl_usdt for t in wins)
    gross_loss   = abs(sum(t.pnl_usdt for t in loses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # ── Max Drawdown ─────────────────────────────────────────────────────────
    equity = initial_capital
    peak   = equity
    max_dd = 0.0
    for t in closed:
        equity += t.pnl_usdt
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # ── Sharpe Ratio (yıllıklaştırılmış, günlük PnL kullanarak) ──────────────
    # Her trade'i ayrı bir günmüş gibi modelle — yaklaşım
    pnl_series = [t.pnl_pct for t in closed]
    n = len(pnl_series)
    if n > 1:
        mean_r  = sum(pnl_series) / n
        std_r   = math.sqrt(sum((r - mean_r) ** 2 for r in pnl_series) / (n - 1))
        # Yaklaşık yıllıklaştırma: 252 işlem günü
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # ── En uzun kayıp serisi ─────────────────────────────────────────────────
    max_losing_streak = 0
    current_streak    = 0
    for t in closed:
        if t.pnl_usdt <= 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    # ── Sonuç ─────────────────────────────────────────────────────────────────
    return {
        "total_trades":       len(closed),
        "winning_trades":     len(wins),
        "losing_trades":      len(loses),
        "win_rate":           win_rate,
        "total_pnl_usdt":     total_pnl,
        "total_pnl_pct":      total_pnl / initial_capital,
        "avg_win_usdt":       avg_win,
        "avg_loss_usdt":      avg_loss,
        "profit_factor":      profit_factor,
        "max_drawdown_pct":   max_dd,
        "sharpe_ratio":       sharpe,
        "max_losing_streak":  max_losing_streak,
        "avg_duration_bars":  sum(t.duration_bars for t in closed) / len(closed) if closed else 0,
    }


def print_report(report: dict, coin: str = "", timeframe: str = "15m") -> None:
    """Raporu terminale yazdırır."""
    sep = "─" * 45
    print(f"\n{sep}")
    print(f"  BACKTEST RAPORU — {coin} [{timeframe}]")
    print(sep)
    if "error" in report:
        print(f"  HATA: {report['error']}")
        return

    wr = report["win_rate"]
    pf = report["profit_factor"]
    pnl = report["total_pnl_usdt"]
    pnl_pct = report["total_pnl_pct"] * 100
    dd = report["max_drawdown_pct"] * 100
    sh = report["sharpe_ratio"]

    print(f"  İşlem Sayısı    : {report['total_trades']} ({report['winning_trades']}W / {report['losing_trades']}L)")
    print(f"  Win Rate        : {wr:.1%}")
    print(f"  Profit Factor   : {pf:.2f}")
    print(f"  Toplam PnL      : {'+'if pnl>=0 else ''}{pnl:.2f} USDT  ({pnl_pct:+.2f}%)")
    print(f"  Ort. Kazanç     : +{report['avg_win_usdt']:.2f} USDT")
    print(f"  Ort. Kayıp      : {report['avg_loss_usdt']:.2f} USDT")
    print(f"  Max Drawdown    : {dd:.2f}%")
    print(f"  Sharpe Ratio    : {sh:.2f}")
    print(f"  Max Kayıp Serisi: {report['max_losing_streak']} işlem")
    print(f"  Ort. Süre       : {report['avg_duration_bars']:.1f} bar")
    print(sep)
