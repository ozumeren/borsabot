"""
Paper Trading Engine — Gerçek para olmadan simülasyon.
PAPER_TRADING=true olduğunda TradeExecutor yerine bu kullanılır.
"""
from dataclasses import dataclass, field
from typing import Optional
from database.trade_logger import TradeLogger, TradeRecord
from signals.combiner import FinalSignal
from signals.technical_signal import Direction
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.circuit_breaker import CircuitBreaker
from utils.logger import get_logger
from utils.helpers import format_usdt, format_pct, pct_change

logger = get_logger("paper_trading")

OKX_FEE_PCT = 0.0005  # %0.05 işlem başına


@dataclass
class PaperPosition:
    coin: str
    direction: str
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    quantity: float
    margin: float
    leverage: int
    db_id: Optional[int] = None
    current_price: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        if self.direction == "long":
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.margin == 0:
            return 0.0
        return self.unrealized_pnl / self.margin


class PaperEngine:
    """Simüle edilmiş işlem motoru."""

    def __init__(
        self,
        position_sizer: PositionSizer,
        stop_calc: StopLossCalculator,
        circuit_breaker: CircuitBreaker,
        trade_logger: TradeLogger,
        notifier=None,
    ):
        self.position_sizer = position_sizer
        self.stop_calc = stop_calc
        self.circuit_breaker = circuit_breaker
        self.trade_logger = trade_logger
        self.notifier = notifier
        self.positions: dict[str, PaperPosition] = {}

    def restore_from_db(self) -> int:
        """Bot yeniden başlatılınca veritabanındaki açık pozisyonları belleğe yükler."""
        open_trades = self.trade_logger.get_open_trades()
        for t in open_trades:
            if t["coin"] in self.positions:
                continue
            pos = PaperPosition(
                coin=t["coin"],
                direction=t["direction"],
                entry_price=t["entry_price"],
                stop_loss_price=t["stop_loss_price"],
                take_profit_price=t["take_profit_price"] or 0.0,
                quantity=t["quantity"],
                margin=t["margin_used"],
                leverage=t["leverage"],
                db_id=t["id"],
                current_price=t["entry_price"],
            )
            self.positions[t["coin"]] = pos
        if open_trades:
            logger.info("Pozisyonlar DB'den yüklendi", count=len(open_trades))
        return len(open_trades)

    def open_position(self, signal: FinalSignal, portfolio_value: float) -> Optional[PaperPosition]:
        allowed, reason = self.circuit_breaker.is_trading_allowed(len(self.positions))
        if not allowed:
            logger.info("Paper işlem engellendi", reason=reason)
            return None

        if signal.coin in self.positions:
            logger.debug("Pozisyon zaten var", coin=signal.coin)
            return None

        direction = "long" if signal.direction == Direction.LONG else "short"
        sl_price = self.stop_calc.calculate_stop_loss(signal.direction, signal.entry_price)
        tp_price = self.stop_calc.calculate_take_profit(signal.direction, signal.entry_price, sl_price)

        sizing = self.position_sizer.calculate(
            portfolio_value=portfolio_value,
            entry_price=signal.entry_price,
            stop_loss_price=sl_price,
            signal_score=signal.combined_score,
        )

        record = TradeRecord(
            coin=signal.coin,
            direction=direction,
            entry_price=signal.entry_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            quantity=sizing.quantity,
            margin_used=sizing.margin_required,
            leverage=self.position_sizer.leverage,
            is_paper=True,
            technical_score=signal.technical_score,
            sentiment_score=signal.sentiment_score,
            combined_score=signal.combined_score,
            signal_reasons=signal.reasons,
        )
        db_id = self.trade_logger.log_open(record)

        pos = PaperPosition(
            coin=signal.coin,
            direction=direction,
            entry_price=signal.entry_price,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            quantity=sizing.quantity,
            margin=sizing.margin_required,
            leverage=self.position_sizer.leverage,
            db_id=db_id,
            current_price=signal.entry_price,
        )
        self.positions[signal.coin] = pos

        logger.info(
            "[PAPER] Pozisyon açıldı",
            coin=signal.coin,
            direction=direction,
            entry=signal.entry_price,
            sl=sl_price,
            tp=tp_price,
            margin=format_usdt(sizing.margin_required),
            score=f"{signal.combined_score:.2f}",
        )

        if self.notifier:
            self.notifier.send_trade_opened(pos, is_paper=True)

        return pos

    def update_prices(self, price_map: dict[str, float]) -> list[str]:
        """
        Pozisyonları günceller. SL/TP vurarsa kapatır.
        Dönen: kapanan coin listesi
        """
        closed = []
        for coin, pos in list(self.positions.items()):
            price = price_map.get(coin)
            if price is None:
                continue
            pos.current_price = price

            # SL kontrolü
            sl_hit = (
                (pos.direction == "long"  and price <= pos.stop_loss_price) or
                (pos.direction == "short" and price >= pos.stop_loss_price)
            )
            # TP kontrolü
            tp_hit = (
                (pos.direction == "long"  and price >= pos.take_profit_price) or
                (pos.direction == "short" and price <= pos.take_profit_price)
            )
            # Acil kapama
            emergency = self.circuit_breaker.should_emergency_close(pos.unrealized_pnl_pct)

            if sl_hit or tp_hit or emergency:
                status = "CLOSED_SL" if sl_hit else ("CLOSED_TP" if tp_hit else "CLOSED_CIRCUIT")
                self._close_position(coin, pos, price, status)
                closed.append(coin)

        return closed

    def _close_position(self, coin: str, pos: PaperPosition, exit_price: float, status: str) -> None:
        fee = pos.quantity * exit_price * OKX_FEE_PCT * 2  # giriş + çıkış
        pnl = pos.unrealized_pnl - fee
        pnl_pct = pnl / pos.margin if pos.margin > 0 else 0.0

        self.circuit_breaker.update_pnl(pnl)
        self.trade_logger.log_close(pos.db_id, exit_price, status, pnl, pnl_pct)

        logger.info(
            f"[PAPER] Pozisyon kapandı ({status})",
            coin=coin,
            exit=exit_price,
            pnl=format_usdt(pnl),
            pnl_pct=format_pct(pnl_pct),
        )

        if self.notifier:
            self.notifier.send_trade_closed(coin, status, pnl, pnl_pct, is_paper=True)

        del self.positions[coin]
