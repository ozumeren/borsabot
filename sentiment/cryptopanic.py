import httpx
from config.constants import CRYPTOPANIC_BASE_URL
from utils.logger import get_logger

logger = get_logger("sentiment.cryptopanic")

# Sentiment etiket → skor dönüşümü
VOTE_SCORE_MAP = {
    "important": 0.3,
    "bullish": 1.0,
    "bearish": -1.0,
    "lol": -0.2,
    "toxic": -0.4,
    "saved": 0.2,
}


class CryptoPanicFetcher:
    """CryptoPanic API - kripto haber sentiment analizi."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._base_url = CRYPTOPANIC_BASE_URL

    def fetch_news(self, coin: str, limit: int = 20) -> list[dict]:
        """Belirli bir coin için son haberleri çeker."""
        if not self.api_key:
            logger.debug("CryptoPanic API key yok, atlanıyor")
            return []

        try:
            params = {
                "auth_token": self.api_key,
                "currencies": coin.upper(),
                "public": "true",
                "limit": limit,
                "kind": "news",
            }
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(self._base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", [])
        except Exception as e:
            logger.warning("CryptoPanic API hatası", coin=coin, error=str(e))
            return []

    def calculate_sentiment_score(self, news_items: list[dict]) -> float:
        """
        Haber listesinden -1.0 ile +1.0 arasında sentiment skoru hesaplar.
        Oy bilgisi yoksa başlıktaki anahtar kelimelerden tahmin eder.
        """
        if not news_items:
            return 0.0

        scores = []
        for item in news_items:
            votes = item.get("votes", {})
            if votes:
                score = self._votes_to_score(votes)
                scores.append(score)
            else:
                # Başlıktan basit keyword analizi
                title = (item.get("title") or "").lower()
                score = self._keyword_score(title)
                scores.append(score)

        return sum(scores) / len(scores) if scores else 0.0

    def get_headlines(self, news_items: list[dict]) -> list[str]:
        return [item.get("title", "") for item in news_items if item.get("title")]

    def _votes_to_score(self, votes: dict) -> float:
        total_weight = 0.0
        weighted_score = 0.0
        for label, weight in VOTE_SCORE_MAP.items():
            count = votes.get(label, 0) or 0
            weighted_score += count * weight
            total_weight += abs(count * weight)
        if total_weight == 0:
            return 0.0
        return max(-1.0, min(1.0, weighted_score / max(total_weight, 1)))

    def _keyword_score(self, title: str) -> float:
        bullish_words = ["surge", "rally", "pump", "moon", "bullish", "high", "record",
                         "adoption", "partnership", "launch", "upgrade", "gain", "rise"]
        bearish_words = ["crash", "dump", "drop", "bear", "bearish", "hack", "ban",
                         "lawsuit", "fraud", "sell", "fall", "decline", "low", "fear"]
        bull = sum(1 for w in bullish_words if w in title)
        bear = sum(1 for w in bearish_words if w in title)
        total = bull + bear
        if total == 0:
            return 0.0
        return (bull - bear) / total
