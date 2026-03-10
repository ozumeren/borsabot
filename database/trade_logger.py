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

    def get_open_trades(self) -> list[Trade]:
        with get_session() as session:
            return session.query(Trade).filter(Trade.status == "OPEN").all()

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
