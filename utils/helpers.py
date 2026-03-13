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
    """Fiyatı anlamlı basamak sayısıyla gösterir (küçük coinlerde kusuratlar kaybolmasın)."""
    abs_val = abs(amount)
    if abs_val == 0:
        return "$0.00"
    elif abs_val >= 1000:
        return f"${amount:,.2f}"
    elif abs_val >= 1:
        return f"${amount:,.4f}"
    elif abs_val >= 0.01:
        return f"${amount:,.6f}"
    else:
        return f"${amount:,.8f}"


def format_price(price: float) -> str:
    """Coin fiyatı için — büyük coinlerde 2, küçüklerde 6-8 ondalık."""
    if price >= 100:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.4f}"
    elif price >= 0.0001:
        return f"${price:,.6f}"
    else:
        return f"${price:,.8f}"


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def coin_from_symbol(symbol: str) -> str:
    """'BTC/USDT:USDT' → 'BTC'"""
    return symbol.split("/")[0]


def symbol_to_okx(coin: str) -> str:
    """'BTC' → 'BTC/USDT:USDT' (OKX perpetual swap formatı)"""
    return f"{coin}/USDT:USDT"
