#!/usr/bin/env python3
"""
BorsaBot — OKX Kripto Futures Trading Bot
Başlatmak için: python main.py
"""
import asyncio
import sys
from pathlib import Path

# Proje kökünü Python path'ine ekle
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from core.bot import BotEngine
from core.scheduler import BotScheduler
from utils.logger import setup_logging, get_logger

logger = get_logger("main")


async def main() -> None:
    setup_logging(log_level="INFO")
    logger.info("=" * 50)
    logger.info("BorsaBot başlatılıyor")
    logger.info("=" * 50)

    # Canlı moda geçmeden önce kontrol
    if not settings.paper_trading:
        errors = settings.validate_for_live()
        if errors:
            logger.error("Canlı trading için gerekli ayarlar eksik", errors=errors)
            sys.exit(1)
        logger.warning("=" * 50)
        logger.warning("UYARI: CANLI TRADING MODU AKTİF")
        logger.warning("Gerçek para kullanılıyor!")
        logger.warning("=" * 50)
        # 5 saniye bekleme — yanlışlıkla başlatmaya karşı
        await asyncio.sleep(5)
    else:
        logger.info("Paper trading modu (simülasyon) aktif")

    bot = BotEngine(settings)
    await bot.initialize()

    # İlk veri çekimlerini hemen yap (scheduler'ı beklemeden)
    await bot.fetch_fear_greed()
    await bot.fetch_news()
    await bot.fetch_funding_data()

    scheduler = BotScheduler()
    scheduler.setup(bot)
    scheduler.start()

    try:
        # Sonsuz döngü
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Kapatma sinyali alındı")
    finally:
        await bot.shutdown()
        scheduler.stop()
        logger.info("Bot kapatıldı")


if __name__ == "__main__":
    asyncio.run(main())
