from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
_engine: Any = None


class SettingsUpdate(BaseModel):
    leverage: Optional[int] = None
    max_leverage: Optional[int] = None
    max_concurrent_positions: Optional[int] = None
    scan_top_n_coins: Optional[int] = None
    daily_loss_limit_pct: Optional[float] = None
    stop_loss_pct_from_entry: Optional[float] = None
    max_position_size_pct: Optional[float] = None
    min_technical_score: Optional[float] = None
    min_combined_score: Optional[float] = None


@router.get("/settings")
async def get_settings():
    s = _engine.settings
    return {
        "paper_trading": s.paper_trading,
        "leverage": s.leverage,
        "max_leverage": s.max_leverage,
        "margin_mode": s.margin_mode,
        "max_concurrent_positions": s.max_concurrent_positions,
        "timeframe": s.timeframe,
        "scan_top_n_coins": s.scan_top_n_coins,
        "daily_loss_limit_pct": s.daily_loss_limit_pct,
        "stop_loss_pct_from_entry": s.stop_loss_pct_from_entry,
        "max_position_size_pct": s.max_position_size_pct,
        "min_technical_score": s.min_technical_score,
        "min_combined_score": s.min_combined_score,
        "database_url": s.database_url,
    }


@router.put("/settings")
async def update_settings(body: SettingsUpdate):
    s = _engine.settings
    updated = []
    for field, value in body.model_dump(exclude_none=True).items():
        if hasattr(s, field):
            setattr(s, field, value)
            updated.append(field)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown setting: {field}")

    # Keep position_sizer and other components in sync
    if "leverage" in updated or "max_position_size_pct" in updated:
        _engine.position_sizer.leverage = s.leverage
        _engine.position_sizer.max_position_pct = s.max_position_size_pct

    if "daily_loss_limit_pct" in updated:
        _engine.circuit_breaker.daily_loss_limit_pct = s.daily_loss_limit_pct

    if "stop_loss_pct_from_entry" in updated:
        _engine.stop_calc.default_stop_pct = s.stop_loss_pct_from_entry

    return {"updated": updated, "settings": await get_settings()}
