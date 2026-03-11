from dataclasses import dataclass


@dataclass
class PositionSize:
    quantity: float           # kontrat sayısı
    notional_value: float     # USDT cinsinden pozisyon değeri
    margin_required: float    # gereken teminat (USDT)
    risk_amount: float        # stop vurursa kaybedilecek USDT


class PositionSizer:
    """
    Fixed fractional + volatilite bazlı pozisyon boyutu hesaplama.

    Formül:
        margin     = portfolio * max_pct * score_multiplier * vol_multiplier
        notional   = margin * leverage
        quantity   = notional / entry_price
        risk       = margin * stop_pct * leverage

    score_multiplier : combined_score 0.55 → ×0.5, 1.0 → ×1.0
    vol_multiplier   : ATR/price > %3 → ×0.6, %1-3 → ×1.0, < %1 → ×1.2
    """

    def __init__(self, max_position_pct: float = 0.10, leverage: int = 5):
        self.max_position_pct = max_position_pct
        self.leverage = leverage

    def calculate(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_price: float,
        signal_score: float = 0.55,
        atr: float = 0.0,
        leverage: int = 0,   # 0 = self.leverage kullan (varsayılan); > 0 = dinamik kaldıraç
    ) -> PositionSize:
        if entry_price <= 0 or portfolio_value <= 0:
            return PositionSize(0.0, 0.0, 0.0, 0.0)

        lev = leverage if leverage > 0 else self.leverage

        # Sinyal gücüne göre ölçekle (0.55 → 0.5x, 1.0 → 1.0x)
        score_multiplier = min(1.0, max(0.5, (signal_score - 0.55) / 0.45 * 0.5 + 0.5))

        # Volatilite bazlı ölçekleme
        vol_multiplier = 1.0
        if atr > 0:
            vol_pct = atr / entry_price
            if vol_pct > 0.03:
                vol_multiplier = 0.6   # yüksek volatilite → küçük pozisyon
            elif vol_pct < 0.01:
                vol_multiplier = 1.2   # düşük volatilite → biraz büyük pozisyon

        margin = portfolio_value * self.max_position_pct * score_multiplier * vol_multiplier

        notional = margin * lev
        quantity = notional / entry_price

        stop_pct = abs(entry_price - stop_loss_price) / entry_price
        risk_amount = margin * stop_pct * self.leverage

        return PositionSize(
            quantity=quantity,
            notional_value=notional,
            margin_required=margin,
            risk_amount=risk_amount,
        )
