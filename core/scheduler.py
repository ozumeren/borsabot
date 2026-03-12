import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config.constants import (
    POSITION_MONITOR_INTERVAL,
    MAIN_LOOP_INTERVAL,
    NEWS_FETCH_INTERVAL,
    FEAR_GREED_INTERVAL,
    FUNDING_FETCH_INTERVAL,
    DAILY_RESET_HOUR,
)
from utils.logger import get_logger

logger = get_logger("core.scheduler")


class BotScheduler:
    """APScheduler ile tüm job'ları yönetir."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def setup(self, bot) -> None:
        """Bot'un tüm periyodik job'larını kaydet."""

        # Pozisyon izleme — 10 saniye
        self.scheduler.add_job(
            bot.monitor_positions,
            IntervalTrigger(seconds=POSITION_MONITOR_INTERVAL),
            id="position_monitor",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=5,
        )

        # Ana sinyal döngüsü — 60 saniye
        self.scheduler.add_job(
            bot.run_signal_loop,
            IntervalTrigger(seconds=MAIN_LOOP_INTERVAL),
            id="main_signal_loop",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )

        # Haber çekme — 5 dakika
        self.scheduler.add_job(
            bot.fetch_news,
            IntervalTrigger(seconds=NEWS_FETCH_INTERVAL),
            id="news_fetcher",
            max_instances=1,
            misfire_grace_time=60,
        )

        # Fear & Greed — 1 saat
        self.scheduler.add_job(
            bot.fetch_fear_greed,
            IntervalTrigger(seconds=FEAR_GREED_INTERVAL),
            id="fear_greed_fetcher",
            max_instances=1,
        )

        # BTC piyasa rejimi — 30 dakika
        self.scheduler.add_job(
            bot.update_btc_regime,
            IntervalTrigger(minutes=30),
            id="btc_regime",
            max_instances=1,
            misfire_grace_time=60,
        )

        # Çoklu borsa funding verisi — 5 dakika
        self.scheduler.add_job(
            bot.fetch_funding_data,
            IntervalTrigger(seconds=FUNDING_FETCH_INTERVAL),
            id="funding_fetcher",
            max_instances=1,
            misfire_grace_time=60,
        )

        # Canlı durum mesajı güncelleme — 1 dakika (30s offset, signal_loop ile çakışmasın)
        import datetime as _dt
        _status_start = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=30)
        self.scheduler.add_job(
            bot.send_live_status_update,
            IntervalTrigger(minutes=1, start_date=_status_start),
            id="live_status_update",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=55,
        )

        # En iyi fırsat tarayıcı — 15 dakika
        self.scheduler.add_job(
            bot.send_opportunity_scan,
            IntervalTrigger(minutes=15),
            id="opportunity_scan",
            max_instances=1,
        )

        # PnL özeti — 15 dakika
        self.scheduler.add_job(
            bot.send_pnl_update,
            IntervalTrigger(minutes=15),
            id="pnl_update",
            max_instances=1,
        )

        # Açık pozisyon detay raporu — 30 dakika
        self.scheduler.add_job(
            bot.send_positions_report,
            IntervalTrigger(minutes=30),
            id="positions_report",
            max_instances=1,
        )

        # Günlük sıfırlama — gece 00:00 UTC
        self.scheduler.add_job(
            bot.daily_reset,
            CronTrigger(hour=DAILY_RESET_HOUR, minute=0, second=0, timezone="UTC"),
            id="daily_reset",
            max_instances=1,
        )

        logger.info("Tüm job'lar zamanlandı", job_count=len(self.scheduler.get_jobs()))

    def start(self) -> None:
        self.scheduler.start()
        logger.info("Scheduler başlatıldı")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler durduruldu")
