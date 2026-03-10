from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import ccxt
import logging

logger = logging.getLogger("borsabot.retry")

# Yeniden denenmesi gereken hatalar
RETRYABLE_EXCEPTIONS = (
    ccxt.NetworkError,
    ccxt.RateLimitExceeded,
    ccxt.RequestTimeout,
)

# Hiçbir zaman yeniden denenmemesi gereken hatalar
NON_RETRYABLE_EXCEPTIONS = (
    ccxt.AuthenticationError,
    ccxt.InsufficientFunds,
    ccxt.InvalidOrder,
    ccxt.BadSymbol,
)


def exchange_retry(max_attempts: int = 5, base_delay: float = 1.0, max_delay: float = 32.0):
    """OKX API çağrıları için retry dekoratörü."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_delay, min=base_delay, max=max_delay),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def http_retry(max_attempts: int = 3, base_delay: float = 2.0):
    """Dış HTTP API çağrıları için retry dekoratörü."""
    import httpx

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=base_delay, min=base_delay, max=16.0),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
