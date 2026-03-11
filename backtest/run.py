"""
Backtest CLI.

Kullanım:
    python -m backtest.run --coin BTC --days 90
    python -m backtest.run --coin BTC ETH SOL --days 180 --tf 15m --download
"""
from __future__ import annotations

import argparse
import sys
import os

# proje kökünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backtest.downloader import download_ohlcv, load_csv, save_csv, _okx_exchange
from backtest.engine import BacktestEngine
from backtest.report import generate_report, print_report


def main():
    parser = argparse.ArgumentParser(description="BorsaBot Backtest")
    parser.add_argument("--coin", nargs="+", default=["BTC"], help="Coin sembolü (BTC ETH ...)")
    parser.add_argument("--days", type=int, default=90, help="Kaç günlük veri")
    parser.add_argument("--tf", default="15m", help="Timeframe (varsayılan: 15m)")
    parser.add_argument("--capital", type=float, default=1000.0, help="Başlangıç sermayesi ($)")
    parser.add_argument(
        "--download", action="store_true",
        help="Veri yoksa veya yenilemek istiyorsan OKX'ten indir"
    )
    parser.add_argument("--stop-atr", type=float, default=1.5, help="SL = ATR × katsayı")
    parser.add_argument("--tp-rr", type=float, default=2.0, help="Risk/reward oranı")
    parser.add_argument("--min-score", type=float, default=0.60, help="Min teknik sinyal skoru")
    args = parser.parse_args()

    engine = BacktestEngine(
        stop_atr_mult=args.stop_atr,
        tp_rr=args.tp_rr,
        min_tech_score=args.min_score,
    )

    for coin in args.coin:
        # Veri yükle / indir
        try:
            if args.download:
                raise FileNotFoundError("Yeniden indir")
            df = load_csv(coin, args.tf)
            # Gün kontrolü
            if len(df) < args.days * 4:  # 15m = 4 bar/saat
                raise FileNotFoundError("Yetersiz veri, yeniden indir")
        except FileNotFoundError:
            print(f"{coin}: CSV bulunamadı, OKX'ten indiriliyor...")
            exchange = _okx_exchange()
            exchange.load_markets()
            symbol = f"{coin}/USDT:USDT"
            df = download_ohlcv(exchange, symbol, args.tf, args.days)
            if df.empty:
                print(f"{coin}: veri alınamadı, atlanıyor.")
                continue
            save_csv(df, coin, args.tf)

        # Son N günü kullan
        bars_per_day = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}.get(args.tf, 96)
        df = df.iloc[-(args.days * bars_per_day):]

        if len(df) < 100:
            print(f"{coin}: yeterli veri yok ({len(df)} bar), atlanıyor.")
            continue

        print(f"\n{coin} backtesti çalışıyor ({len(df)} bar)...")
        trades = engine.run(coin, df, initial_capital=args.capital)
        report = generate_report(trades, initial_capital=args.capital)
        print_report(report, coin=coin, timeframe=args.tf)


if __name__ == "__main__":
    main()
