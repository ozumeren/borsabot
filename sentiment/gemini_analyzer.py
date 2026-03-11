from __future__ import annotations
import json
import time
import httpx
from utils.logger import get_logger

logger = get_logger("sentiment.gemini")

# Fallback sırası: önce en güncel, rate limit'te bir sonrakine geç
MODELS = [
    ("v1beta", "gemini-3.1-flash-lite-preview"),
    ("v1",     "gemini-2.5-flash-lite"),
    ("v1",     "gemini-2.5-flash"),
    ("v1",     "gemini-2.0-flash"),
]

CACHE_TTL = 600  # 10 dakika


class GeminiAnalyzer:
    """Google Gemini ile haber sentiment analizi. Rate limit'te otomatik model değiştirir."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._cache: dict[str, tuple[float, str, float]] = {}  # coin → (score, reason, ts)
        self._model_index = 0   # şu an kullanılan model indeksi
        self._model_blocked_until: dict[int, float] = {}  # model_idx → cooldown bitiş ts

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, coin: str, headlines: list[str]) -> tuple[float, str]:
        """
        Haberleri Gemini ile analiz eder.
        Dönüş: (score, reason)  — score: -1.0 (çok bearish) → +1.0 (çok bullish)
        Tüm modeller başarısız → (0.0, "")
        """
        if not self.enabled or not headlines:
            return 0.0, ""

        cached = self._cache.get(coin)
        if cached and (time.time() - cached[2]) < CACHE_TTL:
            logger.debug("Gemini cache hit", coin=coin, score=cached[0])
            return cached[0], cached[1]

        prompt = self._build_prompt(coin, headlines)

        # Tüm modelleri sırayla dene
        for idx, (version, model_name) in enumerate(MODELS):
            # Cooldown süresi geçmemişse atla
            blocked_until = self._model_blocked_until.get(idx, 0)
            if time.time() < blocked_until:
                continue

            url = f"https://generativelanguage.googleapis.com/{version}/models/{model_name}:generateContent?key={self.api_key}"
            try:
                with httpx.Client(timeout=25.0) as client:
                    resp = client.post(
                        url,
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {
                                "temperature": 0.1,
                                "maxOutputTokens": 400,
                            },
                        },
                    )

                if resp.status_code == 429:
                    # Rate limit — 5 dakika cooldown, sonrakini dene
                    self._model_blocked_until[idx] = time.time() + 300
                    logger.warning("Gemini rate limit, model değiştiriliyor", model=model_name, next_model=MODELS[min(idx+1, len(MODELS)-1)][1])
                    continue

                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                score, reason = self._parse_response(text)
                self._cache[coin] = (score, reason, time.time())
                logger.info("Gemini analizi", coin=coin, model=model_name, score=f"{score:.2f}", reason=reason)
                self._model_index = idx  # başarılı modeli kaydet
                return score, reason

            except httpx.TimeoutException:
                logger.warning("Gemini timeout, sonraki model deneniyor", model=model_name)
                self._model_blocked_until[idx] = time.time() + 120  # 2 dk cooldown
                continue
            except Exception as e:
                logger.warning("Gemini API hatası", model=model_name, coin=coin, error=str(e))
                continue

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
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:])
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
