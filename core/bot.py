"""
BotEngine — Ana orkestrasyon sınıfı.
Tüm modülleri bir araya getirir ve iş mantığını yönetir.
"""
import asyncio
import datetime
import time
import ta
from typing import Optional
from config.settings import BotSettings
from exchange.client import OKXClient
from data.market_data import MarketDataFetcher
from data.funding_data import MultiExchangeFundingFetcher
from indicators.technical import TechnicalAnalyzer
from sentiment.cryptopanic import CryptoPanicFetcher
from sentiment.rss_feeds import RSSFeedFetcher
from sentiment.fear_greed import FearGreedFetcher
from sentiment.gemini_analyzer import GeminiAnalyzer
from signals.technical_signal import TechnicalSignalGenerator, Direction
from signals.combiner import SignalCombiner, FinalSignal
from risk.position_sizer import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.circuit_breaker import CircuitBreaker
from risk.correlation import CorrelationGuard
from risk.leverage import calculate_leverage
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
        self.sig_combiner  = SignalCombiner(
            min_combined_score=settings.min_combined_score,
            trade_logger=self.trade_logger,
        )

        # Sentiment
        self.cryptopanic     = CryptoPanicFetcher(settings.cryptopanic_api_key)
        self.rss_fetcher     = RSSFeedFetcher()
        self.fear_greed      = FearGreedFetcher()
        self.gemini_analyzer = GeminiAnalyzer(settings.gemini_api_key)

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
            single_position_emergency_pct=0.18,  # SL ~%9 (1.5% fiyat × 6x) + buffer → %18'den sonra emergency
        )

        # Korelasyon koruyucu
        self.correlation_guard = CorrelationGuard()

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
        # Paper modda PAPER_INITIAL_BALANCE ayarlıysa onu kullan
        if self.settings.paper_trading and self.settings.paper_initial_balance > 0:
            portfolio = self.settings.paper_initial_balance
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

        # Bot başlar başlamaz BTC rejimini belirle
        await self.update_btc_regime()

        # Restart sonrası açık pozisyonları DB'den geri yükle
        if self.settings.paper_trading:
            restored = self.engine.restore_from_db()
            for coin, pos in self.engine.positions.items():
                self.state.add_position(coin, pos)
            if restored:
                logger.info("Paper pozisyonlar geri yüklendi", count=restored)
        else:
            # Canlı modda OKX pozisyonlarını DB ile karşılaştır
            await self._reconcile_live_positions()

        # Telegram komut handler'ını kaydet ve dinleyiciyi başlat
        self.notifier.set_command_handler(self._handle_telegram_command)
        asyncio.create_task(self.notifier.start_command_listener())

    # ── Scheduler'dan çağrılan job'lar ───────────────────────────────────────

    async def run_signal_loop(self) -> None:
        """Ana sinyal döngüsü — 60 saniyede bir çalışır."""
        try:
            # Ardışık kayıp sonrası duraklama kontrolü
            if self.state.loss_pause_until > time.time():
                remaining = int((self.state.loss_pause_until - time.time()) / 60)
                logger.info("Kayıp duraklaması aktif, sinyal döngüsü atlanıyor", kalan_dk=remaining)
                return

            symbols = self.market_data.scan_top_coins(self.settings.scan_top_n_coins)
            if not symbols:
                return

            SL_COOLDOWN_SECS = 45 * 60  # 45 dakika
            now = time.time()
            # Süresi dolan cooldown'ları temizle
            self.state.sl_cooldown = {
                c: ts for c, ts in self.state.sl_cooldown.items()
                if now - ts < SL_COOLDOWN_SECS
            }

            signals = []          # (FinalSignal, IndicatorValues) pairs
            for symbol in symbols:
                coin = coin_from_symbol(symbol)
                # SL cooldown aktifse bu coini atla
                if coin in self.state.sl_cooldown:
                    remaining = int((SL_COOLDOWN_SECS - (now - self.state.sl_cooldown[coin])) / 60)
                    logger.debug("SL cooldown aktif, atlanıyor", coin=coin, kalan_dk=remaining)
                    continue
                result = await self._evaluate_coin(coin, symbol)
                if result and result[0].is_actionable:
                    signals.append(result)

            # En iyi fırsatı state'e kaydet (send_opportunity_scan için)
            if signals:
                best = max(signals, key=lambda r: r[0].combined_score)
                self.state.best_opportunity = best

            # En güçlü sinyalleri işle
            signals.sort(key=lambda r: r[0].combined_score, reverse=True)
            open_positions = self.engine.positions if self.settings.paper_trading else self.state.open_positions
            slots = self.settings.max_concurrent_positions - len(open_positions)

            for signal, _iv in signals[:slots]:
                # Korelasyon grubu limiti kontrolü
                open_coins = (
                    set(self.engine.positions.keys())
                    if self.settings.paper_trading
                    else set(self.state.open_positions.keys())
                )
                if not self.correlation_guard.can_open(signal.coin, open_coins):
                    logger.info(
                        "Korelasyon limiti — sinyal atlandı",
                        coin=signal.coin,
                    )
                    continue

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

            # last_prices'ı güncelle (pozisyon kartlarında güncel fiyat göstermek için)
            self.state.last_prices.update(price_map)

            if self.settings.paper_trading:
                closed = self.engine.update_prices(price_map)  # {coin: (status, pnl)}
                for coin, (status, pnl) in closed.items():
                    self.state.remove_position(coin)
                    self.state.update_daily_pnl(pnl)
                    self.state.portfolio_value = self.engine.portfolio_value
                    # TP1 kısmi kapanma için trade sayısı artmaz, sadece pnl güncellenir
                    if status != "CLOSED_TP1":
                        self.state.daily_trades += 1
                        if pnl > 0:
                            self.state.daily_winning += 1
                        else:
                            self.state.daily_losing += 1
                    if status in ("CLOSED_SL", "CLOSED_CIRCUIT"):
                        self.state.sl_cooldown[coin] = time.time()
                        self.state.consecutive_losses += 1
                        logger.info("SL cooldown başladı (45dk)", coin=coin, status=status,
                                    consecutive=self.state.consecutive_losses)
                        # 3 ardışık SL → 2 saat dur
                        if self.state.consecutive_losses >= 3:
                            pause_hours = 2
                            self.state.loss_pause_until = time.time() + pause_hours * 3600
                            self.state.consecutive_losses = 0
                            logger.warning("3 ardışık SL — işlemler 2 saat durduruldu")
                            if self.notifier:
                                self.notifier.send(
                                    "⛔ <b>3 ardışık stop loss!</b>\n"
                                    "Bot 2 saat boyunca yeni işlem açmayacak.\n"
                                    "Piyasa koşulları değerlendirilmeli."
                                )
                    elif status in ("CLOSED_TP", "CLOSED_TP1", "CLOSED_TP2"):
                        self.state.consecutive_losses = 0  # kazanışta sıfırla
            else:
                await self._sync_live_positions()
                # Monitor job içinde likidayon + fill kontrolü de çalışır
                self.engine.monitor_open_positions()

        except Exception as e:
            logger.error("Pozisyon izleme hatası", error=str(e))

    async def fetch_news(self) -> None:
        """Haberleri çek ve cache'e kaydet — 5 dakikada bir."""
        try:
            all_articles = self.rss_fetcher.fetch_all(max_age_hours=6)

            coins = list(set(
                list(self.state.open_positions.keys()) +
                [coin_from_symbol(s) for s in (self.market_data.scan_top_coins(20) or [])]
            ))

            # CryptoPanic: tek batch isteğiyle tüm coinlerin haberlerini çek
            await asyncio.to_thread(self.cryptopanic.fetch_news_batch, coins, limit=50)

            for coin in coins:
                headlines    = self.rss_fetcher.filter_by_coin(all_articles, coin)
                cp_news      = self.cryptopanic.fetch_news(coin)   # cache'ten gelir
                cp_headlines = self.cryptopanic.get_headlines(cp_news)
                all_headlines = list(set(headlines + cp_headlines))[:20]
                self.state.news_cache[coin] = all_headlines

                # Gemini ile AI sentiment analizi
                if self.gemini_analyzer.enabled and all_headlines:
                    score, reason = await asyncio.to_thread(
                        self.gemini_analyzer.analyze, coin, all_headlines
                    )
                    self.state.gemini_cache[coin] = (score, reason)

        except Exception as e:
            logger.error("Haber çekme hatası", error=str(e))

    async def fetch_fear_greed(self) -> None:
        """Fear & Greed indexini güncelle — saatte bir."""
        try:
            self.state.fear_greed_index = self.fear_greed.fetch()
        except Exception as e:
            logger.error("Fear & Greed hatası", error=str(e))

    async def update_btc_regime(self) -> None:
        """BTC 4h trendine göre piyasa rejimini günceller — 30 dakikada bir."""
        try:
            df = self.market_data.fetch_ohlcv("BTC/USDT:USDT", "4h")
            if df is None or len(df) < 50:
                return
            ema9  = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator().iloc[-1]
            ema21 = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
            ema50 = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator().iloc[-1]
            price = df["close"].iloc[-1]
            # Güçlü bull: fiyat > EMA9 > EMA21 > EMA50
            # Güçlü bear: fiyat < EMA9 < EMA21 < EMA50
            if price > ema9 > ema21 > ema50:
                regime = "bull"
            elif price < ema9 < ema21 < ema50:
                regime = "bear"
            else:
                regime = "neutral"
            old = self.state.btc_regime
            self.state.btc_regime = regime
            changed = old != regime
            if changed:
                logger.info("BTC rejimi değişti", old=old, new=regime,
                            ema9=f"{ema9:.0f}", ema21=f"{ema21:.0f}", ema50=f"{ema50:.0f}")
            if self.notifier:
                emoji = "🟢" if regime == "bull" else ("🔴" if regime == "bear" else "🟡")
                change_tag = " <i>(değişti)</i>" if changed else ""
                self.notifier.send(
                    f"{emoji} <b>BTC Piyasa Rejimi: {regime.upper()}</b>{change_tag}\n"
                    f"EMA9={ema9:.0f} | EMA21={ema21:.0f} | EMA50={ema50:.0f}"
                )
        except Exception as e:
            logger.error("BTC rejim güncelleme hatası", error=str(e))

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

    async def send_live_status_update(self) -> None:
        """Her dakika son durum mesajını düzenleyerek günceller."""
        try:
            await asyncio.to_thread(self.notifier.update_portfolio_status)
        except Exception as e:
            logger.debug("Canlı durum güncellemesi başarısız", error=str(e))

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

    async def send_positions_report(self) -> None:
        """
        30 dakikada bir açık pozisyonların detaylı durumunu Telegram'a gönderir.
        Her pozisyon için: yön, kaldıraç, giriş/anlık fiyat, gerçekleşmemiş PnL,
        SL/TP mesafesi, trailing stop durumu.
        """
        try:
            import datetime as dt

            if self.settings.paper_trading:
                positions = self.engine.positions
            else:
                positions = {}  # canlı: state'deki kayıtları kullan

            open_count = len(positions) if self.settings.paper_trading else len(self.state.open_positions)

            if open_count == 0:
                # Açık pozisyon yoksa sadece özet gönder
                self.notifier.send(
                    f"📍 <b>Pozisyon Durumu</b>\n"
                    f"Açık pozisyon yok.\n"
                    f"Portföy: <b>${self.state.portfolio_value:,.2f}</b>"
                )
                return

            now_str = dt.datetime.utcnow().strftime("%H:%M UTC")
            lines = [f"📍 <b>Pozisyon Durumu</b>  <i>{now_str}</i>\n"]

            total_unrealized = 0.0

            if self.settings.paper_trading:
                for coin, pos in positions.items():
                    # Anlık fiyatı çek
                    symbol = f"{coin}/USDT:USDT"
                    current = self.market_data.get_current_price(symbol) or pos.current_price
                    pos.current_price = current

                    pnl = pos.unrealized_pnl
                    total_unrealized += pnl
                    pnl_pct = pos.unrealized_pnl_pct

                    dir_emoji = "🟢" if pos.direction == "long" else "🔴"
                    pnl_emoji = "📈" if pnl >= 0 else "📉"
                    sign = "+" if pnl >= 0 else ""

                    # SL / TP mesafesi
                    if pos.direction == "long":
                        sl_dist = (current - pos.stop_loss_price) / current * 100
                        tp_dist = (pos.take_profit_price - current) / current * 100
                    else:
                        sl_dist = (pos.stop_loss_price - current) / current * 100
                        tp_dist = (current - pos.take_profit_price) / current * 100

                    trail_tag = " 🔄trail" if pos.trailing_active else ""

                    lines.append(
                        f"{dir_emoji} <b>{coin}</b> {pos.direction.upper()} {pos.leverage}x{trail_tag}\n"
                        f"  Giriş: ${pos.entry_price:,.4f}  →  Anlık: ${current:,.4f}\n"
                        f"  {pnl_emoji} PnL: <b>{sign}${pnl:.2f}</b> ({sign}{pnl_pct*100:.1f}%)\n"
                        f"  SL -{sl_dist:.1f}%  |  TP +{tp_dist:.1f}%"
                    )
            else:
                # Canlı mod: sadece kayıtlardaki bilgiler
                for coin, record in self.state.open_positions.items():
                    symbol = f"{coin}/USDT:USDT"
                    current = self.market_data.get_current_price(symbol) or record.entry_price
                    from config.constants import OKX_TAKER_FEE_PCT
                    fee = record.quantity * (record.entry_price + current) * OKX_TAKER_FEE_PCT
                    if record.direction == "long":
                        pnl = (current - record.entry_price) * record.quantity - fee
                        sl_dist = (current - record.stop_loss_price) / current * 100
                        tp_dist = ((record.take_profit_price or current) - current) / current * 100
                    else:
                        pnl = (record.entry_price - current) * record.quantity - fee
                        sl_dist = (record.stop_loss_price - current) / current * 100
                        tp_dist = (current - (record.take_profit_price or current)) / current * 100

                    total_unrealized += pnl
                    pnl_pct = pnl / record.margin_used if record.margin_used > 0 else 0.0
                    dir_emoji = "🟢" if record.direction == "long" else "🔴"
                    pnl_emoji = "📈" if pnl >= 0 else "📉"
                    sign = "+" if pnl >= 0 else ""

                    lines.append(
                        f"{dir_emoji} <b>{coin}</b> {record.direction.upper()} {record.leverage}x\n"
                        f"  Giriş: ${record.entry_price:,.4f}  →  Anlık: ${current:,.4f}\n"
                        f"  {pnl_emoji} PnL: <b>{sign}${pnl:.2f}</b> ({sign}{pnl_pct*100:.1f}%)\n"
                        f"  SL -{sl_dist:.1f}%  |  TP +{tp_dist:.1f}%"
                    )

            sign_u = "+" if total_unrealized >= 0 else ""
            lines.append(
                f"\n💰 Toplam Gerçekleşmemiş: <b>{sign_u}${total_unrealized:.2f}</b>\n"
                f"Portföy: <b>${self.state.portfolio_value:,.2f}</b>"
            )

            self.notifier.send("\n".join(lines))

        except Exception as e:
            logger.error("Pozisyon raporu hatası", error=str(e))

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
        """Tek bir coin için tam sinyal değerlendirmesi (15m + MTF 1h/4h/1d filtresi)."""
        df = self.market_data.fetch_ohlcv(symbol, self.settings.timeframe)
        if df is None:
            return None

        # Son mum henüz kapanmamış — kapalı mum üzerinden sinyal üret
        df = df.iloc[:-1]

        try:
            iv = self.tech_analyzer.compute(df)
        except ValueError:
            return None

        tech_signal = self.tech_sig_gen.generate(iv)
        if tech_signal.direction == Direction.NONE:
            return None

        # ── MTF Filtresi: 1h + 4h soft ceza ──────────────────────────────────
        # Hard-block yerine skor cezası: zıt yön = combined_score'dan düşülür
        # 1h zıt: -0.08 | 4h zıt: -0.12 | 1D EMA50 zıt: -0.15
        mtf_penalty = 0.0
        for tf, w_short, w_long, penalty in [("1h", 9, 21, 0.08), ("4h", 9, 21, 0.12)]:
            try:
                df_tf = self.market_data.fetch_ohlcv(symbol, tf)
                if df_tf is not None and len(df_tf) >= w_long:
                    df_tf = df_tf.iloc[:-1]
                    ema_s = ta.trend.EMAIndicator(df_tf["close"], window=w_short).ema_indicator().iloc[-1]
                    ema_l = ta.trend.EMAIndicator(df_tf["close"], window=w_long).ema_indicator().iloc[-1]
                    if tech_signal.direction == Direction.LONG and ema_s < ema_l:
                        mtf_penalty += penalty
                        logger.debug(f"MTF {tf}: LONG için -{penalty} ceza", coin=coin)
                    elif tech_signal.direction == Direction.SHORT and ema_s > ema_l:
                        mtf_penalty += penalty
                        logger.debug(f"MTF {tf}: SHORT için -{penalty} ceza", coin=coin)
            except Exception as e:
                logger.debug(f"MTF {tf} fetch hatası", coin=coin, error=str(e))

        # ── 1D Trend Filtresi: EMA50 makro yön (soft ceza) ───────────────────
        try:
            df_1d = self.market_data.fetch_ohlcv(symbol, "1d", limit=60)
            if df_1d is not None and len(df_1d) >= 50:
                df_1d = df_1d.iloc[:-1]
                ema50_1d = ta.trend.EMAIndicator(df_1d["close"], window=50).ema_indicator().iloc[-1]
                price_1d = df_1d["close"].iloc[-1]
                if tech_signal.direction == Direction.LONG and price_1d < ema50_1d:
                    mtf_penalty += 0.15
                    logger.debug("1D EMA50 altında: LONG için -0.15 ceza", coin=coin)
                elif tech_signal.direction == Direction.SHORT and price_1d > ema50_1d:
                    mtf_penalty += 0.15
                    logger.debug("1D EMA50 üstünde: SHORT için -0.15 ceza", coin=coin)
        except Exception as e:
            logger.debug("1D fetch hatası", coin=coin, error=str(e))

        # ── BTC Piyasa Rejimi Filtresi ────────────────────────────────────────
        # Gerçek piyasa anlık fiyatı
        real_price = self.market_data.get_current_price(symbol)
        entry_price = real_price if real_price else iv.close

        # Sentiment
        cp_news  = self.cryptopanic.fetch_news(coin, limit=5)
        cp_score = self.cryptopanic.calculate_sentiment_score(cp_news)

        # Gemini AI analizi (fetch_news cache'inden — ek API çağrısı yok)
        gemini_reason = ""
        gemini_cached = self.state.gemini_cache.get(coin)
        if gemini_cached:
            gemini_score, gemini_reason = gemini_cached
            # Gemini %60 + CryptoPanic %40 ağırlıklı ortalama
            cp_score = 0.6 * gemini_score + 0.4 * cp_score

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
            atr=iv.atr,
            leverage=self.settings.leverage,  # varsayılan; aşağıda gerçek değerle güncellenir
        )
        final_signal.adx = iv.adx
        final_signal.bb_width_pct = iv.bb_width_pct

        # ── MTF cezasını uygula ───────────────────────────────────────────────
        if mtf_penalty > 0 and final_signal.is_actionable:
            final_signal.combined_score = max(0.0, round(final_signal.combined_score - mtf_penalty, 4))
            if final_signal.combined_score < self.sig_combiner.min_combined_score:
                logger.debug(
                    "MTF cezası sonrası skor yetersiz — sinyal iptal",
                    coin=coin, penalty=mtf_penalty, score=final_signal.combined_score,
                )
                final_signal.direction = Direction.NONE

        # Gerçek combined_score ile kaldıracı hesapla ve güncelle
        if final_signal.is_actionable:
            final_signal.leverage = calculate_leverage(
                combined_score=final_signal.combined_score,
                adx=iv.adx,
                atr=iv.atr,
                price=entry_price,
                base_leverage=self.settings.leverage,
                max_leverage=self.settings.max_leverage,
            )

        if final_signal.is_actionable and gemini_reason:
            final_signal.reasons.append(f"Gemini AI: {gemini_reason}")

        if final_signal.is_actionable:
            logger.info(
                "Sinyal üretildi",
                coin=coin,
                direction=final_signal.direction.value,
                score=f"{final_signal.combined_score:.2f}",
                leverage=f"{final_signal.leverage}x",
                adx=f"{iv.adx:.1f}",
                funding=f"{funding_snap.rate_pct_str() if funding_snap else 'N/A'}",
                reasons=final_signal.reasons[:3],
            )

        return final_signal, iv

    # ── Fırsat Tarayıcı ───────────────────────────────────────────────────────

    async def scan_coins_for_report(self) -> list:
        """
        Tüm coinleri tarar; is_actionable olsun ya da olmasın tüm sinyalleri toplar.
        MTF filtresi atlanır (display-only tarama).
        Eşik geçici olarak 0.42'ye düşürülür — gerçek trading için 0.55 geçerli.
        Dönen: [(FinalSignal, IndicatorValues, mtf_ok: bool)] sorted by score
        """
        symbols = self.market_data.scan_top_coins(self.settings.scan_top_n_coins)
        results = []

        # Geçici olarak eşiği düşür (tarama modunda daha fazla sonuç görünsün)
        original_min = self.sig_combiner.min_combined_score
        self.sig_combiner.min_combined_score = 0.42

        try:
            for symbol in symbols:
                coin = coin_from_symbol(symbol)
                try:
                    df = self.market_data.fetch_ohlcv(symbol, self.settings.timeframe)
                    if df is None:
                        continue
                    iv = self.tech_analyzer.compute(df)
                    tech_signal = self.tech_sig_gen.generate(iv)
                    if tech_signal.direction == Direction.NONE:
                        continue

                    # MTF kontrolü (sadece bilgi için, filtreleme değil)
                    mtf_ok = True
                    try:
                        df_1h = self.market_data.fetch_ohlcv(symbol, "1h")
                        if df_1h is not None and len(df_1h) >= 21:
                            ema9  = ta.trend.EMAIndicator(df_1h["close"], window=9).ema_indicator().iloc[-1]
                            ema21 = ta.trend.EMAIndicator(df_1h["close"], window=21).ema_indicator().iloc[-1]
                            if tech_signal.direction == Direction.LONG and ema9 < ema21:
                                mtf_ok = False
                            elif tech_signal.direction == Direction.SHORT and ema9 > ema21:
                                mtf_ok = False
                    except Exception:
                        pass

                    real_price = self.market_data.get_current_price(symbol)
                    entry_price = real_price if real_price else iv.close
                    cp_news    = self.cryptopanic.fetch_news(coin, limit=5)
                    cp_score   = self.cryptopanic.calculate_sentiment_score(cp_news)
                    gemini_cached = self.state.gemini_cache.get(coin)
                    if gemini_cached:
                        cp_score = 0.6 * gemini_cached[0] + 0.4 * cp_score
                    fg_index     = self.state.fear_greed_index
                    funding_snap = self.state.funding_cache.get(coin)
                    market_signal = funding_snap.combined_market_signal if funding_snap else 0.0
                    dyn_leverage  = calculate_leverage(
                        combined_score=tech_signal.score, adx=iv.adx,
                        atr=iv.atr, price=entry_price,
                        base_leverage=self.settings.leverage,
                        max_leverage=self.settings.max_leverage,
                    )
                    final_signal = self.sig_combiner.combine(
                        technical=tech_signal, cryptopanic_score=cp_score,
                        fear_greed_index=fg_index, market_signal=market_signal,
                        coin=coin, entry_price=entry_price, atr=iv.atr,
                        leverage=dyn_leverage,
                    )
                    final_signal.adx = iv.adx
                    final_signal.bb_width_pct = iv.bb_width_pct
                    # combined_score var ama direction NONE olabilir → teknik yönü koru
                    if final_signal.direction == Direction.NONE and final_signal.combined_score >= 0.42:
                        final_signal = FinalSignal(
                            direction=tech_signal.direction,
                            combined_score=final_signal.combined_score,
                            technical_score=final_signal.technical_score,
                            sentiment_score=final_signal.sentiment_score,
                            market_score=final_signal.market_score,
                            coin=coin,
                            entry_price=entry_price,
                            reasons=final_signal.reasons or tech_signal.reasons,
                            atr=iv.atr,
                            leverage=dyn_leverage,
                            adx=iv.adx,
                            bb_width_pct=iv.bb_width_pct,
                        )
                    if final_signal.combined_score >= 0.42:
                        results.append((final_signal, iv, mtf_ok))
                except Exception:
                    continue
        finally:
            self.sig_combiner.min_combined_score = original_min

        results.sort(key=lambda r: r[0].combined_score, reverse=True)
        return results

    def _format_scan_results(self, results: list) -> str:
        """Top 5 fırsatı Telegram mesajı olarak formatlar."""
        from utils.helpers import format_usdt
        now_str = datetime.datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
        if not results:
            return (
                f"📊 <b>PİYASA TARAMASI</b> — {now_str}\n\n"
                "Şu an işlem yapılabilir sinyal bulunamadı.\n"
                "Piyasa yatay veya tüm coinler eşiğin altında."
            )
        trading_threshold = self.settings.min_combined_score
        lines = [f"📊 <b>PİYASA TARAMASI — Top {min(5, len(results))} Fırsat</b>\n{now_str}\n"]
        for i, item in enumerate(results[:5], 1):
            signal, iv, mtf_ok = item
            direction = "LONG" if signal.direction.value == "long" else "SHORT"
            dir_emoji = "🟢" if direction == "LONG" else "🔴"
            score = self._display_score(signal)
            score_str = f"+{score}" if score > 0 else str(score)
            sl  = self.stop_calc.calculate_stop_loss(signal.direction, signal.entry_price, signal.atr)
            tp1 = self.stop_calc.calculate_take_profit(signal.direction, signal.entry_price, sl)
            reasons = self._humanize_reasons(signal, iv)
            reason = reasons[0] if reasons else ""

            # Durumu belirt
            if signal.combined_score >= trading_threshold and mtf_ok:
                status = "✅ İşlem açılabilir"
            elif signal.combined_score >= trading_threshold and not mtf_ok:
                status = "⚠️ Skor yeterli ama 1s trend ters"
            else:
                status = f"🔸 Skor düşük ({signal.combined_score:.2f} < {trading_threshold:.2f})"

            lines.append(
                f"{i}. {dir_emoji} <b>{signal.coin}/USDT — {direction}</b> ({score_str})\n"
                f"   Giriş: {format_usdt(signal.entry_price)} | SL: {format_usdt(sl)} | TP: {format_usdt(tp1)}\n"
                f"   {reason}\n"
                f"   {status}"
            )
        lines.append("\n💡 Girmek için: <code>/ac BTC</code>")
        return "\n\n".join(lines)

    def _build_scan_summary(self, results: list) -> str:
        """Gemini'ye gönderilecek tarama özetini oluşturur."""
        trading_threshold = self.settings.min_combined_score
        fg = self.state.fear_greed_index
        lines = [f"Fear & Greed Index: {fg}/100"]
        for signal, iv, mtf_ok in results[:5]:
            direction = "LONG" if signal.direction.value == "long" else "SHORT"
            actionable = signal.combined_score >= trading_threshold and mtf_ok
            sl  = self.stop_calc.calculate_stop_loss(signal.direction, signal.entry_price, signal.atr)
            tp1 = self.stop_calc.calculate_take_profit(signal.direction, signal.entry_price, sl)
            sl_pct  = abs(signal.entry_price - sl) / signal.entry_price * 100
            tp1_pct = abs(tp1 - signal.entry_price) / signal.entry_price * 100
            lines.append(
                f"{signal.coin} {direction}: skor={signal.combined_score:.2f} "
                f"(teknik={signal.technical_score:.2f}, sentiment={signal.sentiment_score:.2f}) "
                f"fiyat={signal.entry_price} SL=%{sl_pct:.1f} TP=%{tp1_pct:.1f} "
                f"MTF={'uyumlu' if mtf_ok else 'ters'} "
                f"ADX={iv.adx:.1f} RSI={iv.rsi:.1f} "
                f"{'→ TRADE AÇILIR' if actionable else '→ eşik altı/MTF ters'}"
            )
        return "\n".join(lines)

    async def _open_coin_by_command(self, coin: str) -> None:
        """Belirtilen coin için pozisyon açar. Önce cache'e bakar, yoksa fresh eval yapar."""
        from utils.helpers import format_usdt
        # Cache'den bul (3-tuple: signal, iv, mtf_ok)
        cached = next(
            (r for r in self.state.scan_results if r[0].coin == coin),
            None,
        )
        if cached:
            signal, iv, _mtf_ok = cached
        else:
            # Fresh evaluate
            symbol = f"{coin}/USDT:USDT"
            result = await self._evaluate_coin(coin, symbol)
            if not result:
                self.notifier.send(f"⚠️ <b>{coin}</b>: fiyat verisi alınamadı.")
                return
            signal, iv = result

        if not signal.is_actionable:
            direction = "LONG" if signal.direction.value == "long" else "SHORT"
            score = self._display_score(signal)
            self.notifier.send(
                f"⚠️ <b>{coin}</b> sinyali yeterince güçlü değil.\n"
                f"Yön: {direction} | Skor: {score} | Eşik: {self.settings.min_combined_score:.2f}"
            )
            return

        # Mevcut pozisyon kontrolü
        open_coins = set(self.engine.positions.keys()) if self.settings.paper_trading else set(self.state.open_positions.keys())
        if coin in open_coins:
            self.notifier.send(f"⚠️ <b>{coin}</b> için zaten açık pozisyon var.")
            return

        # Circuit breaker
        allowed, reason = self.circuit_breaker.is_trading_allowed(len(open_coins))
        if not allowed:
            self.notifier.send(f"🔴 İşlem açılamaz: {reason}")
            return

        # Pozisyon aç
        portfolio_val = self.engine.portfolio_value if self.settings.paper_trading else self.client.get_portfolio_value()
        self.state.portfolio_value = portfolio_val

        if self.settings.paper_trading:
            pos = self.engine.open_position(signal, portfolio_val)
            if pos:
                self.state.add_position(coin, pos)
                direction = "LONG" if signal.direction.value == "long" else "SHORT"
                self.notifier.send(
                    f"✅ <b>{coin}</b> {direction} pozisyonu açıldı.\n"
                    f"Giriş: {format_usdt(pos.entry_price)} | SL: {format_usdt(pos.stop_loss_price)} | TP1: {format_usdt(pos.take_profit_price)}"
                )
            else:
                self.notifier.send(f"❌ <b>{coin}</b> pozisyonu açılamadı (circuit breaker veya limit).")
        else:
            self.engine.execute(signal, portfolio_val)

    async def send_opportunity_scan(self) -> None:
        """Her 15 dakikada en iyi piyasa fırsatını Telegram'a gönderir."""
        try:
            opp = self.state.best_opportunity
            if not opp:
                return
            signal, iv = opp
            if not signal.is_actionable:
                return

            trend_1h = await asyncio.to_thread(self._get_tf_trend, signal.coin, "1h")
            trend_4h = await asyncio.to_thread(self._get_tf_trend, signal.coin, "4h")
            msg = self._format_opportunity(signal, iv, trend_1h, trend_4h)
            self.notifier.send(msg)
        except Exception as e:
            logger.warning("Fırsat tarayıcı hatası", error=str(e))

    def _get_tf_trend(self, coin: str, tf: str) -> str:
        symbol = f"{coin}/USDT:USDT"
        try:
            df = self.market_data.fetch_ohlcv(symbol, tf)
            if df is None or len(df) < 21:
                return "belirsiz"
            ema9  = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator().iloc[-1]
            ema21 = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator().iloc[-1]
            return "yukarı ↑" if ema9 > ema21 else "aşağı ↓"
        except Exception:
            return "belirsiz"

    def _display_score(self, signal) -> int:
        """combined_score (0-1) → -10/+10 arası görsel skor."""
        magnitude = int((signal.combined_score - 0.5) * 20)
        magnitude = max(1, min(10, magnitude))
        return -magnitude if signal.direction.value == "short" else magnitude

    def _humanize_reasons(self, signal, iv) -> list[str]:
        """İndikatör değerlerini sade Türkçe açıklamalara çevirir."""
        is_short = signal.direction.value == "short"
        reasons = []

        # RSI
        if iv.rsi > 70:
            reasons.append(f"Coin çok alındı, düşüş bekleniyor (RSI: {iv.rsi:.1f})")
        elif iv.rsi > 55 and is_short:
            reasons.append(f"RSI alış bölgesinde ({iv.rsi:.2f})")
        elif iv.rsi < 30:
            reasons.append(f"Coin çok satıldı, yükseliş bekleniyor (RSI: {iv.rsi:.1f})")
        elif iv.rsi < 45 and not is_short:
            reasons.append(f"RSI satış bölgesinden çıkıyor ({iv.rsi:.2f})")
        else:
            reasons.append(f"RSI: {iv.rsi:.1f}")

        # MACD
        if iv.macd_hist < 0:
            reasons.append("Momentum aşağı döndü")
        elif iv.macd_hist > 0:
            reasons.append("Momentum yukarı döndü")

        # EMA trend
        if iv.ema_short < iv.ema_long:
            reasons.append("Kısa vadeli trend aşağı")
        elif iv.ema_short > iv.ema_long:
            reasons.append("Kısa vadeli trend yukarı")

        # Bollinger
        if iv.bb_pct > 0.85:
            reasons.append("Fiyat üst Bollinger bandını test ediyor")
        elif iv.bb_pct < 0.15:
            reasons.append("Fiyat alt Bollinger bandını test ediyor")

        # ADX
        if iv.adx > 40:
            reasons.append(f"Trend çok güçlü (ADX: {iv.adx:.0f})")
        elif iv.adx > 25:
            reasons.append(f"Trend güçleniyor (ADX: {iv.adx:.0f})")

        return reasons[:5]

    def _format_opportunity(self, signal, iv, trend_1h: str, trend_4h: str) -> str:
        direction = "LONG" if signal.direction.value == "long" else "SHORT"
        dir_emoji = "🟢" if direction == "LONG" else "🔴"
        score = self._display_score(signal)
        score_str = f"+{score}" if score > 0 else str(score)
        now = datetime.datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
        reasons = self._humanize_reasons(signal, iv)
        trend_desc = "yükseliş" if direction == "LONG" else "düşüş"
        reasons_text = "\n".join(f"  - {r}" for r in reasons)

        return (
            f"🔍 <b>EN İYİ FIRSAT: {signal.coin}USDT — {direction}</b>\n"
            f"{now} | Skor: {score_str}\n\n"
            f"1s trend: {trend_1h} | 4s trend: {trend_4h}\n"
            f"{dir_emoji} En güçlü {trend_desc} sinyali bu coinde\n"
            f"{reasons_text}"
        )

    async def _handle_telegram_command(self, command: str, **kwargs) -> None:
        """Telegram'dan gelen komutları işler."""
        if command == "kapat":
            coin = kwargs.get("coin", "").upper()
            if self.settings.paper_trading:
                pos = self.engine.positions.get(coin)
                if pos:
                    price = self.market_data.get_current_price(f"{coin}/USDT:USDT") or pos.entry_price
                    self.engine._close_position(coin, pos, price, "CLOSED_MANUAL")
                    self.state.remove_position(coin)
                    self.notifier.send(f"✅ <b>{coin}</b> pozisyonu manuel olarak kapatıldı.")
                else:
                    self.notifier.send(f"⚠️ <b>{coin}</b> için açık pozisyon bulunamadı.")
            else:
                if coin in self.state.open_positions:
                    self.engine.close_position(coin, "CLOSED_MANUAL")
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
                coins = list(self.state.open_positions.keys())
                if not coins:
                    self.notifier.send("ℹ️ Kapatılacak açık pozisyon yok.")
                    return
                ok = [c for c in coins if self.engine.close_position(c, "CLOSED_MANUAL")]
                self.notifier.send(f"✅ {len(ok)}/{len(coins)} pozisyon kapatıldı: {', '.join(ok)}")

        elif command == "durdur":
            self.circuit_breaker.is_halted = True
            self.notifier.send("🔴 <b>Bot durduruldu.</b> Yeni işlem açılmayacak.\n/baslat ile devam ettir.")

        elif command == "baslat":
            self.circuit_breaker.is_halted = False
            self.notifier.send("🟢 <b>Bot devam ediyor.</b> Yeni işlemler açılabilir.")

        elif command == "tara":
            self.notifier.send("🔍 Piyasa taranıyor, lütfen bekleyin...")
            try:
                results = await self.scan_coins_for_report()
                self.state.scan_results = results
                msg = self._format_scan_results(results)
                self.notifier.send(msg)
                # Gemini ile genel yorum
                if self.gemini_analyzer.enabled and results:
                    summary = self._build_scan_summary(results)
                    commentary = await asyncio.to_thread(
                        self.gemini_analyzer.analyze_scan, summary
                    )
                    if commentary:
                        self.notifier.send(f"🤖 <b>Gemini Yorumu</b>\n\n{commentary}")
            except Exception as e:
                self.notifier.send(f"❌ Tarama başarısız: {e}")

        elif command == "ac":
            coin = kwargs.get("coin", "").upper().replace("USDT", "").strip()
            if not coin:
                self.notifier.send("⚠️ Kullanım: /ac BTC")
                return
            self.notifier.send(f"🔍 <b>{coin}</b> analiz ediliyor...")
            try:
                await self._open_coin_by_command(coin)
            except Exception as e:
                self.notifier.send(f"❌ {coin} işlemi açılamadı: {e}")

        elif command == "bakiye":
            try:
                if self.settings.paper_trading:
                    balance = self.engine.portfolio_value
                else:
                    balance = self.state.portfolio_value
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

            # DB'de OPEN ama OKX'te yok → kapanmış say
            for coin in list(self.state.open_positions.keys()):
                if coin not in live_coins:
                    record = self.state.open_positions.get(coin)
                    symbol = f"{coin}/USDT:USDT"
                    mark_price = self.market_data.get_current_price(symbol) or (
                        record.entry_price if record else 0.0
                    )
                    if record and record.db_id and mark_price > 0:
                        pnl = (
                            (mark_price - record.entry_price) * record.quantity
                            if record.direction == "long"
                            else (record.entry_price - mark_price) * record.quantity
                        )
                        pnl_pct = pnl / record.margin_used if record.margin_used > 0 else 0.0
                        self.trade_logger.log_close(
                            record.db_id, mark_price, "CLOSED_MANUAL", pnl, pnl_pct
                        )
                        self.notifier.send_alert(
                            f"ℹ️ {coin} OKX'te kapanmış — DB güncellendi (PnL: {pnl:+.2f} USDT)"
                        )
                    self.state.remove_position(coin)
                    logger.info("Pozisyon kapandı (OKX senkronizasyon)", coin=coin)

            # OKX'te açık ama bot'ta kayıt yok → uyarı ver
            bot_coins = set(self.state.open_positions.keys())
            for live_coin in live_coins:
                if live_coin not in bot_coins:
                    logger.warning("OKX'te kayıtsız pozisyon var!", coin=live_coin)
                    self.notifier.send_alert(
                        f"⚠️ OKX'te {live_coin} pozisyonu var ama bot kayıtlarında yok!"
                    )

        except Exception as e:
            logger.warning("OKX pozisyon senkronizasyon hatası", error=str(e))

    async def _reconcile_live_positions(self) -> None:
        """
        Bot restart'ında OKX pozisyonlarını DB ile tam karşılaştır.
        DB'deki OPEN pozisyonları state'e yükler; OKX'te olmayan kapalı sayar.
        """
        logger.info("Canlı pozisyon mutabakatı başlatılıyor...")
        try:
            # DB'deki açık işlemleri yükle
            open_trades = self.trade_logger.get_open_trades()
            live_positions = self.client.fetch_positions()
            live_coins = {
                p["symbol"].split("/")[0]
                for p in live_positions
                if p.get("contracts", 0) > 0
            }

            reconciled = 0
            for t in open_trades:
                coin = t["coin"]
                if t.get("is_paper"):
                    continue  # paper trade'leri atla

                if coin in live_coins:
                    # OKX'te gerçekten açık → state'e ekle
                    from database.trade_logger import TradeRecord
                    record = TradeRecord(
                        coin=coin,
                        direction=t["direction"],
                        entry_price=t["entry_price"],
                        stop_loss_price=t["stop_loss_price"],
                        take_profit_price=t["take_profit_price"],
                        quantity=t["quantity"],
                        margin_used=t["margin_used"],
                        leverage=t["leverage"],
                        is_paper=False,
                    )
                    record.db_id = t["id"]
                    self.state.add_position(coin, record)
                    reconciled += 1
                else:
                    # OKX'te yok → kapanmış say
                    symbol = f"{coin}/USDT:USDT"
                    mark_price = self.market_data.get_current_price(symbol) or t["entry_price"]
                    direction = t["direction"]
                    qty = t["quantity"]
                    entry = t["entry_price"]
                    margin = t["margin_used"]
                    pnl = (mark_price - entry) * qty if direction == "long" else (entry - mark_price) * qty
                    pnl_pct = pnl / margin if margin > 0 else 0.0
                    self.trade_logger.log_close(t["id"], mark_price, "CLOSED_MANUAL", pnl, pnl_pct)
                    logger.warning("DB'deki pozisyon OKX'te yok — kapandı sayıldı", coin=coin)

            if reconciled:
                logger.info("Mutabakat tamamlandı", live_positions=reconciled)
                self.notifier.send_alert(
                    f"🔄 Bot yeniden başlatıldı. {reconciled} açık pozisyon senkronize edildi."
                )
        except Exception as e:
            logger.error("Pozisyon mutabakatı hatası", error=str(e))
