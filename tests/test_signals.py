"""
Temel sinyal ve risk modülü testleri.
Çalıştır: pytest tests/ -v
"""
import pytest
from signals.technical_signal import TechnicalSignalGenerator, Direction
from signals.combiner import SignalCombiner
from risk.stop_loss import StopLossCalculator
from risk.position_sizer import PositionSizer
from risk.circuit_breaker import CircuitBreaker
from indicators.technical import IndicatorValues
from data.funding_data import FundingSnapshot, ExchangeFundingRate


def make_iv(**kwargs) -> IndicatorValues:
    """Test için varsayılan IndicatorValues."""
    defaults = dict(
        rsi=50.0, macd_line=0.0, macd_signal=0.0, macd_hist=0.0, macd_hist_prev=0.0,
        ema_short=100.0, ema_long=100.0, sma_long=100.0,
        bb_upper=105.0, bb_mid=100.0, bb_lower=95.0, bb_pct=0.5, bb_width_pct=0.10,
        atr=1.5, adx=25.0, close=100.0, volume=1000.0, volume_avg20=700.0,
    )
    defaults.update(kwargs)
    return IndicatorValues(**defaults)


class TestTechnicalSignal:
    def test_strong_long_signal(self):
        # Trend-uyumlu: RSI güçlü bullish bölge, BB üst bölge, EMA yükselen, MACD crossover
        iv = make_iv(rsi=70.0, macd_hist=0.5, macd_hist_prev=-0.1, macd_line=0.5, macd_signal=0.1,
                     ema_short=101.0, ema_long=99.0, bb_pct=0.85, close=101.0, sma_long=99.0)
        gen = TechnicalSignalGenerator(min_score=0.6)
        sig = gen.generate(iv)
        assert sig.direction == Direction.LONG
        assert sig.score >= 0.6

    def test_strong_short_signal(self):
        # Trend-uyumlu: RSI güçlü bearish bölge, BB alt bölge, EMA düşen, MACD crossover
        iv = make_iv(rsi=30.0, macd_hist=-0.5, macd_hist_prev=0.1, macd_line=-0.5, macd_signal=-0.1,
                     ema_short=99.0, ema_long=101.0, bb_pct=0.15, close=99.0, sma_long=101.0)
        gen = TechnicalSignalGenerator(min_score=0.6)
        sig = gen.generate(iv)
        assert sig.direction == Direction.SHORT
        assert sig.score >= 0.6

    def test_neutral_signal(self):
        iv = make_iv(rsi=50.0)
        gen = TechnicalSignalGenerator(min_score=0.6)
        sig = gen.generate(iv)
        assert sig.direction == Direction.NONE


class TestStopLoss:
    def test_long_stop_loss(self):
        calc = StopLossCalculator(default_stop_pct=0.015)
        sl = calc.calculate_stop_loss(Direction.LONG, 100.0)
        assert sl == pytest.approx(98.5, rel=1e-3)

    def test_short_stop_loss(self):
        calc = StopLossCalculator(default_stop_pct=0.015)
        sl = calc.calculate_stop_loss(Direction.SHORT, 100.0)
        assert sl == pytest.approx(101.5, rel=1e-3)

    def test_take_profit_2r(self):
        calc = StopLossCalculator(default_stop_pct=0.015)
        sl = 98.5
        tp = calc.calculate_take_profit(Direction.LONG, 100.0, sl, rr_ratio=2.0)
        assert tp == pytest.approx(103.0, rel=1e-3)


class TestPositionSizer:
    def test_basic_sizing(self):
        sizer = PositionSizer(max_position_pct=0.10, leverage=5)
        size = sizer.calculate(
            portfolio_value=10_000,
            entry_price=100.0,
            stop_loss_price=98.5,
            signal_score=0.75,
        )
        assert size.margin_required <= 10_000 * 0.10
        assert size.quantity > 0
        assert size.notional_value == pytest.approx(size.margin_required * 5, rel=1e-3)

    def test_zero_portfolio(self):
        sizer = PositionSizer()
        size = sizer.calculate(portfolio_value=0, entry_price=100, stop_loss_price=98)
        assert size.quantity == 0.0


class TestFundingData:
    def test_high_positive_funding_is_short_signal(self):
        snap = FundingSnapshot(
            coin="BTC",
            rates=[ExchangeFundingRate("Binance", 0.0015)],
            avg_rate=0.0015,
        )
        assert snap.funding_signal == -1.0

    def test_high_negative_funding_is_long_signal(self):
        snap = FundingSnapshot(
            coin="BTC",
            rates=[ExchangeFundingRate("Binance", -0.0015)],
            avg_rate=-0.0015,
        )
        assert snap.funding_signal == 1.0

    def test_neutral_funding(self):
        snap = FundingSnapshot(coin="BTC", avg_rate=0.0001)
        assert snap.funding_signal == 0.0

    def test_ls_ratio_short_signal(self):
        snap = FundingSnapshot(coin="BTC", long_short_ratio=2.0)
        assert snap.ls_signal == -1.0

    def test_ls_ratio_long_signal(self):
        snap = FundingSnapshot(coin="BTC", long_short_ratio=0.5)
        assert snap.ls_signal == 1.0


class TestCombinerWithMarket:
    def _make_tech(self, direction=Direction.LONG, score=0.70):
        from signals.technical_signal import TechnicalSignal
        return TechnicalSignal(direction, score, ["test"])

    def test_market_signal_boosts_score(self):
        combiner = SignalCombiner(min_combined_score=0.55)
        tech = self._make_tech(Direction.LONG, 0.65)
        sig_no_market = combiner.combine(tech, 0.0, 50, market_signal=0.0,
                                         coin="BTC", entry_price=100.0)
        sig_with_market = combiner.combine(tech, 0.0, 50, market_signal=1.0,
                                           coin="BTC", entry_price=100.0)
        assert sig_with_market.combined_score > sig_no_market.combined_score

    def test_contradicting_market_lowers_score(self):
        combiner = SignalCombiner(min_combined_score=0.55)
        tech = self._make_tech(Direction.LONG, 0.65)
        sig = combiner.combine(tech, 0.0, 50, market_signal=-1.0,
                               coin="BTC", entry_price=100.0)
        sig_neutral = combiner.combine(tech, 0.0, 50, market_signal=0.0,
                                       coin="BTC", entry_price=100.0)
        assert sig.combined_score < sig_neutral.combined_score


class TestCircuitBreaker:
    def test_daily_loss_triggers_halt(self):
        cb = CircuitBreaker(daily_loss_limit_pct=0.03)
        cb.set_portfolio_start(10_000)
        cb.update_pnl(-350)  # -3.5%
        allowed, reason = cb.is_trading_allowed(0)
        assert not allowed
        assert "zarar" in reason.lower()

    def test_max_positions(self):
        cb = CircuitBreaker(max_positions=3)
        allowed, reason = cb.is_trading_allowed(3)
        assert not allowed

    def test_daily_reset(self):
        cb = CircuitBreaker(daily_loss_limit_pct=0.03)
        cb.set_portfolio_start(10_000)
        cb.update_pnl(-400)
        cb.daily_reset()
        allowed, _ = cb.is_trading_allowed(0)
        assert allowed
