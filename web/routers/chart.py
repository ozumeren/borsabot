import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
_engine: Any = None

VALID_TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


@router.get("/chart/{symbol}")
async def get_chart(
    symbol: str,
    timeframe: str = Query(default="15m"),
    limit: int = Query(default=200, ge=50, le=500),
):
    if timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Geçersiz timeframe.")

    coin = symbol.upper()
    okx_symbol = f"{coin}/USDT:USDT"

    try:
        df = await asyncio.to_thread(
            _engine.market_data.fetch_ohlcv,
            okx_symbol, timeframe, limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Veri çekme hatası: {str(e)}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"{coin} için veri bulunamadı")

    # DataFrame index = DatetimeIndex (timestamp adlı), kolonlar: open/high/low/close/volume
    candles = []
    for ts, row in df.iterrows():
        # ts bir pandas Timestamp — Unix timestamp'e çevir (saniye cinsinden)
        t = int(ts.timestamp())
        candles.append({
            "time":   t,
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": float(row.get("volume", 0)),
        })

    candles.sort(key=lambda x: x["time"])

    last_price = candles[-1]["close"] if candles else None
    change_pct = None
    if len(candles) >= 2:
        change_pct = (candles[-1]["close"] - candles[0]["close"]) / candles[0]["close"] * 100

    return {
        "coin":       coin,
        "timeframe":  timeframe,
        "candles":    candles,
        "last_price": last_price,
        "change_pct": change_pct,
        "count":      len(candles),
    }
