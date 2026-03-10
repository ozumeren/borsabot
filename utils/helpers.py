import time
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_ms() -> int:
    return int(time.time() * 1000)


def pct_change(old: float, new: float) -> float:
    """İki değer arasındaki yüzde değişimi döndürür."""
    if old == 0:
        return 0.0
    return (new - old) / old


def format_usdt(amount: float) -> str:
    return f"${amount:,.2f}"


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def coin_from_symbol(symbol: str) -> str:
    """'BTC/USDT:USDT' → 'BTC'"""
    return symbol.split("/")[0]


def symbol_to_okx(coin: str) -> str:
    """'BTC' → 'BTC/USDT:USDT' (OKX perpetual swap formatı)"""
    return f"{coin}/USDT:USDT"
