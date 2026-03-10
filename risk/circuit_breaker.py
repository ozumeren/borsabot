from utils.logger import get_logger

logger = get_logger("risk.circuit_breaker")


class CircuitBreaker:
    """
    3 katmanlı koruma:
      1. Günlük PnL limiti (%3)
      2. Max açık pozisyon sayısı
      3. Tek pozisyon acil kapama eşiği (%5 portföy kaybı)
    """

    def __init__(
        self,
        daily_loss_limit_pct: float = 0.03,
        max_positions: int = 5,
        single_position_emergency_pct: float = 0.05,
    ):
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_positions = max_positions
        self.single_position_emergency_pct = single_position_emergency_pct

        self._halted = False
        self._halt_reason = ""
        self._daily_pnl = 0.0
        self._portfolio_at_day_start = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def is_trading_allowed(self, open_position_count: int) -> tuple[bool, str]:
        """(izin_var, neden) döndürür."""
        if self._halted:
            return False, f"DURDURULDU: {self._halt_reason}"

        if self._portfolio_at_day_start > 0:
            daily_pnl_pct = self._daily_pnl / self._portfolio_at_day_start
            if daily_pnl_pct <= -self.daily_loss_limit_pct:
                self._halt(f"Günlük zarar limiti aşıldı: {daily_pnl_pct*100:.2f}%")
                return False, self._halt_reason

        if open_position_count >= self.max_positions:
            return False, f"Max pozisyon sayısına ulaşıldı ({self.max_positions})"

        return True, ""

    def should_emergency_close(self, position_pnl_pct: float) -> bool:
        """Tek pozisyon için acil kapama kontrolü."""
        return position_pnl_pct <= -self.single_position_emergency_pct

    def update_pnl(self, pnl_delta: float) -> None:
        self._daily_pnl += pnl_delta

    def set_portfolio_start(self, value: float) -> None:
        self._portfolio_at_day_start = value

    def daily_reset(self) -> None:
        """Gece yarısı UTC'de çağrılır."""
        logger.info("Circuit breaker günlük sıfırlama", daily_pnl=self._daily_pnl)
        self._halted = False
        self._halt_reason = ""
        self._daily_pnl = 0.0

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def daily_pnl_pct(self) -> float:
        if self._portfolio_at_day_start <= 0:
            return 0.0
        return self._daily_pnl / self._portfolio_at_day_start

    # ── Private ───────────────────────────────────────────────────────────────

    def _halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        logger.warning("CIRCUIT BREAKER TETIKLENDI", reason=reason)
