import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException

router = APIRouter()
_engine: Any = None


def _serialize_pos(coin: str, pos: Any, current_price: float | None = None) -> dict:
    if hasattr(pos, "__dict__"):
        d = {k: v for k, v in pos.__dict__.items() if not k.startswith("_")}
        d["coin"] = coin
        if current_price is not None:
            d["current_price"] = current_price
        return d
    if isinstance(pos, dict):
        result = {"coin": coin, **pos}
        if current_price is not None:
            result["current_price"] = current_price
        return result
    return {"coin": coin}


async def _get_price(coin: str) -> float | None:
    """last_prices'da yoksa exchange'den ticker fiyatını çek."""
    price = _engine.state.last_prices.get(coin)
    if price:
        return float(price)
    try:
        symbol = f"{coin}/USDT:USDT"
        ticker = await asyncio.to_thread(
            _engine.market_data.client.exchange.fetch_ticker, symbol
        )
        last = ticker.get("last") or ticker.get("close")
        if last:
            return float(last)
    except Exception:
        pass
    # Fallback: son OHLCV çubuğundan kapat fiyatı
    try:
        df = await asyncio.to_thread(
            _engine.market_data.fetch_ohlcv,
            f"{coin}-USDT-SWAP", "1m", limit=2,
        )
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None


@router.get("/positions")
async def list_positions():
    state = _engine.state
    prices = await asyncio.gather(*[
        _get_price(coin) for coin in state.open_positions
    ])
    positions = [
        _serialize_pos(coin, pos, price)
        for (coin, pos), price in zip(state.open_positions.items(), prices)
    ]
    return {"positions": positions, "count": len(positions)}


@router.post("/positions/close/{symbol}")
async def close_position(symbol: str):
    state = _engine.state
    coin = symbol.upper()
    if coin not in state.open_positions:
        raise HTTPException(status_code=404, detail=f"No open position for {coin}")
    try:
        await _engine.close_position(coin, reason="CLOSED_MANUAL")
        return {"success": True, "coin": coin}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
