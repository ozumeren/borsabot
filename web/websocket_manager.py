import asyncio
import json
import time
from typing import Any
from fastapi import WebSocket
from utils.logger import get_logger

logger = get_logger("web.ws")

# Pozisyon fiyat önbelleği — exchange çağrısını 10s'de bir sınırla
_price_cache: dict[str, tuple[float, float]] = {}  # coin → (fiyat, ts)
_PRICE_TTL = 10.0


class WebSocketManager:
    def __init__(self) -> None:
        self._live_clients: list[WebSocket] = []
        self._signal_clients: list[WebSocket] = []

    async def connect_live(self, ws: WebSocket) -> None:
        await ws.accept()
        self._live_clients.append(ws)
        logger.info("WS live client connected", total=len(self._live_clients))

    async def connect_signals(self, ws: WebSocket) -> None:
        await ws.accept()
        self._signal_clients.append(ws)
        logger.info("WS signals client connected", total=len(self._signal_clients))

    def disconnect_live(self, ws: WebSocket) -> None:
        self._live_clients = [c for c in self._live_clients if c is not ws]

    def disconnect_signals(self, ws: WebSocket) -> None:
        self._signal_clients = [c for c in self._signal_clients if c is not ws]

    async def _broadcast(self, clients: list[WebSocket], data: dict) -> None:
        dead: list[WebSocket] = []
        payload = json.dumps(data, default=str)
        for ws in list(clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in clients:
                clients.remove(ws)

    async def broadcast_live(self, data: dict) -> None:
        await self._broadcast(self._live_clients, data)

    async def broadcast_signals(self, data: dict) -> None:
        await self._broadcast(self._signal_clients, data)


ws_manager = WebSocketManager()


def _serialize_position(coin: str, pos: Any, current_price: float | None = None) -> dict:
    if hasattr(pos, "__dict__"):
        d = {k: v for k, v in pos.__dict__.items() if not k.startswith("_")}
        d["coin"] = coin
        d["current_price"] = current_price
        return d
    if isinstance(pos, dict):
        return {"coin": coin, "current_price": current_price, **pos}
    return {"coin": coin}


async def _fetch_prices(engine: Any, coins: list[str]) -> dict[str, float]:
    """Açık pozisyonlar için anlık fiyat — state cache → bellek cache → exchange."""
    result: dict[str, float] = {}
    now = time.time()
    to_fetch: list[str] = []

    for coin in coins:
        p = engine.state.last_prices.get(coin)
        if p:
            result[coin] = float(p)
            continue
        cached = _price_cache.get(coin)
        if cached and now - cached[1] < _PRICE_TTL:
            result[coin] = cached[0]
            continue
        to_fetch.append(coin)

    if to_fetch:
        async def _one(coin: str) -> tuple[str, float | None]:
            try:
                ticker = await asyncio.to_thread(
                    engine.market_data.client.exchange.fetch_ticker,
                    f"{coin}/USDT:USDT",
                )
                price = float(ticker.get("last") or ticker.get("close") or 0)
                if price:
                    _price_cache[coin] = (price, time.time())
                    return coin, price
            except Exception:
                pass
            return coin, None

        for coin, price in await asyncio.gather(*[_one(c) for c in to_fetch]):
            if price:
                result[coin] = price

    return result


async def live_broadcaster(engine: Any) -> None:
    """Background task: her 3 saniyede canlı veri yayını."""
    from web.overview_scanner import get_cache as _overview_cache

    while True:
        try:
            state = engine.state
            coins = list(state.open_positions.keys())
            prices = await _fetch_prices(engine, coins)

            positions = [
                _serialize_position(coin, pos, prices.get(coin))
                for coin, pos in state.open_positions.items()
            ]

            cb = engine.circuit_breaker
            payload = {
                "type":                   "live",
                "ts":                     time.time(),
                "portfolio_value":        state.portfolio_value,
                "daily_pnl":              state.daily_pnl,
                "daily_trades":           state.daily_trades,
                "fear_greed_index":       state.fear_greed_index,
                "btc_regime":             state.btc_regime,
                "positions":              positions,
                "circuit_breaker_active": cb.is_triggered if hasattr(cb, "is_triggered") else False,
                "consecutive_losses":     state.consecutive_losses,
                "loss_pause_until":       state.loss_pause_until,
                "overview":               _overview_cache(),   # Tarayıcı verisi (60s'de bir değişir)
            }
            await ws_manager.broadcast_live(payload)
        except Exception as e:
            logger.warning("live_broadcaster error", error=str(e))
        await asyncio.sleep(3)


async def signals_broadcaster(engine: Any) -> None:
    """Background task: her 60 saniyede sinyal tarama yayını."""
    while True:
        try:
            state = engine.state
            scan = []
            for fs, iv in state.scan_results:
                scan.append({
                    "coin":            getattr(fs, "coin", ""),
                    "direction":       str(getattr(fs, "direction", "")),
                    "combined_score":  getattr(fs, "combined_score", 0.0),
                    "technical_score": getattr(fs, "technical_score", 0.0),
                    "sentiment_score": getattr(fs, "sentiment_score", 0.0),
                    "reasons":         getattr(fs, "reasons", []),
                })
            payload = {
                "type":        "signals",
                "ts":          time.time(),
                "btc_regime":  state.btc_regime,
                "scan_results": scan,
            }
            await ws_manager.broadcast_signals(payload)
        except Exception as e:
            logger.warning("signals_broadcaster error", error=str(e))
        await asyncio.sleep(60)
