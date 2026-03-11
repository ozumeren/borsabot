import json
import datetime
from dataclasses import dataclass, field
from typing import Optional

from database.db import get_session
from database.models import Trade, DailyStats, SentimentLog
from utils.helpers import utcnow


@dataclass
class TradeRecord:
    coin: str
    direction: str           # 'long' | 'short'
    entry_price: float
    stop_loss_price: float
    quantity: float
    margin_used: float
    leverage: int = 5
    take_profit_price: Optional[float] = None
    exit_price: Optional[float] = None
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    is_paper: bool = False
    technical_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    combined_score: Optional[float] = None
    signal_reasons: list = field(default_factory=list)
    db_id: Optional[int] = None
    status: str = "OPEN"


class TradeLogger:
    def log_open(self, record: TradeRecord) -> int:
        with get_session() as session:
            trade = Trade(
                coin=record.coin,
                direction=record.direction,
                status="OPEN",
                entry_price=record.entry_price,
                stop_loss_price=record.stop_loss_price,
                take_profit_price=record.take_profit_price,
                quantity=record.quantity,
                margin_used=record.margin_used,
                leverage=record.leverage,
                entry_order_id=record.entry_order_id,
                sl_order_id=record.sl_order_id,
                tp_order_id=record.tp_order_id,
                is_paper=record.is_paper,
                technical_score=record.technical_score,
                sentiment_score=record.sentiment_score,
                combined_score=record.combined_score,
                signal_reasons=json.dumps(record.signal_reasons, ensure_ascii=False),
            )
            session.add(trade)
            session.flush()
            record.db_id = trade.id
            return trade.id

    def log_close(
        self,
        db_id: int,
        exit_price: float,
        status: str,
        pnl_usdt: float,
        pnl_pct: float,
    ) -> None:
        with get_session() as session:
            trade = session.get(Trade, db_id)
            if trade:
                trade.exit_price = exit_price
                trade.status = status
                trade.pnl_usdt = pnl_usdt
                trade.pnl_pct = pnl_pct
                trade.closed_at = utcnow()

    def log_partial_tp(
        self,
        db_id: int,
        tp1_price: float,
        pnl: float,
        pnl_pct: float,
        half_qty: float,
        half_margin: float,
        tp2_price: float,
        entry_price: float,
        coin: str,
        direction: str,
        leverage: int,
    ) -> int:
        """
        TP1 kısmi kapama:
        - Orijinal kaydı yarı miktar/marjinle CLOSED_TP1 olarak kapatır.
        - Kalan yarı için yeni OPEN kayıt açar (SL=entry/breakeven, TP=TP2).
        Yeni kaydın id'sini döndürür.
        """
        with get_session() as session:
            original = session.get(Trade, db_id)
            if original:
                original.quantity   = half_qty
                original.margin_used = half_margin
                original.exit_price = tp1_price
                original.status     = "CLOSED_TP1"
                original.pnl_usdt   = pnl
                original.pnl_pct    = pnl_pct
                original.closed_at  = utcnow()

            continuation = Trade(
                coin=coin,
                direction=direction,
                status="OPEN",
                entry_price=entry_price,
                stop_loss_price=entry_price,   # breakeven
                take_profit_price=tp2_price,
                quantity=half_qty,
                margin_used=half_margin,
                leverage=leverage,
                is_paper=True,
                combined_score=original.combined_score if original else 0.0,
                signal_reasons=original.signal_reasons if original else "[]",
            )
            session.add(continuation)
            session.flush()
            return continuation.id

    def get_open_trades(self) -> list[dict]:
        with get_session() as session:
            trades = session.query(Trade).filter(Trade.status == "OPEN").all()
            return [
                {
                    "id": t.id, "coin": t.coin, "direction": t.direction,
                    "entry_price": t.entry_price, "stop_loss_price": t.stop_loss_price,
                    "take_profit_price": t.take_profit_price, "quantity": t.quantity,
                    "margin_used": t.margin_used, "leverage": t.leverage,
                    "is_paper": t.is_paper,
                }
                for t in trades
            ]

    def get_recent_win_rate(self, last_n: int = 20) -> Optional[float]:
        """Son N kapalı trade'in win rate'ini döndürür. Yeterli veri yoksa None."""
        with get_session() as session:
            trades = (
                session.query(Trade)
                .filter(Trade.status != "OPEN")
                .order_by(Trade.closed_at.desc())
                .limit(last_n)
                .all()
            )
            if len(trades) < 5:
                return None
            wins = sum(1 for t in trades if t.pnl_usdt is not None and t.pnl_usdt > 0)
            return wins / len(trades)

    def log_daily_stats(self, stats: dict) -> None:
        today = datetime.date.today().isoformat()
        with get_session() as session:
            existing = session.query(DailyStats).filter_by(date=today).first()
            if existing:
                for k, v in stats.items():
                    setattr(existing, k, v)
            else:
                session.add(DailyStats(date=today, **stats))

    def log_sentiment(
        self,
        coin: str,
        cryptopanic_score: float,
        fear_greed_index: int,
        combined_score: float,
        summary: str = "",
    ) -> None:
        with get_session() as session:
            session.add(SentimentLog(
                coin=coin,
                cryptopanic_score=cryptopanic_score,
                fear_greed_index=fear_greed_index,
                combined_score=combined_score,
                source_summary=summary,
            ))
