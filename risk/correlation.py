"""
Korelasyon grubu limiti.
Aynı grup içindeki coinlerde aynı anda en fazla 2 pozisyon açılabilir.
"""
from utils.logger import get_logger

logger = get_logger("risk.correlation")

# Hard-coded korelasyon grupları
GROUPS: dict = {
    "btclike": {"BTC", "ETH", "SOL", "BNB", "AVAX"},
    "defi":    {"UNI", "AAVE", "LINK", "CRV", "MKR"},
    "layer2":  {"ARB", "OP", "IMX", "MATIC", "MANTA"},
    "meme":    {"DOGE", "SHIB", "PEPE", "FLOKI", "BONK"},
}

MAX_PER_GROUP = 2


class CorrelationGuard:
    """Aynı korelasyon grubundan maksimum MAX_PER_GROUP pozisyon açılmasına izin verir."""

    def _group_of(self, coin: str) -> str:
        """Coin'in hangi gruba ait olduğunu döndürür. Grupda yoksa 'other'."""
        for group_name, members in GROUPS.items():
            if coin.upper() in members:
                return group_name
        return "other"

    def can_open(self, coin: str, open_positions: set) -> bool:
        """
        Yeni pozisyon açmak için izin verir mi?

        coin            : açılmak istenen coin (örn. 'BTC')
        open_positions  : halihazırda açık coinlerin set'i
        """
        group = self._group_of(coin)
        if group == "other":
            return True  # Bilinen grupta değilse limit yok

        group_members = GROUPS[group]
        count = sum(1 for c in open_positions if c.upper() in group_members)

        if count >= MAX_PER_GROUP:
            logger.info(
                "Korelasyon grubu limiti aşıldı",
                coin=coin,
                group=group,
                count=count,
                max=MAX_PER_GROUP,
            )
            return False
        return True
