"""
BotEngine — Ana orkestrasyon sınıfı.
Tüm modülleri bir araya getirir ve iş mantığını yönetir.
"""
import asyncio
from typing import Optional
from config.settings import BotSettings
from exchange.client import OKXClient
from data.market_data import MarketDataFetcher
from data.funding_data import MultiExchangeFundingFetcher
from indicators.technical import TechnicalAnalyzer
from sentiment.cryptopanic import CryptoPanicFetcher
from sentiment.rss_feeds import RSSFeedFetcher
from sentiment.fear_greed import FearGreedFetcher
from signals.technical_signal import TechnicalSignalGenerator, Direction
from signals.combiner import SignalCombiner
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.circuit_breaker import CircuitBreaker
from notifications.telegram_bot import TelegramNotifier
from database.trade_logger import TradeLogger
from database.db import init_db
from core.state import BotState
from utils.logger import get_logger
from utils.helpers import coin_from_symbol

logger = get_logger("core.bot")


class BotEngine:
    def __init__(self, settings: BotSettings):
        self.settings = settings
        self.state = BotState()

        # Veritabanı
        init_db(settings.database_url)
        self.trade_logger = TradeLogger()

        # Exchange
        self.client = OKXClient(settings)
        self.market_data = MarketDataFetcher(self.client)

        # Analiz
        self.tech_analyzer = TechnicalAnalyzer()
        self.tech_sig_gen  = TechnicalSignalGenerator(min_score=settings.min_technical_score)
        self.sig_combiner  = SignalCombiner(min_combined_score=settings.min_combined_score)

        # Sentiment
        self.cryptopanic = CryptoPanicFetcher(settings.cryptopanic_api_key)
        self.rss_fetcher = RSSFeedFetcher()
        self.fear_greed  = FearGreedFetcher()

        # Çoklu borsa piyasa verisi (API key gerekmez)
        self.funding_fetcher = MultiExchangeFundingFetcher(
            okx_exchange=self.client.exchange
        )

        # Risk
        self.position_sizer = PositionSizer(
            max_position_pct=settings.max_position_size_pct,
            leverage=settings.leverage,
        )
        self.stop_calc = StopLossCalculator(
            default_stop_pct=settings.stop_loss_pct_from_entry,
        )
        self.circuit_breaker = CircuitBreaker(
            daily_loss_limit_pct=settings.daily_loss_limit_pct,
            max_positions=settings.max_concurrent_positions,
        )

        # Bildirim
        self.notifier = TelegramNotifier(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
        )

        # Trading engine (paper veya canlı)
        if settings.paper_trading:
            from paper_trading.paper_engine import PaperEngine
            self.engine = PaperEngine(
                position_sizer=self.position_sizer,
                stop_calc=self.stop_calc,
                circuit_breaker=self.circuit_breaker,
                trade_logger=self.trade_logger,
                notifier=self.notifier,
            )
        else:
            from execution.trade_executor import TradeExecutor
            self.engine = TradeExecutor(
                client=self.client,
                position_sizer=self.position_sizer,
                stop_calc=self.stop_calc,
                circuit_breaker=self.circuit_breaker,
                trade_logger=self.trade_logger,
                state=self.state,
                notifier=self.notifier,
                settings=settings,
            )

    async def initialize(self) -> None:
        """Başlangıç kontrolü: API bağlantısı, bakiye senkronizasyonu."""
        logger.info("Bot başlatılıyor...")

        if not self.client.ping():
            raise ConnectionError("OKX API bağlantısı kurulamadı!")

        portfolio = self.client.get_portfolio_value()
        self.state.portfolio_value = portfolio
        self.state.portfolio_value_at_day_start = portfolio
        self.circuit_breaker.set_portfolio_start(portfolio)
        if self.settings.paper_trading:
            self.engine.portfolio_value = portfolio  # paper başlangıç bakiyesi

        logger.info(
            "Bot başlatıldı",
            mode="PAPER" if self.settings.paper_trading else "CANLI",
            portfolio=portfolio,
        )
        self.notifier.send_alert(
            f"Bot başlatıldı ({'PAPER' if self.settings.paper_trading else 'CANLI'})\n"
            f"Portföy: ${portfolio:,.2f}"
        )

        # Restart sonrası açık pozisyonları DB'den geri yükle
        if self.settings.paper_trading:
            restored = self.engine.restore_from_db()
            for coin, pos in self.engine.positions.items():
                self.state.add_position(coin, pos)
            if restored:
                logger.info("Paper pozisyonlar geri yüklendi", count=restored)

        # Telegram komut handler'ını kaydet ve dinleyiciyi başlat
        self.notifier.set_command_handler(self._handle_telegram_command)
        asyncio.create_task(self.notifier.start_command_listener())

    # ── Scheduler'dan çağrılan job'lar ───────────────────────────────────────

    async def run_signal_loop(self) -> None:
        """Ana sinyal döngüsü — 60 saniyede bir çalışır."""
        try:
            symbols = self.market_data.scan_top_coins(self.settings.scan_top_n_coins)
            if not symbols:
                return

            signals = []
            for symbol in symbols:
                coin = coin_from_symbol(symbol)
                signal = await self._evaluate_coin(coin, symbol)
                if signal and signal.is_actionable:
                    signals.append(signal)

            # En güçlü sinyalleri işle
            signals.sort(key=lambda s: s.combined_score, reverse=True)
            open_positions = self.engine.positions if self.settings.paper_trading else self.state.open_positions
            slots = self.settings.max_concurrent_positions - len(open_positions)

            for signal in signals[:slots]:
                if self.settings.paper_trading:
                    portfolio_val = self.engine.portfolio_value
                else:
                    portfolio_val = self.client.get_portfolio_value()
                self.state.portfolio_value = portfolio_val

                if self.settings.paper_trading:
                    pos = self.engine.open_position(signal, portfolio_val)
                    if pos:
                        self.state.add_position(signal.coin, pos)
                else:
                    self.engine.execute(signal, portfolio_val)

        except Exception as e:
            logger.error("Sinyal döngüsü hatası", error=str(e))

    async def monitor_positions(self) -> None:
        """Açık pozisyonları izle — 10 saniyede bir çalışır."""
        try:
            if self.settings.paper_trading:
                active_coins = list(self.engine.positions.keys())
            else:
                active_coins = list(self.state.open_positions.keys())

            if not active_coins:
                return

            price_map = {}
            for coin in active_coins:
                symbol = coin + "/USDT:USDT"
                price = self.market_data.get_current_price(symbol)
                if price:
                    price_map[coin] = price

            if self.settings.paper_trading:
                closed = self.engine.update_prices(price_map)
                for coin in closed:
                    self.state.remove_position(coin)
            else:
                await self._sync_live_positions()

        except Exception as e:
            logger.error("Pozisyon izleme hatası", error=str(e))

    async def fetch_news(self) -> None:
        """Haberleri çek ve cache'e kaydet — 5 dakikada bir."""
        try:
            all_articles = self.rss_fetcher.fetch_all(max_age_hours=6)

            coins = list(self.state.open_positions.keys()) + \
                    [coin_from_symbol(s) for s in
                     (self.market_data.scan_top_coins(10) or [])]
            for coin in coins:
                headlines    = self.rss_fetcher.filter_by_coin(all_articles, coin)
                cp_news      = self.cryptopanic.fetch_news(coin, limit=10)
                cp_headlines = self.cryptopanic.get_headlines(cp_news)
                self.state.news_cache[coin] = list(set(headlines + cp_headlines))[:20]

        except Exception as e:
            logger.error("Haber çekme hatası", error=str(e))

    async def fetch_fear_greed(self) -> None:
        """Fear & Greed indexini güncelle — saatte bir."""
        try:
            self.state.fear_greed_index = self.fear_greed.fetch()
        except Exception as e:
            logger.error("Fear & Greed hatası", error=str(e))

    async def fetch_funding_data(self) -> None:
        """
        OKX + Binance + Bybit'ten funding rate, OI ve L/S oranı çeker.
        5 dakikada bir çalışır.
        """
        try:
            symbols = self.market_data.scan_top_coins(self.settings.scan_top_n_coins)
            coins = [coin_from_symbol(s) for s in (symbols or [])]

            for coin in coins:
                try:
                    snap = self.funding_fetcher.fetch(coin)
                    self.state.funding_cache[coin] = snap
                except Exception as e:
                    logger.debug("Funding verisi alınamadı", coin=coin, error=str(e))

            logger.debug("Funding cache güncellendi", coins=len(self.state.funding_cache))
        except Exception as e:
            logger.error("Funding fetch hatası", error=str(e))

    async def send_pnl_update(self) -> None:
        """15 dakikada bir toplam PnL özetini Telegram'a gönderir."""
        try:
            from database.db import get_session
            from database.models import Trade
            from sqlalchemy import func

            with get_session() as session:
                # Bugünkü kapalı işlemler
                import datetime
                today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                today_pnl = session.query(func.sum(Trade.pnl_usdt)).filter(
                    Trade.status != "OPEN",
                    Trade.closed_at >= today,
                ).scalar() or 0.0
                today_trades = session.query(Trade).filter(
                    Trade.status != "OPEN",
                    Trade.closed_at >= today,
                ).count()
                today_wins = session.query(Trade).filter(
                    Trade.status != "OPEN",
                    Trade.closed_at >= today,
                    Trade.pnl_usdt > 0,
                ).count()

                # Açık pozisyonlar gerçekleşmemiş PnL
                open_positions = self.engine.positions if self.settings.paper_trading else {}
                unrealized = sum(p.unrealized_pnl for p in open_positions.values())

                # Toplam (tüm zamanlar)
                total_pnl = session.query(func.sum(Trade.pnl_usdt)).filter(
                    Trade.status != "OPEN"
                ).scalar() or 0.0

            open_count = len(open_positions)
            sign_today = "+" if today_pnl >= 0 else ""
            sign_unreal = "+" if unrealized >= 0 else ""
            sign_total = "+" if total_pnl >= 0 else ""
            wr = f"{today_wins}/{today_trades}" if today_trades else "—"

            text = (
                f"📊 <b>PnL Güncelleme</b>\n"
                f"Bugün: <b>{sign_today}${today_pnl:,.2f}</b>  ({wr} kazanç)\n"
                f"Gerçekleşmemiş: <b>{sign_unreal}${unrealized:,.2f}</b>  ({open_count} açık pozisyon)\n"
                f"Toplam: <b>{sign_total}${total_pnl:,.2f}</b>"
            )
            self.notifier.send(text)
        except Exception as e:
            logger.error("PnL güncelleme hatası", error=str(e))

    async def daily_reset(self) -> None:
        """Gece yarısı UTC sıfırlama."""
        stats = {
            "total_trades": self.state.daily_trades,
            "winning_trades": self.state.daily_winning,
            "losing_trades": self.state.daily_losing,
            "total_pnl_usdt": self.state.daily_pnl,
            "max_drawdown_pct": self.state.max_drawdown_pct,
            "circuit_breaker_fired": self.circuit_breaker.is_halted,
            "portfolio_value_end": self.state.portfolio_value,
        }
        self.trade_logger.log_daily_stats(stats)
        self.notifier.send_daily_summary(stats)

        self.circuit_breaker.daily_reset()
        self.state.reset_daily()
        logger.info("Günlük sıfırlama tamamlandı")

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.warning("Bot kapatılıyor...")
        self.notifier.send_alert("Bot kapatılıyor. Açık pozisyonlar kontrol edin.")

    # ── İç metodlar ───────────────────────────────────────────────────────────

    async def _evaluate_coin(self, coin: str, symbol: str):
        """Tek bir coin için tam sinyal değerlendirmesi."""
        df = self.market_data.fetch_ohlcv(symbol, self.settings.timeframe)
        if df is None:
            return None

        try:
            iv = self.tech_analyzer.compute(df)
        except ValueError:
            return None

        tech_signal = self.tech_sig_gen.generate(iv)
        if tech_signal.direction == Direction.NONE:
            return None

        # Gerçek piyasa anlık fiyatı (sandbox değil) — monitor ile tutarlı
        real_price = self.market_data.get_current_price(symbol)
        entry_price = real_price if real_price else iv.close

        # Sentiment
        cp_news  = self.cryptopanic.fetch_news(coin, limit=5)
        cp_score = self.cryptopanic.calculate_sentiment_score(cp_news)
        fg_index = self.state.fear_greed_index

        # Çoklu borsa piyasa verisi (cache'den)
        funding_snap = self.state.funding_cache.get(coin)
        market_signal = funding_snap.combined_market_signal if funding_snap else 0.0

        final_signal = self.sig_combiner.combine(
            technical=tech_signal,
            cryptopanic_score=cp_score,
            fear_greed_index=fg_index,
            market_signal=market_signal,
            coin=coin,
            entry_price=entry_price,
        )

        if final_signal.is_actionable:
            logger.info(
                "Sinyal üretildi",
                coin=coin,
                direction=final_signal.direction.value,
                score=f"{final_signal.combined_score:.2f}",
                funding=f"{funding_snap.rate_pct_str() if funding_snap else 'N/A'}",
                reasons=final_signal.reasons[:3],
            )

        return final_signal

    async def _handle_telegram_command(self, command: str, **kwargs) -> None:
        """Telegram'dan gelen komutları işler."""
        if command == "kapat":
            coin = kwargs.get("coin", "").upper()
            pos = self.engine.positions.get(coin) if self.settings.paper_trading else None
            if pos:
                price = self.market_data.get_current_price(f"{coin}/USDT:USDT") or pos.entry_price
                self.engine._close_position(coin, pos, price, "CLOSED_MANUAL")
                del self.engine.positions[coin]
                self.state.remove_position(coin)
                self.notifier.send(f"✅ <b>{coin}</b> pozisyonu manuel olarak kapatıldı.")
            else:
                self.notifier.send(f"⚠️ <b>{coin}</b> için açık pozisyon bulunamadı.")

        elif command == "hepsiniKapat":
            if self.settings.paper_trading:
                coins = list(self.engine.positions.keys())
                if not coins:
                    self.notifier.send("ℹ️ Kapatılacak açık pozisyon yok.")
                    return
                for coin in coins:
                    pos = self.engine.positions[coin]
                    price = self.market_data.get_current_price(f"{coin}/USDT:USDT") or pos.entry_price
                    self.engine._close_position(coin, pos, price, "CLOSED_MANUAL")
                    self.state.remove_position(coin)
                self.engine.positions.clear()
                self.notifier.send(f"✅ {len(coins)} pozisyon kapatıldı: {', '.join(coins)}")
            else:
                self.notifier.send("⚠️ Canlı modda manuel kapama henüz desteklenmiyor.")

        elif command == "durdur":
            self.circuit_breaker.is_halted = True
            self.notifier.send("🔴 <b>Bot durduruldu.</b> Yeni işlem açılmayacak.\n/baslat ile devam ettir.")

        elif command == "baslat":
            self.circuit_breaker.is_halted = False
            self.notifier.send("🟢 <b>Bot devam ediyor.</b> Yeni işlemler açılabilir.")

        elif command == "bakiye":
            try:
                if self.settings.paper_trading:
                    balance = self.engine.portfolio_value
                else:
                    balance = self.client.get_portfolio_value()
                open_count = len(self.engine.positions) if self.settings.paper_trading else len(self.state.open_positions)
                mode = "📄 PAPER" if self.settings.paper_trading else "💰 CANLI"
                self.notifier.send(
                    f"💳 <b>Bakiye</b> ({mode})\n"
                    f"USDT: <b>${balance:,.2f}</b>\n"
                    f"Açık Pozisyon: {open_count}"
                )
            except Exception as e:
                self.notifier.send(f"❌ Bakiye alınamadı: {e}")

    async def _sync_live_positions(self) -> None:
        """Canlı modda OKX pozisyon durumunu senkronize et."""
        try:
            live_positions = self.client.fetch_positions()
            live_coins = {
                p["symbol"].split("/")[0]
                for p in live_positions
                if p.get("contracts", 0) > 0
            }
            for coin in list(self.state.open_positions.keys()):
                if coin not in live_coins:
                    self.state.remove_position(coin)
                    logger.info("Pozisyon kapandı (OKX senkronizasyon)", coin=coin)
        except Exception as e:
            logger.warning("OKX pozisyon senkronizasyon hatası", error=str(e))
