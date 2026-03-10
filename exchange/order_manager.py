from typing import Optional
from exchange.client import OKXClient
from utils.logger import get_logger

logger = get_logger("exchange.order_manager")


class OrderManager:
    """Açık pozisyon yönetimi: emir gönder, iptal et, kapat."""

    def __init__(self, client: OKXClient):
        self.client = client

    def open_long(
        self,
        symbol: str,
        quantity: float,
        leverage: int,
        stop_loss_price: float,
        take_profit_price: Optional[float] = None,
    ) -> dict:
        """Tam LONG pozisyon açma: giriş + SL + TP."""
        self.client.set_leverage(symbol, leverage, "long")

        # Giriş emri
        entry = self.client.create_market_order(symbol, "buy", quantity, "long")
        logger.info("LONG giriş emri gönderildi", symbol=symbol, qty=quantity, order=entry["id"])

        # Stop-loss trigger
        sl = self.client.create_trigger_order(
            symbol, "sell", quantity, stop_loss_price, "long", reduce_only=True
        )
        logger.info("SL emri gönderildi", symbol=symbol, sl_price=stop_loss_price, order=sl["id"])

        tp = None
        if take_profit_price:
            tp = self.client.create_trigger_order(
                symbol, "sell", quantity, take_profit_price, "long", reduce_only=True
            )
            logger.info("TP emri gönderildi", symbol=symbol, tp_price=take_profit_price, order=tp["id"])

        return {
            "entry_order": entry,
            "sl_order": sl,
            "tp_order": tp,
            "entry_price": float(entry.get("average") or entry.get("price") or 0),
        }

    def open_short(
        self,
        symbol: str,
        quantity: float,
        leverage: int,
        stop_loss_price: float,
        take_profit_price: Optional[float] = None,
    ) -> dict:
        """Tam SHORT pozisyon açma: giriş + SL + TP."""
        self.client.set_leverage(symbol, leverage, "short")

        entry = self.client.create_market_order(symbol, "sell", quantity, "short")
        logger.info("SHORT giriş emri gönderildi", symbol=symbol, qty=quantity, order=entry["id"])

        sl = self.client.create_trigger_order(
            symbol, "buy", quantity, stop_loss_price, "short", reduce_only=True
        )

        tp = None
        if take_profit_price:
            tp = self.client.create_trigger_order(
                symbol, "buy", quantity, take_profit_price, "short", reduce_only=True
            )

        return {
            "entry_order": entry,
            "sl_order": sl,
            "tp_order": tp,
            "entry_price": float(entry.get("average") or entry.get("price") or 0),
        }

    def close_position(self, symbol: str, direction: str, quantity: float) -> dict:
        """Market fiyattan pozisyonu kapat."""
        side = "sell" if direction == "long" else "buy"
        order = self.client.create_market_order(
            symbol, side, quantity, direction, reduce_only=True
        )
        logger.info("Pozisyon kapatıldı", symbol=symbol, direction=direction)
        return order

    def cancel_order_safe(self, order_id: str, symbol: str) -> bool:
        """Emir iptali - hata durumunda False döner."""
        try:
            self.client.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.warning("Emir iptal edilemedi", order_id=order_id, error=str(e))
            return False
