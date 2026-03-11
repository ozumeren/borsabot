#!/usr/bin/env python3
"""
BorsaBot Portföy Durum Raporu
Kullanım: python status.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import datetime
import httpx
from database.db import init_db, get_session
from database.models import Trade, DailyStats


def fetch_price(coin: str) -> float:
    """OKX public API'den anlık fiyat çeker (auth gerekmez)."""
    try:
        inst_id = f"{coin}-USDT-SWAP"
        r = httpx.get(
            f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}",
            timeout=5.0,
        )
        data = r.json().get("data", [])
        if data:
            return float(data[0]["last"])
    except Exception:
        pass
    return 0.0

SEP = "─" * 60


def fmt_usdt(v: float) -> str:
    return f"${v:,.2f}"


def fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.2f}%"


def fmt_pnl(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:,.2f}"


def print_open_positions(session) -> float:
    trades = session.query(Trade).filter(Trade.status == "OPEN").order_by(Trade.opened_at).all()
    print(f"\n📂 AÇIK POZİSYONLAR ({len(trades)})")
    print(SEP)
    if not trades:
        print("  Açık pozisyon yok.")
        return 0.0

    total_margin = 0.0
    for t in trades:
        dur = datetime.datetime.utcnow() - t.opened_at
        hours = int(dur.total_seconds() // 3600)
        mins = int((dur.total_seconds() % 3600) // 60)
        yön = "LONG 📈" if t.direction == "long" else "SHORT 📉"
        current = fetch_price(t.coin)
        if current > 0 and t.entry_price > 0:
            chg = (current - t.entry_price) / t.entry_price
            if t.direction == "short":
                chg = -chg
            notional = t.margin_used * t.leverage
            fee = notional * 0.001  # %0.05 giriş + %0.05 çıkış
            unreal_pnl = chg * notional - fee
            chg_str = f"  Anlık: {fmt_usdt(current)} ({fmt_pct(chg)})  Net PnL: {fmt_pnl(unreal_pnl)}"
        else:
            chg_str = ""
        print(f"  {t.coin:<6} {yön:<10}  Giriş: {fmt_usdt(t.entry_price)}")
        if chg_str:
            print(f"        {chg_str}")
        print(f"         SL: {fmt_usdt(t.stop_loss_price)}   TP: {fmt_usdt(t.take_profit_price or 0)}")
        print(f"         Margin: {fmt_usdt(t.margin_used)}  Kaldıraç: {t.leverage}x  "
              f"Skor: {t.combined_score:.2f}  Süre: {hours}s {mins}dk")
        total_margin += t.margin_used

    print(f"\n  Toplam kullanılan margin: {fmt_usdt(total_margin)}")
    return total_margin


def print_daily_stats(session) -> None:
    today = datetime.date.today().isoformat()
    stats = session.query(DailyStats).filter_by(date=today).first()
    print(f"\n📊 BUGÜNKÜ İSTATİSTİKLER ({today})")
    print(SEP)
    if not stats:
        print("  Bugün henüz kapanmış işlem yok.")
        return

    total = stats.total_trades or 0
    win_rate = (stats.winning_trades / total * 100) if total > 0 else 0
    pnl = stats.total_pnl_usdt or 0.0
    cb = "🔴 ATEŞLENDI" if stats.circuit_breaker_fired else "🟢 Aktif"

    print(f"  İşlem sayısı  : {total}  (✅ {stats.winning_trades} kazanç / ❌ {stats.losing_trades} kayıp)")
    print(f"  Kazanma oranı : {win_rate:.1f}%")
    print(f"  Günlük PnL    : {fmt_pnl(pnl)}")
    print(f"  Max Drawdown  : {fmt_pct(stats.max_drawdown_pct or 0)}")
    print(f"  Circuit Breaker: {cb}")


def print_recent_trades(session, limit: int = 5) -> None:
    trades = (
        session.query(Trade)
        .filter(Trade.status != "OPEN")
        .order_by(Trade.closed_at.desc())
        .limit(limit)
        .all()
    )
    print(f"\n🕐 SON {limit} KAPANAN İŞLEM")
    print(SEP)
    if not trades:
        print("  Henüz kapanmış işlem yok.")
        return

    for t in trades:
        pnl = t.pnl_usdt or 0.0
        pnl_pct = t.pnl_pct or 0.0
        emoji = "✅" if pnl >= 0 else "❌"
        closed = t.closed_at.strftime("%m-%d %H:%M") if t.closed_at else "?"
        print(f"  {emoji} {t.coin:<6} {t.direction.upper():<5}  "
              f"{t.status:<14}  PnL: {fmt_pnl(pnl)} ({fmt_pct(pnl_pct)})  {closed}")


def print_all_time_stats(session) -> None:
    from sqlalchemy import func
    closed = session.query(Trade).filter(Trade.status != "OPEN")
    total = closed.count()
    wins = closed.filter(Trade.pnl_usdt > 0).count()
    total_pnl = session.query(func.sum(Trade.pnl_usdt)).filter(Trade.status != "OPEN").scalar() or 0.0
    open_count = session.query(Trade).filter(Trade.status == "OPEN").count()

    print("\n📈 TÜM ZAMANLAR")
    print(SEP)
    win_rate = (wins / total * 100) if total > 0 else 0
    print(f"  Toplam kapalı işlem : {total}  (✅ {wins} / ❌ {total - wins})")
    print(f"  Kazanma oranı       : {win_rate:.1f}%")
    print(f"  Toplam PnL          : {fmt_pnl(total_pnl)}")
    print(f"  Şu an açık pozisyon : {open_count}")


def main() -> None:
    print("\n" + "═" * 60)
    print("  🤖  BORSABOT — PORTFÖY DURUM RAPORU")
    print(f"  {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("═" * 60)

    init_db()
    with get_session() as session:
        print_open_positions(session)
        print_daily_stats(session)
        print_recent_trades(session)
        print_all_time_stats(session)

    print("\n" + "═" * 60 + "\n")


if __name__ == "__main__":
    main()
