from typing import Any, Optional
from fastapi import APIRouter, Query
from database.db import get_session
from database.models import Trade, DailyStats

router = APIRouter()
_engine: Any = None


@router.get("/trades")
async def list_trades(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    coin: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
):
    with get_session() as session:
        q = session.query(Trade)
        if status:
            q = q.filter(Trade.status == status.upper())
        if coin:
            q = q.filter(Trade.coin == coin.upper())
        if direction:
            q = q.filter(Trade.direction == direction.lower())

        total = q.count()
        rows = (
            q.order_by(Trade.opened_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        trades = [
            {
                "id": t.id,
                "coin": t.coin,
                "direction": t.direction,
                "status": t.status,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_loss_price": t.stop_loss_price,
                "take_profit_price": t.take_profit_price,
                "quantity": t.quantity,
                "margin_used": t.margin_used,
                "leverage": t.leverage,
                "pnl_usdt": t.pnl_usdt,
                "pnl_pct": t.pnl_pct,
                "is_paper": t.is_paper,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "technical_score": t.technical_score,
                "sentiment_score": t.sentiment_score,
                "combined_score": t.combined_score,
                "signal_reasons": t.signal_reasons,
            }
            for t in rows
        ]

    return {
        "trades": trades,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/trades/stats")
async def get_stats():
    with get_session() as session:
        # Daily stats last 30 days
        daily = (
            session.query(DailyStats)
            .order_by(DailyStats.date.desc())
            .limit(30)
            .all()
        )

        # Lifetime aggregates from trades table
        closed = session.query(Trade).filter(Trade.status != "OPEN").all()
        total = len(closed)
        wins = sum(1 for t in closed if (t.pnl_usdt or 0) > 0)
        total_pnl = sum(t.pnl_usdt or 0 for t in closed)
        pnls = [t.pnl_usdt or 0 for t in closed]

        # Simple Sharpe (daily returns approximation)
        sharpe = None
        if len(pnls) >= 10:
            import statistics
            mean_r = statistics.mean(pnls)
            std_r = statistics.stdev(pnls)
            sharpe = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else None

        return {
            "lifetime": {
                "total_trades": total,
                "winning_trades": wins,
                "losing_trades": total - wins,
                "win_rate": wins / total if total else 0.0,
                "total_pnl_usdt": total_pnl,
                "sharpe_ratio": sharpe,
            },
            "daily": [
                {
                    "date": s.date,
                    "total_trades": s.total_trades,
                    "winning_trades": s.winning_trades,
                    "losing_trades": s.losing_trades,
                    "total_pnl_usdt": s.total_pnl_usdt,
                    "max_drawdown_pct": s.max_drawdown_pct,
                    "circuit_breaker_fired": s.circuit_breaker_fired,
                    "portfolio_value_start": s.portfolio_value_start,
                    "portfolio_value_end": s.portfolio_value_end,
                }
                for s in reversed(daily)
            ],
        }
