"""
Tarihsel OHLCV veri indirici.

Kullanım:
    python -m backtest.downloader --coin BTC ETH --days 180 --tf 15m
"""
import argparse
import time
import os
import pandas as pd
from datetime import datetime, timedelta, timezone

import ccxt

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _okx_exchange():
    """API key gerektirmeyen public ccxt OKX bağlantısı."""
    return ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def download_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    days: int,
) -> pd.DataFrame:
    """
    Belirtilen coin/timeframe için tarihsel OHLCV çeker.
    Pagination ile tüm verileri indirir.
    """
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_ms = int(since_dt.timestamp() * 1000)
    limit = 300
    all_candles: list = []

    print(f"  {symbol} [{timeframe}] indiriliyor — {days} gün...")
    while True:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        except Exception as e:
            print(f"  Hata: {e} — 5s bekleniyor...")
            time.sleep(5)
            continue

        if not candles:
            break

        all_candles.extend(candles)
        last_ts = candles[-1][0]
        since_ms = last_ts + 1

        if len(candles) < limit:
            break
        time.sleep(0.3)  # rate limit

    if not all_candles:
        print(f"  {symbol}: veri alınamadı!")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    print(f"  {symbol}: {len(df)} mum indirildi ({df.index[0]} → {df.index[-1]})")
    return df


def save_csv(df: pd.DataFrame, coin: str, timeframe: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{coin}_{timeframe}.csv")
    df.to_csv(path)
    print(f"  Kaydedildi: {path}")
    return path


def load_csv(coin: str, timeframe: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"{coin}_{timeframe}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Veri dosyası bulunamadı: {path}")
    df = pd.read_csv(path, index_col="timestamp", parse_dates=True)
    return df.astype(float)


def main():
    parser = argparse.ArgumentParser(description="BorsaBot OHLCV veri indirici")
    parser.add_argument("--coin", nargs="+", default=["BTC"], help="Coin sembolü (örn: BTC ETH)")
    parser.add_argument("--days", type=int, default=90, help="Kaç günlük veri (varsayılan: 90)")
    parser.add_argument("--tf", default="15m", help="Timeframe (varsayılan: 15m)")
    args = parser.parse_args()

    exchange = _okx_exchange()
    exchange.load_markets()

    for coin in args.coin:
        symbol = f"{coin}/USDT:USDT"
        df = download_ohlcv(exchange, symbol, args.tf, args.days)
        if not df.empty:
            save_csv(df, coin, args.tf)


if __name__ == "__main__":
    main()
