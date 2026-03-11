from __future__ import annotations
import json
import time
import httpx
from utils.logger import get_logger

logger = get_logger("sentiment.gemini")

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1"
    "/models/gemini-2.5-flash-lite:generateContent"
)
CACHE_TTL = 600  # 10 dakika


class GeminiAnalyzer:
    """Google Gemini Flash ile haber sentiment analizi."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._cache: dict[str, tuple[float, str, float]] = {}  # coin → (score, reason, ts)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, coin: str, headlines: list[str]) -> tuple[float, str]:
        """
        Haberleri Gemini ile analiz eder.
        Dönüş: (score, reason)  — score: -1.0 (çok bearish) → +1.0 (çok bullish)
        Hata veya API yok → (0.0, "")
        """
        if not self.enabled or not headlines:
            return 0.0, ""

        cached = self._cache.get(coin)
        if cached and (time.time() - cached[2]) < CACHE_TTL:
            logger.debug("Gemini cache hit", coin=coin, score=cached[0])
            return cached[0], cached[1]

        prompt = self._build_prompt(coin, headlines)
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    f"{GEMINI_API_URL}?key={self.api_key}",
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 400,
                        },
                    },
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                score, reason = self._parse_response(text)
                self._cache[coin] = (score, reason, time.time())
                logger.info("Gemini analizi", coin=coin, score=f"{score:.2f}", reason=reason)
                return score, reason

        except Exception as e:
            logger.warning("Gemini API hatası", coin=coin, error=str(e))
            return 0.0, ""

    def _build_prompt(self, coin: str, headlines: list[str]) -> str:
        headlines_text = "\n".join(f"- {h}" for h in headlines[:8])
        return (
            f"You are a crypto market analyst. Analyze these recent news headlines for {coin}.\n\n"
            f"Headlines:\n{headlines_text}\n\n"
            f"Return ONLY valid JSON in this exact format:\n"
            f'{{\"score\": 0.0, \"reason\": \"kısa Türkçe açıklama\"}}\n\n'
            f"Rules:\n"
            f"- score: -1.0 (çok bearish) to 1.0 (çok bullish), 0.0 = nötr\n"
            f"- reason: 1 cümle Türkçe, neden bu skoru verdiğini açıkla\n"
            f"- Sadece JSON döndür, başka hiçbir şey yazma"
        )

    def _parse_response(self, text: str) -> tuple[float, str]:
        # Markdown kod bloğunu temizle (```json ... ```)
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:])  # ilk satırı (```json) at
            if clean.endswith("```"):
                clean = clean[:-3]
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start == -1 or end == 0:
            return 0.0, ""
        try:
            data = json.loads(clean[start:end])
            score = float(data.get("score", 0.0))
            score = max(-1.0, min(1.0, score))
            reason = str(data.get("reason", ""))
            return score, reason
        except (json.JSONDecodeError, ValueError):
            return 0.0, ""
