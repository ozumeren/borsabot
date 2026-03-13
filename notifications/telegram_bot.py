from __future__ import annotations
import asyncio
import datetime
import httpx
import os
from typing import Optional
from utils.logger import get_logger
from utils.helpers import format_usdt, format_pct

logger = get_logger("notifications.telegram")

_STATUS_ID_FILE = "/tmp/borsabot_status_msgid.txt"


class TelegramNotifier:
    """Telegram Bot API ile bildirim gönderir (sync wrapper)."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._enabled = bool(bot_token and chat_id)
        self._status_message_id: Optional[int] = self._load_status_id()

    def _load_status_id(self) -> Optional[int]:
        """Disk'ten son durum mesajı ID'sini yükler (restart'ta kaybolmasın)."""
        try:
            if os.path.exists(_STATUS_ID_FILE):
                val = open(_STATUS_ID_FILE).read().strip()
                return int(val) if val else None
        except Exception:
            pass
        return None

    def _save_status_id(self, message_id: int) -> None:
        try:
            open(_STATUS_ID_FILE, "w").write(str(message_id))
        except Exception:
            pass

    def send(self, text: str) -> Optional[int]:
        """Mesaj gönderir. Başarılıysa message_id döner, hata varsa None."""
        if not self._enabled:
            logger.debug("Telegram devre dışı (token/chat_id eksik)")
            return None
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
                return resp.json().get("result", {}).get("message_id")
        except Exception as e:
            logger.warning("Telegram gönderim hatası", error=str(e))
            return None

    def _edit_message(self, message_id: int, text: str) -> bool:
        """Var olan mesajı düzenler. 'not modified' hatasını sessizce geçer."""
        if not self._enabled:
            return False
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._base_url}/editMessageText",
                    json={
                        "chat_id": self.chat_id,
                        "message_id": message_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code == 400 and "not modified" in resp.text:
                    return True  # içerik aynı, sorun değil
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning("Telegram edit hatası", message_id=message_id, error=str(e))
            return False

    def send_trade_opened(self, pos, is_paper: bool = False) -> None:
        mode = "[PAPER]" if is_paper else "[CANLI]"
        direction_emoji = "🟢 LONG" if pos.direction == "long" else "🔴 SHORT"
        margin = getattr(pos, "margin", None) or getattr(pos, "margin_used", 0.0)
        reasons = getattr(pos, "signal_reasons", [])
        reasons_text = ""
        if reasons:
            bullet = "\n".join(f"  • {r}" for r in reasons)
            reasons_text = f"\n\n<b>Neden açıldı?</b>\n{bullet}"
        text = (
            f"<b>{mode} YENİ POZİSYON</b>\n"
            f"Coin: <b>{pos.coin}/USDT</b>\n"
            f"Yön: {direction_emoji} ({pos.leverage}x)\n"
            f"Giriş: {format_usdt(pos.entry_price)}\n"
            f"Hedef: {format_usdt(pos.take_profit_price)}\n"
            f"Stop-Loss: {format_usdt(pos.stop_loss_price)}\n"
            f"Teminat: {format_usdt(margin)}"
            f"{reasons_text}"
        )
        self.send(text)

    def send_trade_closed(
        self,
        coin: str,
        status: str,
        pnl: float,
        pnl_pct: float,
        is_paper: bool = False,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
    ) -> None:
        mode = "[PAPER]" if is_paper else "[CANLI]"
        status_map = {
            "CLOSED_TP": "✅ Hedef fiyata ulaştı (Take Profit)",
            "CLOSED_SL": "❌ Stop loss tetiklendi",
            "CLOSED_CIRCUIT": "⚠️ Acil kapama — likidayon/günlük limit riski",
            "CLOSED_MANUAL": "🔵 Manuel kapatma (/kapat komutu)",
        }
        status_text = status_map.get(status, status)
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        price_line = ""
        if entry_price > 0 and exit_price > 0:
            chg = (exit_price - entry_price) / entry_price * 100
            price_line = (
                f"\nGiriş: {format_usdt(entry_price)} → Çıkış: {format_usdt(exit_price)}"
                f" ({'+' if chg >= 0 else ''}{chg:.2f}%)"
            )
        text = (
            f"<b>{mode} POZİSYON KAPANDI</b>\n"
            f"Coin: <b>{coin}/USDT</b>\n"
            f"{status_text}"
            f"{price_line}\n"
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

    def send_partial_tp(
        self,
        coin: str,
        tp1_price: float,
        pnl: float,
        pnl_pct: float,
        tp2_price: float,
        is_paper: bool = False,
    ) -> None:
        mode = "[PAPER]" if is_paper else "[CANLI]"
        sign = "+" if pnl >= 0 else ""
        text = (
            f"✅ <b>{mode} TP1 — %50 Pozisyon Kapatıldı</b>\n"
            f"Coin: <b>{coin}/USDT</b>\n"
            f"Fiyat: {format_usdt(tp1_price)}\n"
            f"PnL (½ pozisyon): 📈 {sign}{format_usdt(pnl)} ({format_pct(pnl_pct)})\n"
            f"SL → Giriş fiyatına çekildi (breakeven)\n"
            f"Kalan ½ → TP2 hedef: <b>{format_usdt(tp2_price)}</b>"
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

    def _build_status_text(self) -> str:
        """Portföy durum metnini oluşturur."""
        from database.db import init_db, get_session
        from database.models import Trade, DailyStats
        from sqlalchemy import func

        init_db()
        with get_session() as session:
            open_trades = session.query(Trade).filter(Trade.status == "OPEN").all()
            now_cet = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            now_utc = now_cet.strftime("%Y-%m-%d %H:%M CET")
            lines = [f"🤖 <b>PORTFÖY DURUMU</b>  <i>{now_utc}</i>\n"]

            lines.append(f"📂 <b>Açık Pozisyonlar ({len(open_trades)})</b>")
            if not open_trades:
                lines.append("  — Açık pozisyon yok")
            else:
                total_margin = 0.0
                total_unrealized = 0.0
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
                        fee = notional * 0.002
                        unreal = chg * notional - fee
                        total_unrealized += unreal
                        sign = "+" if unreal >= 0 else ""
                        price_line = (
                            f"\n  Anlık: <b>{format_usdt(current)}</b> "
                            f"({'+' if chg>=0 else ''}{chg*100:.2f}%)  "
                            f"Gerçekleşmemiş: <b>{sign}{format_usdt(unreal)}</b>"
                        )
                    notional_display = t.margin_used * t.leverage
                    lines.append(
                        f"  <b>{t.coin}</b> {yön} {t.leverage}x | Giriş: {format_usdt(t.entry_price)}"
                        f"{price_line}\n"
                        f"  SL: {format_usdt(t.stop_loss_price)} | TP: {format_usdt(t.take_profit_price or 0)}\n"
                        f"  Teminat: {format_usdt(t.margin_used)} | Hacim: {format_usdt(notional_display)} | Skor: {t.combined_score:.2f} | {h}s {m}dk"
                    )
                    total_margin += t.margin_used
                unreal_sign = "+" if total_unrealized >= 0 else ""
                unreal_emoji = "📈" if total_unrealized >= 0 else "📉"
                lines.append(
                    f"  Kullanılan margin: <b>{format_usdt(total_margin)}</b>\n"
                    f"  {unreal_emoji} Toplam Gerçekleşmemiş PnL: <b>{unreal_sign}{format_usdt(total_unrealized)}</b>"
                )

            today = datetime.date.today().isoformat()
            stats = session.query(DailyStats).filter_by(date=today).first()

            # Bugünkü realize edilmiş PnL'i Trade tablosundan da çek (DailyStats yoksa bile)
            today_dt = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_realized = session.query(func.sum(Trade.pnl_usdt)).filter(
                Trade.status != "OPEN",
                Trade.closed_at >= today_dt,
            ).scalar() or 0.0
            today_trade_count = session.query(Trade).filter(
                Trade.status != "OPEN",
                Trade.closed_at >= today_dt,
            ).count()
            today_wins = session.query(Trade).filter(
                Trade.status != "OPEN",
                Trade.closed_at >= today_dt,
                Trade.pnl_usdt > 0,
            ).count()
            today_losses = today_trade_count - today_wins

            lines.append(f"\n📊 <b>Bugün ({today})</b>")
            if not today_trade_count:
                lines.append("  — Henüz kapalı işlem yok")
            else:
                wr = (today_wins / today_trade_count * 100) if today_trade_count else 0
                real_sign = "+" if today_realized >= 0 else ""
                real_emoji = "📈" if today_realized >= 0 else "📉"
                cb = "🔴 Ateşlendi" if (stats and stats.circuit_breaker_fired) else "🟢 Aktif"
                lines.append(
                    f"  İşlem: {today_trade_count} | ✅ {today_wins} / ❌ {today_losses}\n"
                    f"  Kazanma: {wr:.1f}%\n"
                    f"  {real_emoji} Realize PnL: <b>{real_sign}{format_usdt(today_realized)}</b>\n"
                    f"  Circuit Breaker: {cb}"
                )

            closed = session.query(Trade).filter(Trade.status != "OPEN")
            total_all = closed.count()
            wins_all = closed.filter(Trade.pnl_usdt > 0).count()
            total_pnl_all = session.query(func.sum(Trade.pnl_usdt)).filter(Trade.status != "OPEN").scalar() or 0.0
            wr_all = (wins_all / total_all * 100) if total_all else 0
            pnl_sign = "+" if total_pnl_all >= 0 else ""
            pnl_emoji = "📈" if total_pnl_all >= 0 else "📉"
            lines.append(
                f"\n📈 <b>Tüm Zamanlar</b>\n"
                f"  Kapalı: {total_all} | Kazanma: {wr_all:.1f}%\n"
                f"  {pnl_emoji} Toplam Realize PnL: <b>{pnl_sign}{format_usdt(total_pnl_all)}</b>"
            )

        return "\n".join(lines)

    def send_portfolio_status(self) -> None:
        """/durum komutu: yeni mesaj gönderir, message_id'yi saklar."""
        try:
            text = self._build_status_text()
            msg_id = self.send(text)
            if msg_id:
                self._status_message_id = msg_id
                self._save_status_id(msg_id)
                logger.info("Durum mesajı gönderildi", message_id=msg_id)
        except Exception as e:
            logger.warning("Portföy durumu gönderilemedi", error=str(e))
            self.send(f"❌ Portföy durumu alınamadı: {e}")

    def update_portfolio_status(self) -> None:
        """Otomatik güncelleme: son durum mesajını düzenler, yoksa yeni gönderir."""
        try:
            text = self._build_status_text()
            if self._status_message_id:
                success = self._edit_message(self._status_message_id, text)
                if not success:
                    # Edit başarısız (mesaj silinmiş olabilir) → yeni mesaj gönder
                    logger.info("Edit başarısız, yeni durum mesajı gönderiliyor")
                    msg_id = self.send(text)
                    if msg_id:
                        self._status_message_id = msg_id
                        self._save_status_id(msg_id)
                else:
                    logger.debug("Durum mesajı güncellendi", message_id=self._status_message_id)
            else:
                msg_id = self.send(text)
                if msg_id:
                    self._status_message_id = msg_id
                    self._save_status_id(msg_id)
                    logger.info("İlk durum mesajı gönderildi", message_id=msg_id)
        except Exception as e:
            logger.warning("Durum güncellemesi başarısız", error=str(e))

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
            "/tara — Piyasayı tara, en iyi 5 fırsatı listele\n"
            "/ac BTC — BTC için analiz yap ve pozisyon aç\n"
            "/kapat ETH — ETH pozisyonunu kapat\n"
            "/hepsiniKapat — Tüm pozisyonları kapat\n"
            "/durdur — Yeni işlem açmayı durdur\n"
            "/baslat — Yeni işlem açmaya izin ver\n"
            "/yardim — Bu listeyi göster"
        )

        while True:
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.get(
                        f"{self._base_url}/getUpdates",
                        params={"offset": offset, "timeout": 10, "allowed_updates": ["message"]},
                    )
                    data = resp.json()

                if not data.get("ok"):
                    await asyncio.sleep(2)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    raw = msg.get("text", "").strip()
                    cmd = raw.split("@")[0].lower()

                    # Her komutu ayrı task olarak çalıştır — polling loop bloke olmasın
                    if cmd in ("/durum", "/status"):
                        logger.info("Telegram /durum komutu")
                        asyncio.create_task(asyncio.to_thread(self.send_portfolio_status))

                    elif cmd == "/tara":
                        logger.info("Telegram /tara komutu")
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("tara"))

                    elif cmd.startswith("/ac"):
                        parts = raw.split()
                        if len(parts) >= 2:
                            coin = parts[1].upper().replace("USDT", "").strip()
                            logger.info("Telegram /ac komutu", coin=coin)
                            if self._command_handler:
                                asyncio.create_task(self._command_handler("ac", coin=coin))
                        else:
                            self.send("⚠️ Kullanım: /ac BTC")

                    elif cmd == "/bakiye":
                        logger.info("Telegram /bakiye komutu")
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("bakiye"))

                    elif cmd.startswith("/kapat "):
                        coin = raw.split(" ", 1)[1].upper().strip()
                        logger.info("Telegram /kapat komutu", coin=coin)
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("kapat", coin=coin))
                        else:
                            self.send("⚠️ Komut işleyici hazır değil.")

                    elif cmd == "/hepsiniKapat".lower():
                        logger.info("Telegram /hepsiniKapat komutu")
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("hepsiniKapat"))
                        else:
                            self.send("⚠️ Komut işleyici hazır değil.")

                    elif cmd == "/durdur":
                        logger.info("Telegram /durdur komutu")
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("durdur"))

                    elif cmd == "/baslat":
                        logger.info("Telegram /baslat komutu")
                        if self._command_handler:
                            asyncio.create_task(self._command_handler("baslat"))

                    elif cmd in ("/yardim", "/help", "/start"):
                        asyncio.create_task(asyncio.to_thread(self.send, HELP_TEXT))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Telegram polling hatası", error=str(e))
                await asyncio.sleep(2)

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
