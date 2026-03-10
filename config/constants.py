# ── Teknik Analiz Parametreleri ──────────────────────────────────────────────
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL_PERIOD = 9

EMA_SHORT = 9
EMA_LONG = 21
SMA_LONG = 200

BB_PERIOD = 20
BB_STD = 2.0

ATR_PERIOD = 14
MIN_CANDLES = 50  # indikatörler için minimum mum sayısı

# ── OKX Rate Limit ───────────────────────────────────────────────────────────
OKX_RATE_LIMIT_MARKET = 20    # 2 saniyede max istek
OKX_RATE_LIMIT_ORDERS = 60

# ── Retry Ayarları ───────────────────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0   # saniye
RETRY_MAX_DELAY = 32.0

# ── Zamanlama (saniye) ───────────────────────────────────────────────────────
POSITION_MONITOR_INTERVAL = 10
MAIN_LOOP_INTERVAL = 60
NEWS_FETCH_INTERVAL = 300
FEAR_GREED_INTERVAL = 3600
DAILY_RESET_HOUR = 0      # UTC gece yarısı

# ── Coin Tarama ──────────────────────────────────────────────────────────────
VOLUME_QUOTE_CURRENCY = "USDT"
MIN_24H_VOLUME_USDT = 5_000_000   # $5M minimum hacim
MAX_SPREAD_PCT = 0.005             # max %0.5 spread
STABLECOIN_BLACKLIST = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "PYUSD"}

# ── RSS Kaynakları ────────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://theblock.co/rss.xml",
]

# ── Fear & Greed API ─────────────────────────────────────────────────────────
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# ── CryptoPanic API ──────────────────────────────────────────────────────────
CRYPTOPANIC_BASE_URL = "https://cryptopanic.com/api/developer/v2/posts/"

# ── Sinyal Ağırlıkları ───────────────────────────────────────────────────────
TECHNICAL_WEIGHT   = 0.55
SENTIMENT_WEIGHT   = 0.25   # CryptoPanic + Fear&Greed
MARKET_DATA_WEIGHT = 0.20   # Funding rate + Long/Short oranı

CRYPTOPANIC_WEIGHT = 0.60   # sentiment içindeki ağırlık
FEAR_GREED_WEIGHT  = 0.40

# ── Funding Rate Fetch Aralığı ────────────────────────────────────────────────
FUNDING_FETCH_INTERVAL = 300   # 5 dakika (funding her 8 saatte sıfırlanır)

# ── Risk ─────────────────────────────────────────────────────────────────────
DEFAULT_RISK_REWARD = 2.0    # take-profit = stop mesafesi × 2
MIN_STOP_DISTANCE_PCT = 0.005  # minimum %0.5 stop
