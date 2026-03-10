import httpx
from config.constants import FEAR_GREED_URL
from utils.logger import get_logger

logger = get_logger("sentiment.fear_greed")


class FearGreedFetcher:
    """alternative.me Fear & Greed Index (ücretsiz API)."""

    def __init__(self):
        self._cached_value: int = 50  # Başlangıç: nötr

    def fetch(self) -> int:
        """0 (Extreme Fear) → 100 (Extreme Greed) arası indeks döner."""
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(FEAR_GREED_URL, params={"limit": 1})
                resp.raise_for_status()
                data = resp.json()
                value = int(data["data"][0]["value"])
                label = data["data"][0]["value_classification"]
                self._cached_value = value
                logger.info("Fear & Greed güncellendi", value=value, label=label)
                return value
        except Exception as e:
            logger.warning("Fear & Greed alınamadı, cache kullanılıyor", error=str(e))
            return self._cached_value

    def get_cached(self) -> int:
        return self._cached_value

    def classify(self, value: int) -> str:
        if value <= 25:
            return "Extreme Fear"
        if value <= 45:
            return "Fear"
        if value <= 55:
            return "Neutral"
        if value <= 75:
            return "Greed"
        return "Extreme Greed"
