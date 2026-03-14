from typing import Any
from fastapi import APIRouter
from database.db import get_session
from database.models import Trade, DailyStats

router = APIRouter()
_engine: Any = None


@router.get("/dashboard")
async def get_dashboard():
    state = _engine.state
    settings = _engine.settings

    # Last 30 days equity from DB
    with get_session() as session:
        stats = (
            session.query(DailyStats)
            .order_by(DailyStats.date.desc())
            .limit(30)
            .all()
        )
        equity_curve = [
            {"date": s.date, "value": s.portfolio_value_end or s.portfolio_value_start or 0}
            for s in reversed(stats)
        ]

        recent_trades = (
            session.query(Trade)
            .filter(Trade.status != "OPEN")
            .order_by(Trade.closed_at.desc())
            .limit(5)
            .all()
        )
        recent = [
            {
                "id": t.id,
                "coin": t.coin,
                "direction": t.direction,
                "pnl_usdt": t.pnl_usdt,
                "pnl_pct": t.pnl_pct,
                "status": t.status,
                "closed_at": t.closed_at,
            }
            for t in recent_trades
        ]

        # Lifetime stats
        all_closed = session.query(Trade).filter(Trade.status != "OPEN").all()
        total_pnl = sum(t.pnl_usdt or 0 for t in all_closed)
        wins = sum(1 for t in all_closed if (t.pnl_usdt or 0) > 0)
        win_rate = wins / len(all_closed) if all_closed else 0.0

    positions = [
        _serialize_pos(coin, pos)
        for coin, pos in state.open_positions.items()
    ]

    # Best opportunity
    best = None
    if state.best_opportunity:
        fs, iv = state.best_opportunity
        best = {
            "coin": getattr(fs, "coin", ""),
            "direction": str(getattr(fs, "direction", "")),
            "combined_score": getattr(fs, "combined_score", 0.0),
            "reasons": getattr(fs, "reasons", []),
        }

    return {
        "portfolio_value": state.portfolio_value,
        "daily_pnl": state.daily_pnl,
        "daily_trades": state.daily_trades,
        "daily_winning": state.daily_winning,
        "daily_losing": state.daily_losing,
        "max_drawdown_pct": state.max_drawdown_pct,
        "fear_greed_index": state.fear_greed_index,
        "btc_regime": state.btc_regime,
        "open_positions_count": len(state.open_positions),
        "consecutive_losses": state.consecutive_losses,
        "paper_trading": settings.paper_trading,
        "equity_curve": equity_curve,
        "recent_trades": recent,
        "open_positions": positions,
        "best_opportunity": best,
        "lifetime_pnl": total_pnl,
        "lifetime_win_rate": win_rate,
        "lifetime_trades": len(all_closed),
    }


def _serialize_pos(coin: str, pos: Any) -> dict:
    if hasattr(pos, "__dict__"):
        d = {k: v for k, v in pos.__dict__.items() if not k.startswith("_")}
        d["coin"] = coin
        return d
    if isinstance(pos, dict):
        return {"coin": coin, **pos}
    return {"coin": coin}
