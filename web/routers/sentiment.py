from typing import Any
from fastapi import APIRouter
from database.db import get_session
from database.models import SentimentLog

router = APIRouter()
_engine: Any = None


@router.get("/sentiment/overview")
async def sentiment_overview():
    state = _engine.state

    # Recent news headlines per coin (from cache)
    news = {coin: headlines[:3] for coin, headlines in state.news_cache.items()}

    # Gemini scores
    gemini = {}
    for coin, (score, reason) in state.gemini_cache.items():
        gemini[coin] = {"score": score, "reason": reason}

    # Recent sentiment from DB
    with get_session() as session:
        rows = (
            session.query(SentimentLog)
            .order_by(SentimentLog.timestamp.desc())
            .limit(50)
            .all()
        )
        recent_logs = [
            {
                "coin": r.coin,
                "timestamp": r.timestamp,
                "cryptopanic_score": r.cryptopanic_score,
                "fear_greed_index": r.fear_greed_index,
                "combined_score": r.combined_score,
            }
            for r in rows
        ]

    return {
        "fear_greed_index": state.fear_greed_index,
        "btc_regime": state.btc_regime,
        "news_by_coin": news,
        "gemini_scores": gemini,
        "recent_sentiment_logs": recent_logs,
    }


@router.get("/sentiment/{coin}")
async def coin_sentiment(coin: str):
    coin = coin.upper()
    state = _engine.state

    headlines = state.news_cache.get(coin, [])
    gemini_data = state.gemini_cache.get(coin)
    funding = state.funding_cache.get(coin)

    with get_session() as session:
        rows = (
            session.query(SentimentLog)
            .filter(SentimentLog.coin == coin)
            .order_by(SentimentLog.timestamp.desc())
            .limit(20)
            .all()
        )
        logs = [
            {
                "timestamp": r.timestamp,
                "cryptopanic_score": r.cryptopanic_score,
                "fear_greed_index": r.fear_greed_index,
                "combined_score": r.combined_score,
                "source_summary": r.source_summary,
            }
            for r in rows
        ]

    return {
        "coin": coin,
        "headlines": headlines,
        "gemini_score": gemini_data[0] if gemini_data else None,
        "gemini_reason": gemini_data[1] if gemini_data else None,
        "funding_rate": getattr(funding, "weighted_rate", None) if funding else None,
        "sentiment_history": logs,
    }
