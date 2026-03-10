from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Exchange ──────────────────────────────────────────────────────────────
    okx_api_key: str = Field(default="", alias="OKX_API_KEY")
    okx_secret_key: str = Field(default="", alias="OKX_SECRET_KEY")
    okx_passphrase: str = Field(default="", alias="OKX_PASSPHRASE")
    okx_sandbox: bool = Field(default=True, alias="OKX_SANDBOX")

    # ── Trading ───────────────────────────────────────────────────────────────
    leverage: int = Field(default=5, alias="LEVERAGE")
    margin_mode: Literal["isolated", "cross"] = Field(default="isolated", alias="MARGIN_MODE")
    max_concurrent_positions: int = Field(default=5, alias="MAX_CONCURRENT_POSITIONS")
    timeframe: str = Field(default="15m", alias="TIMEFRAME")
    scan_top_n_coins: int = Field(default=30, alias="SCAN_TOP_N_COINS")

    # ── Risk ─────────────────────────────────────────────────────────────────
    daily_loss_limit_pct: float = Field(default=0.03, alias="DAILY_LOSS_LIMIT_PCT")
    stop_loss_pct_from_entry: float = Field(default=0.015, alias="STOP_LOSS_PCT_FROM_ENTRY")
    max_position_size_pct: float = Field(default=0.10, alias="MAX_POSITION_SIZE_PCT")

    # ── Sinyal Eşikleri ───────────────────────────────────────────────────────
    min_technical_score: float = Field(default=0.6, alias="MIN_TECHNICAL_SCORE")
    min_combined_score: float = Field(default=0.55, alias="MIN_COMBINED_SCORE")

    # ── Sentiment API'ları ────────────────────────────────────────────────────
    cryptopanic_api_key: str = Field(default="", alias="CRYPTOPANIC_API_KEY")

    # ── Bildirimler ───────────────────────────────────────────────────────────
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # ── Veritabanı ────────────────────────────────────────────────────────────
    database_url: str = Field(default="sqlite:///borsabot.db", alias="DATABASE_URL")

    # ── Güvenlik ─────────────────────────────────────────────────────────────
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")

    def validate_for_live(self) -> list[str]:
        """Canlı trading için gerekli alanları kontrol eder."""
        errors = []
        if not self.okx_api_key:
            errors.append("OKX_API_KEY eksik")
        if not self.okx_secret_key:
            errors.append("OKX_SECRET_KEY eksik")
        if not self.okx_passphrase:
            errors.append("OKX_PASSPHRASE eksik")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN eksik")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID eksik")
        return errors


settings = BotSettings()
