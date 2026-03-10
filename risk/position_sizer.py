from dataclasses import dataclass


@dataclass
class PositionSize:
    quantity: float           # kontrat sayısı
    notional_value: float     # USDT cinsinden pozisyon değeri
    margin_required: float    # gereken teminat (USDT)
    risk_amount: float        # stop vurursa kaybedilecek USDT


class PositionSizer:
    """
    Fixed fractional pozisyon boyutu hesaplama.

    Formül:
        margin     = portfolio * max_pct * score_multiplier  (max %10)
        notional   = margin * leverage
        quantity   = notional / entry_price
        risk       = margin * stop_pct * leverage

    score_multiplier: combined_score 0.55 → ×0.5, 1.0 → ×1.0
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
    ) -> PositionSize:
        if entry_price <= 0 or portfolio_value <= 0:
            return PositionSize(0.0, 0.0, 0.0, 0.0)

        # Sinyal gücüne göre ölçekle (0.55 → 0.5x, 1.0 → 1.0x)
        score_multiplier = min(1.0, max(0.5, (signal_score - 0.55) / 0.45 * 0.5 + 0.5))

        margin = portfolio_value * self.max_position_pct * score_multiplier
        margin = min(margin, portfolio_value * self.max_position_pct)  # üst cap

        notional = margin * self.leverage
        quantity = notional / entry_price

        stop_pct = abs(entry_price - stop_loss_price) / entry_price
        risk_amount = margin * stop_pct * self.leverage

        return PositionSize(
            quantity=quantity,
            notional_value=notional,
            margin_required=margin,
            risk_amount=risk_amount,
        )
