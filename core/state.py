from dataclasses import dataclass, field
from typing import Any
from utils.helpers import utcnow


@dataclass
class BotState:
    """Runtime in-memory state. Persist etmez — restart'ta sıfırlanır."""

    portfolio_value: float = 0.0
    portfolio_value_at_day_start: float = 0.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_winning: int = 0
    daily_losing: int = 0
    max_drawdown_pct: float = 0.0

    # coin → pozisyon verisi (PaperPosition veya canlı pozisyon)
    open_positions: dict[str, Any] = field(default_factory=dict)

    # coin → son fiyat cache
    last_prices: dict[str, float] = field(default_factory=dict)

    # Haber cache
    news_cache: dict[str, list[str]] = field(default_factory=dict)  # coin → headlines
    gemini_cache: dict[str, tuple] = field(default_factory=dict)    # coin → (score, reason)
    fear_greed_index: int = 50

    # En iyi sinyal (send_opportunity_scan için)
    best_opportunity: Any = None   # (FinalSignal, IndicatorValues) tuple veya None

    # Çoklu borsa piyasa verisi cache: coin → FundingSnapshot
    funding_cache: dict[str, Any] = field(default_factory=dict)

    # SL sonrası cooldown: coin → timestamp (float, time.time())
    # 45 dakika boyunca aynı coin yeniden açılmaz
    sl_cooldown: dict[str, float] = field(default_factory=dict)

    # /tara sonuçları: [(FinalSignal, IndicatorValues)] — /ac için kullanılır
    scan_results: list = field(default_factory=list)

    # BTC 4h piyasa rejimi: "bull" | "bear" | "neutral"
    btc_regime: str = "neutral"

    # Ardışık kayıp sayacı — 3 üst üste SL → 2 saat duraklama
    consecutive_losses: int = 0
    loss_pause_until: float = 0.0  # time.time() timestamp

    started_at = utcnow()

    def add_position(self, coin: str, pos: Any) -> None:
        self.open_positions[coin] = pos

    def remove_position(self, coin: str) -> None:
        self.open_positions.pop(coin, None)

    def update_daily_pnl(self, delta: float) -> None:
        self.daily_pnl += delta
        if self.portfolio_value_at_day_start > 0:
            drawdown = abs(min(0.0, self.daily_pnl)) / self.portfolio_value_at_day_start
            if drawdown > self.max_drawdown_pct:
                self.max_drawdown_pct = drawdown

    def reset_daily(self) -> None:
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_winning = 0
        self.daily_losing = 0
        self.max_drawdown_pct = 0.0
        self.portfolio_value_at_day_start = self.portfolio_value
