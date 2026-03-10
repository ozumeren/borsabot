from __future__ import annotations
import feedparser
import httpx
from typing import Optional
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from config.constants import RSS_FEEDS
from utils.logger import get_logger

logger = get_logger("sentiment.rss")


class RSSFeedFetcher:
    """CoinDesk, CoinTelegraph, Decrypt vb. RSS beslemelerinden haber çeker."""

    def __init__(self, feeds: Optional[list] = None):
        self.feeds = feeds or RSS_FEEDS

    def fetch_all(self, max_age_hours: int = 6) -> list[dict]:
        """Son N saatteki tüm haberleri döndürür."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        articles = []

        for url in self.feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    published = self._parse_date(entry)
                    if published and published < cutoff:
                        continue

                    title = entry.get("title", "").strip()
                    summary = self._clean_html(entry.get("summary", ""))

                    articles.append({
                        "title": title,
                        "summary": summary[:300],
                        "url": entry.get("link", ""),
                        "published": published,
                        "source": feed.feed.get("title", url),
                    })
            except Exception as e:
                logger.warning("RSS çekme hatası", url=url, error=str(e))

        logger.debug("RSS haberleri çekildi", count=len(articles))
        return articles

    def filter_by_coin(self, articles: list[dict], coin: str) -> list[str]:
        """Coin ile ilgili haberleri filtrele, başlık+özet listesi döndür."""
        coin_lower = coin.lower()
        results = []
        for art in articles:
            text = f"{art['title']} {art['summary']}".lower()
            if coin_lower in text or self._coin_aliases(coin_lower, text):
                results.append(art["title"])
        return results

    def _coin_aliases(self, coin: str, text: str) -> bool:
        aliases = {
            "btc": ["bitcoin"],
            "eth": ["ethereum"],
            "sol": ["solana"],
            "bnb": ["binance coin", "binance smart chain"],
            "xrp": ["ripple"],
            "ada": ["cardano"],
            "doge": ["dogecoin"],
            "avax": ["avalanche"],
            "dot": ["polkadot"],
            "matic": ["polygon"],
        }
        for alias in aliases.get(coin, []):
            if alias in text:
                return True
        return False

    def _parse_date(self, entry) -> Optional[datetime]:
        try:
            import time
            t = entry.get("published_parsed") or entry.get("updated_parsed")
            if t:
                return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
        except Exception:
            pass
        return None

    def _clean_html(self, html: str) -> str:
        try:
            return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
        except Exception:
            return html
