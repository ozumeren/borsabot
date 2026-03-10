"""
Canlı işlem motoru — PAPER_TRADING=false olduğunda aktif.
FinalSignal → OKX emir gönderimi.
"""
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
            signal.direction, signal.entry_price, atr=None
        )
        tp_price = self.stop_calc.calculate_take_profit(
            signal.direction, signal.entry_price, sl_price
        )
        sizing = self.position_sizer.calculate(
            portfolio_value=portfolio_value,
            entry_price=signal.entry_price,
            stop_loss_price=sl_price,
            signal_score=signal.combined_score,
        )

        if sizing.quantity <= 0:
            logger.warning("Sıfır pozisyon boyutu, işlem yapılmıyor", coin=signal.coin)
            return None

        try:
            if direction == "long":
                result = self.order_manager.open_long(
                    symbol, sizing.quantity, self.settings.leverage,
                    sl_price, tp_price
                )
            else:
                result = self.order_manager.open_short(
                    symbol, sizing.quantity, self.settings.leverage,
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
                leverage=self.settings.leverage,
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
            self.notifier.send_alert(f"İşlem açılamadı: {signal.coin}\n{str(e)}")
            return None
