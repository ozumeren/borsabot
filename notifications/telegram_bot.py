from __future__ import annotations
import asyncio
import datetime
import httpx
from utils.logger import get_logger
from utils.helpers import format_usdt, format_pct

logger = get_logger("notifications.telegram")


class TelegramNotifier:
    """Telegram Bot API ile bildirim gönderir (sync wrapper)."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._enabled = bool(bot_token and chat_id)

    def send(self, text: str) -> bool:
        if not self._enabled:
            logger.debug("Telegram devre dışı (token/chat_id eksik)")
            return False
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning("Telegram gönderim hatası", error=str(e))
            return False

    def send_trade_opened(self, pos, is_paper: bool = False) -> None:
        mode = "[PAPER]" if is_paper else "[CANLI]"
        direction_emoji = "🟢 LONG" if pos.direction == "long" else "🔴 SHORT"
        text = (
            f"<b>{mode} YENİ POZİSYON</b>\n"
            f"Coin: <b>{pos.coin}/USDT</b>\n"
            f"Yön: {direction_emoji} ({pos.leverage}x)\n"
            f"Giriş: {format_usdt(pos.entry_price)}\n"
            f"Stop-Loss: {format_usdt(pos.stop_loss_price)}\n"
            f"Take-Profit: {format_usdt(pos.take_profit_price)}\n"
            f"Miktar: {pos.quantity:.4f} ({format_usdt(pos.quantity * pos.entry_price)})\n"
            f"Teminat: {format_usdt(pos.margin)}"
        )
        self.send(text)

    def send_trade_closed(
        self,
        coin: str,
        status: str,
        pnl: float,
        pnl_pct: float,
        is_paper: bool = False,
    ) -> None:
        mode = "[PAPER]" if is_paper else "[CANLI]"
        status_map = {
            "CLOSED_TP": "✅ TAKE PROFIT HIT",
            "CLOSED_SL": "❌ STOP LOSS HIT",
            "CLOSED_CIRCUIT": "⚠️ ACİL KAPAMA",
            "CLOSED_MANUAL": "🔵 MANUEL KAPAMA",
        }
        status_text = status_map.get(status, status)
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        text = (
            f"<b>{mode} POZİSYON KAPANDI</b>\n"
            f"{status_text}\n"
            f"Coin: <b>{coin}/USDT</b>\n"
            f"PnL: {pnl_emoji} {format_usdt(pnl)} ({format_pct(pnl_pct)})"
        )
        self.send(text)

    def send_circuit_breaker(self, daily_pnl_pct: float) -> None:
        text = (
            f"⚠️ <b>CIRCUIT BREAKER DEVREYE GİRDİ</b>\n"
            f"Günlük PnL: {format_pct(daily_pnl_pct)}\n"
            f"Tüm işlemler durduruldu.\n"
            f"Gece yarısı UTC'de otomatik sıfırlanacak."
        )
        self.send(text)

    def send_daily_summary(self, stats: dict) -> None:
        win_rate = 0.0
        total = stats.get("total_trades", 0)
        if total > 0:
            win_rate = stats.get("winning_trades", 0) / total

        text = (
            f"📊 <b>GÜNLÜK ÖZET</b>\n"
            f"İşlem: {total} | Kar: {stats.get('winning_trades',0)} | Zarar: {stats.get('losing_trades',0)}\n"
            f"Kazanma Oranı: {win_rate*100:.1f}%\n"
            f"PnL: {format_usdt(stats.get('total_pnl_usdt',0))}\n"
            f"Max Drawdown: {format_pct(stats.get('max_drawdown_pct',0))}"
        )
        self.send(text)

    def send_alert(self, message: str) -> None:
        self.send(f"🔔 <b>UYARI</b>\n{message}")

    def send_heartbeat(self, portfolio_value: float, open_positions: int) -> None:
        text = (
            f"💚 Bot çalışıyor\n"
            f"Portföy: {format_usdt(portfolio_value)}\n"
            f"Açık Pozisyon: {open_positions}"
        )
        self.send(text)

    def send_portfolio_status(self) -> None:
        """Veritabanından portföy durumunu çekip Telegram'a gönderir."""
        from database.db import init_db, get_session
        from database.models import Trade, DailyStats
        from sqlalchemy import func

        try:
            init_db()
            with get_session() as session:
                # Açık pozisyonlar
                open_trades = session.query(Trade).filter(Trade.status == "OPEN").all()
                now_utc = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                lines = [f"🤖 <b>PORTFÖY DURUMU</b>  <i>{now_utc}</i>\n"]

                lines.append(f"📂 <b>Açık Pozisyonlar ({len(open_trades)})</b>")
                if not open_trades:
                    lines.append("  — Açık pozisyon yok")
                else:
                    total_margin = 0.0
                    for t in open_trades:
                        yön = "🟢 LONG" if t.direction == "long" else "🔴 SHORT"
                        dur = datetime.datetime.utcnow() - t.opened_at
                        h = int(dur.total_seconds() // 3600)
                        m = int((dur.total_seconds() % 3600) // 60)
                        current = self._fetch_price(t.coin)
                        price_line = ""
                        if current > 0 and t.entry_price > 0:
                            chg = (current - t.entry_price) / t.entry_price
                            if t.direction == "short":
                                chg = -chg
                            notional = t.margin_used * t.leverage
                            fee = notional * 0.002  # %0.10 giriş + %0.10 çıkış (taker fee)
                            unreal = chg * notional - fee
                            sign = "+" if unreal >= 0 else ""
                            price_line = (
                                f"\n  Anlık: <b>{format_usdt(current)}</b> "
                                f"({'+' if chg>=0 else ''}{chg*100:.2f}%)  "
                                f"Net PnL: <b>{sign}{format_usdt(unreal)}</b>"
                            )
                        lines.append(
                            f"  <b>{t.coin}</b> {yön} | Giriş: {format_usdt(t.entry_price)}"
                            f"{price_line}\n"
                            f"  SL: {format_usdt(t.stop_loss_price)} | TP: {format_usdt(t.take_profit_price or 0)}\n"
                            f"  Margin: {format_usdt(t.margin_used)} | Skor: {t.combined_score:.2f} | {h}s {m}dk"
                        )
                        total_margin += t.margin_used
                    lines.append(f"  Kullanılan margin: <b>{format_usdt(total_margin)}</b>")

                # Bugünkü istatistikler
                today = datetime.date.today().isoformat()
                stats = session.query(DailyStats).filter_by(date=today).first()
                lines.append(f"\n📊 <b>Bugün ({today})</b>")
                if not stats or not stats.total_trades:
                    lines.append("  — Henüz kapalı işlem yok")
                else:
                    total = stats.total_trades
                    wr = (stats.winning_trades / total * 100) if total else 0
                    pnl = stats.total_pnl_usdt or 0.0
                    pnl_sign = "+" if pnl >= 0 else ""
                    cb = "🔴 Ateşlendi" if stats.circuit_breaker_fired else "🟢 Aktif"
                    lines.append(
                        f"  İşlem: {total} | ✅ {stats.winning_trades} / ❌ {stats.losing_trades}\n"
                        f"  Kazanma: {wr:.1f}% | PnL: <b>{pnl_sign}{format_usdt(pnl)}</b>\n"
                        f"  Circuit Breaker: {cb}"
                    )

                # Tüm zamanlar
                closed = session.query(Trade).filter(Trade.status != "OPEN")
                total_all = closed.count()
                wins_all = closed.filter(Trade.pnl_usdt > 0).count()
                total_pnl_all = session.query(func.sum(Trade.pnl_usdt)).filter(Trade.status != "OPEN").scalar() or 0.0
                wr_all = (wins_all / total_all * 100) if total_all else 0
                pnl_sign = "+" if total_pnl_all >= 0 else ""
                lines.append(
                    f"\n📈 <b>Tüm Zamanlar</b>\n"
                    f"  Kapalı: {total_all} | Kazanma: {wr_all:.1f}%\n"
                    f"  Toplam PnL: <b>{pnl_sign}{format_usdt(total_pnl_all)}</b>"
                )

                self.send("\n".join(lines))
        except Exception as e:
            logger.warning("Portföy durumu gönderilemedi", error=str(e))
            self.send(f"❌ Portföy durumu alınamadı: {e}")

    def set_command_handler(self, handler) -> None:
        """Bot engine'den komut callback'i kaydeder."""
        self._command_handler = handler

    async def start_command_listener(self) -> None:
        """
        Telegram komutlarını dinler. Desteklenen komutlar:
          /durum        — portföy durumu
          /kapat <COIN> — belirtilen coini kapat (ör: /kapat ETH)
          /hepsiniKapat — tüm açık pozisyonları kapat
          /durdur       — yeni işlem açmayı durdur
          /baslat       — yeni işlem açmaya izin ver
          /yardim       — komut listesi
        """
        if not self._enabled:
            return

        offset = 0
        self._command_handler = getattr(self, "_command_handler", None)
        logger.info("Telegram komut dinleyici başlatıldı")

        HELP_TEXT = (
            "🤖 <b>Kullanılabilir Komutlar</b>\n\n"
            "/durum — Portföy durumu\n"
            "/bakiye — OKX bakiyesi\n"
            "/kapat ETH — ETH pozisyonunu kapat\n"
            "/hepsiniKapat — Tüm pozisyonları kapat\n"
            "/durdur — Yeni işlem açmayı durdur\n"
            "/baslat — Yeni işlem açmaya izin ver\n"
            "/yardim — Bu listeyi göster"
        )

        while True:
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.get(
                        f"{self._base_url}/getUpdates",
                        params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                    )
                    data = resp.json()

                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    raw = msg.get("text", "").strip()
                    cmd = raw.split("@")[0].lower()  # /kapat@botname → /kapat

                    if cmd in ("/durum", "/status"):
                        logger.info("Telegram /durum komutu")
                        self.send_portfolio_status()

                    elif cmd == "/bakiye":
                        logger.info("Telegram /bakiye komutu")
                        if self._command_handler:
                            await self._command_handler("bakiye")

                    elif cmd.startswith("/kapat "):
                        coin = raw.split(" ", 1)[1].upper().strip()
                        logger.info("Telegram /kapat komutu", coin=coin)
                        if self._command_handler:
                            await self._command_handler("kapat", coin=coin)
                        else:
                            self.send(f"⚠️ Komut işleyici hazır değil.")

                    elif cmd == "/hepsiniKapat".lower():
                        logger.info("Telegram /hepsiniKapat komutu")
                        if self._command_handler:
                            await self._command_handler("hepsiniKapat")
                        else:
                            self.send("⚠️ Komut işleyici hazır değil.")

                    elif cmd == "/durdur":
                        logger.info("Telegram /durdur komutu")
                        if self._command_handler:
                            await self._command_handler("durdur")

                    elif cmd == "/baslat":
                        logger.info("Telegram /baslat komutu")
                        if self._command_handler:
                            await self._command_handler("baslat")

                    elif cmd in ("/yardim", "/help", "/start"):
                        self.send(HELP_TEXT)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Telegram polling hatası", error=str(e))
                await asyncio.sleep(10)

    def _fetch_price(self, coin: str) -> float:
        """OKX public API'den anlık fiyat çeker (auth gerekmez)."""
        try:
            inst_id = f"{coin}-USDT-SWAP"
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}")
                data = r.json().get("data", [])
                if data:
                    return float(data[0]["last"])
        except Exception:
            pass
        return 0.0

    def _bot_username(self) -> str:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/getMe")
                return resp.json().get("result", {}).get("username", "")
        except Exception:
            return ""
