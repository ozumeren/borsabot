"""
Canlı işlem motoru — PAPER_TRADING=false olduğunda aktif.
FinalSignal → OKX emir gönderimi.
"""
import datetime
from typing import Optional
from signals.combiner import FinalSignal
from signals.technical_signal import Direction
from exchange.order_manager import OrderManager
from exchange.client import OKXClient
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.circuit_breaker import CircuitBreaker
from database.trade_logger import TradeLogger, TradeRecord
from notifications.telegram_bot import TelegramNotifier
from core.state import BotState
from config.settings import BotSettings
from utils.logger import get_logger
from utils.helpers import format_usdt, symbol_to_okx

logger = get_logger("execution.trade_executor")


class TradeExecutor:
    """Canlı OKX işlem yürütücüsü."""

    def __init__(
        self,
        client: OKXClient,
        position_sizer: PositionSizer,
        stop_calc: StopLossCalculator,
        circuit_breaker: CircuitBreaker,
        trade_logger: TradeLogger,
        state: BotState,
        notifier: TelegramNotifier,
        settings: BotSettings,
    ):
        self.client = client
        self.order_manager = OrderManager(client)
        self.position_sizer = position_sizer
        self.stop_calc = stop_calc
        self.circuit_breaker = circuit_breaker
        self.trade_logger = trade_logger
        self.state = state
        self.notifier = notifier
        self.settings = settings

    def execute(self, signal: FinalSignal, portfolio_value: float) -> Optional[TradeRecord]:
        if not signal.is_actionable:
            return None

        allowed, reason = self.circuit_breaker.is_trading_allowed(
            len(self.state.open_positions)
        )
        if not allowed:
            logger.info("İşlem circuit breaker tarafından engellendi", reason=reason)
            return None

        if signal.coin in self.state.open_positions:
            logger.debug("Pozisyon zaten var, atlanıyor", coin=signal.coin)
            return None

        symbol    = symbol_to_okx(signal.coin)
        direction = "long" if signal.direction == Direction.LONG else "short"

        sl_price = self.stop_calc.calculate_stop_loss(
            signal.direction, signal.entry_price,
            atr=signal.atr, adx=signal.adx, bb_width_pct=signal.bb_width_pct,
        )
        tp_price = self.stop_calc.calculate_take_profit(
            signal.direction, signal.entry_price, sl_price
        )
        sizing = self.position_sizer.calculate(
            portfolio_value=portfolio_value,
            entry_price=signal.entry_price,
            stop_loss_price=sl_price,
            signal_score=signal.combined_score,
            atr=signal.atr,
            leverage=signal.leverage,
        )

        if sizing.quantity <= 0:
            logger.warning("Sıfır pozisyon boyutu, işlem yapılmıyor", coin=signal.coin)
            return None

        try:
            if direction == "long":
                result = self.order_manager.open_long(
                    symbol, sizing.quantity, signal.leverage,
                    sl_price, tp_price
                )
            else:
                result = self.order_manager.open_short(
                    symbol, sizing.quantity, signal.leverage,
                    sl_price, tp_price
                )

            actual_entry = result["entry_price"] or signal.entry_price

            record = TradeRecord(
                coin=signal.coin,
                direction=direction,
                entry_price=actual_entry,
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                quantity=sizing.quantity,
                margin_used=sizing.margin_required,
                leverage=signal.leverage,
                is_paper=False,
                entry_order_id=result["entry_order"]["id"],
                sl_order_id=result["sl_order"]["id"],
                tp_order_id=result["tp_order"]["id"] if result.get("tp_order") else None,
                technical_score=signal.technical_score,
                sentiment_score=signal.sentiment_score,
                combined_score=signal.combined_score,
                signal_reasons=signal.reasons,
            )
            self.trade_logger.log_open(record)
            self.state.add_position(signal.coin, record)
            self.notifier.send_trade_opened(record, is_paper=False)

            logger.info(
                "CANLI pozisyon açıldı",
                coin=signal.coin,
                direction=direction,
                entry=actual_entry,
                sl=sl_price,
                tp=tp_price,
                margin=format_usdt(sizing.margin_required),
            )
            return record

        except Exception as e:
            logger.error("İşlem açılamadı", coin=signal.coin, error=str(e))
            self.notifier.send_alert(f"⚠️ İşlem açılamadı: {signal.coin}\n{str(e)}")
            return None

    def close_position(self, coin: str, reason: str = "CLOSED_MANUAL") -> bool:
        """
        Açık pozisyonu market order ile kapat.
        SL/TP emirlerini iptal eder, DB'yi günceller.
        """
        record = self.state.open_positions.get(coin)
        if not record:
            logger.warning("Kapatılacak pozisyon bulunamadı", coin=coin)
            return False

        symbol = symbol_to_okx(coin)
        try:
            # SL / TP emirlerini iptal et
            if record.sl_order_id:
                self.order_manager.cancel_order_safe(record.sl_order_id, symbol)
            if record.tp_order_id:
                self.order_manager.cancel_order_safe(record.tp_order_id, symbol)

            # Pozisyonu kapat
            close_order = self.order_manager.close_position(
                symbol, record.direction, record.quantity
            )

            exit_price = float(
                close_order.get("average") or close_order.get("price") or record.entry_price
            )

            # PnL hesapla
            if record.direction == "long":
                pnl = (exit_price - record.entry_price) * record.quantity
            else:
                pnl = (record.entry_price - exit_price) * record.quantity
            pnl_pct = pnl / record.margin_used if record.margin_used > 0 else 0.0

            # DB güncelle
            if record.db_id:
                self.trade_logger.log_close(record.db_id, exit_price, reason, pnl, pnl_pct)

            # State güncelle
            self.state.remove_position(coin)
            self.circuit_breaker.update_pnl(pnl)

            pnl_sign = "+" if pnl >= 0 else ""
            logger.info(
                "CANLI pozisyon kapatıldı",
                coin=coin, reason=reason,
                exit=exit_price, pnl=f"{pnl_sign}{pnl:.2f} USDT",
            )
            self.notifier.send_trade_closed(
                coin, reason, pnl, pnl_pct, is_paper=False,
                entry_price=record.entry_price, exit_price=exit_price,
            )
            return True

        except Exception as e:
            logger.error("Pozisyon kapatılamadı", coin=coin, error=str(e))
            self.notifier.send_alert(f"❌ Pozisyon kapatılamadı: {coin}\n{str(e)}")
            return False

    def verify_order_fill(self, order_id: str, symbol: str, timeout_seconds: int = 30) -> bool:
        """
        Emrin dolu olup olmadığını kontrol eder.
        Timeout süresince bekler. Dolmamışsa False döner.
        """
        import time
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                order = self.client.fetch_order(order_id, symbol)
                status = order.get("status", "")
                if status == "closed":
                    return True
                if status in ("canceled", "rejected", "expired"):
                    logger.warning("Emir reddedildi/iptal", order_id=order_id, status=status)
                    return False
            except Exception as e:
                logger.debug("fetch_order hatası", order_id=order_id, error=str(e))
            time.sleep(2)
        logger.warning("Emir fill doğrulaması zaman aşımı", order_id=order_id)
        return False

    def monitor_open_positions(self) -> None:
        """
        OKX'ten gerçek pozisyon durumunu çek, likidayon riskini kontrol et.
        10 saniyelik monitor job'ından çağrılır.
        """
        if not self.state.open_positions:
            return

        try:
            live_positions = self.client.fetch_positions()

            # Likidayon riski kontrolü
            at_risk = self.circuit_breaker.check_liquidation_risk(live_positions)
            for coin in at_risk:
                if coin in self.state.open_positions:
                    self.notifier.send_alert(
                        f"🚨 <b>Likidayon riski!</b> {coin} pozisyonu acil kapatılıyor."
                    )
                    self.close_position(coin, reason="CLOSED_CIRCUIT")

            # Kapanmış pozisyonları tespit et
            live_coins = {
                p["symbol"].split("/")[0]
                for p in live_positions
                if p.get("contracts", 0) > 0
            }
            for coin in list(self.state.open_positions.keys()):
                if coin not in live_coins:
                    record = self.state.open_positions.get(coin)
                    logger.info("Pozisyon OKX'te kapanmış", coin=coin)
                    if record and record.db_id:
                        # Mark price bilgisi olmadan tahmini kapat
                        self.trade_logger.log_close(
                            record.db_id, record.entry_price,
                            "CLOSED_MANUAL", 0.0, 0.0
                        )
                    self.state.remove_position(coin)

        except Exception as e:
            logger.warning("monitor_open_positions hatası", error=str(e))
