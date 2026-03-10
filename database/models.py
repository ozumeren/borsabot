import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, Index
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    coin               = Column(String(20), nullable=False, index=True)
    direction          = Column(String(10), nullable=False)   # 'long' | 'short'
    status             = Column(String(25), nullable=False, default="OPEN")
    # OPEN | CLOSED_TP | CLOSED_SL | CLOSED_MANUAL | CLOSED_CIRCUIT | PAPER

    entry_price        = Column(Float, nullable=False)
    exit_price         = Column(Float, nullable=True)
    stop_loss_price    = Column(Float, nullable=False)
    take_profit_price  = Column(Float, nullable=True)
    quantity           = Column(Float, nullable=False)
    margin_used        = Column(Float, nullable=False)
    leverage           = Column(Integer, default=5)
    pnl_usdt           = Column(Float, nullable=True)
    pnl_pct            = Column(Float, nullable=True)

    entry_order_id     = Column(String(100), nullable=True)
    sl_order_id        = Column(String(100), nullable=True)
    tp_order_id        = Column(String(100), nullable=True)

    is_paper           = Column(Boolean, default=False)
    opened_at          = Column(DateTime, default=datetime.datetime.utcnow)
    closed_at          = Column(DateTime, nullable=True)

    technical_score    = Column(Float, nullable=True)
    sentiment_score    = Column(Float, nullable=True)
    combined_score     = Column(Float, nullable=True)
    signal_reasons     = Column(Text, nullable=True)   # JSON

    __table_args__ = (
        Index("ix_trades_status", "status"),
        Index("ix_trades_opened_at", "opened_at"),
    )


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    date                  = Column(String(10), nullable=False, unique=True)  # "2026-03-10"
    total_trades          = Column(Integer, default=0)
    winning_trades        = Column(Integer, default=0)
    losing_trades         = Column(Integer, default=0)
    total_pnl_usdt        = Column(Float, default=0.0)
    max_drawdown_pct      = Column(Float, default=0.0)
    circuit_breaker_fired = Column(Boolean, default=False)
    portfolio_value_start = Column(Float, nullable=True)
    portfolio_value_end   = Column(Float, nullable=True)
    created_at            = Column(DateTime, default=datetime.datetime.utcnow)


class SentimentLog(Base):
    __tablename__ = "sentiment_log"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    coin                = Column(String(20), nullable=False, index=True)
    timestamp           = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    cryptopanic_score   = Column(Float, nullable=True)
    fear_greed_index    = Column(Integer, nullable=True)
    combined_score      = Column(Float, nullable=True)
    source_summary      = Column(Text, nullable=True)
