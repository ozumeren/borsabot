from typing import Any
import time
from fastapi import APIRouter

router = APIRouter()
_engine: Any = None


@router.get("/bot/status")
async def bot_status():
    state = _engine.state
    settings = _engine.settings
    cb = _engine.circuit_breaker

    paused = state.loss_pause_until > time.time()
    return {
        "running": True,
        "paper_trading": settings.paper_trading,
        "portfolio_value": state.portfolio_value,
        "daily_pnl": state.daily_pnl,
        "daily_trades": state.daily_trades,
        "open_positions": len(state.open_positions),
        "fear_greed_index": state.fear_greed_index,
        "btc_regime": state.btc_regime,
        "consecutive_losses": state.consecutive_losses,
        "loss_pause_active": paused,
        "loss_pause_until": state.loss_pause_until if paused else None,
        "circuit_breaker_active": getattr(cb, "is_triggered", False),
        "max_concurrent_positions": settings.max_concurrent_positions,
    }


@router.post("/bot/scan")
async def trigger_scan():
    """Trigger an immediate coin scan."""
    try:
        raw = await _engine.scan_coins_for_report()
        # raw: [(FinalSignal, IndicatorValues, mtf_ok), ...]
        _engine.state.scan_results = raw

        results = []
        for item in raw:
            fs = item[0]
            results.append({
                "coin": getattr(fs, "coin", ""),
                "direction": str(getattr(fs, "direction", "")),
                "combined_score": getattr(fs, "combined_score", 0.0),
                "technical_score": getattr(fs, "technical_score", 0.0),
                "sentiment_score": getattr(fs, "sentiment_score", 0.0),
                "reasons": getattr(fs, "reasons", []),
            })
        return {"success": True, "scan_results": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/bot/fetch_news")
async def trigger_fetch_news():
    try:
        await _engine.fetch_news()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/bot/fetch_fear_greed")
async def trigger_fear_greed():
    try:
        await _engine.fetch_fear_greed()
        return {"success": True, "fear_greed_index": _engine.state.fear_greed_index}
    except Exception as e:
        return {"success": False, "error": str(e)}
