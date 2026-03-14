/**
 * Global WebSocket sync — /ws/live mesajlarını React Query cache'ine yazar.
 * Tüm sayfalarda polling'i azaltır, veriler 3 saniyede bir güncellenir.
 */
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getApiKey } from '../lib/api'

export default function WsSync() {
  const qc = useQueryClient()

  useEffect(() => {
    const key = getApiKey()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/live?token=${key}`
    let stopped = false
    let ws: WebSocket

    function connect() {
      if (stopped) return
      ws = new WebSocket(url)
      ws.onclose = () => { if (!stopped) setTimeout(connect, 3000) }
      ws.onerror  = () => {}
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type !== 'live') return

          // ── Pozisyonlar ─────────────────────────────────────────────────
          if (Array.isArray(msg.positions)) {
            qc.setQueryData(['positions'], {
              positions: msg.positions,
              count: msg.positions.length,
            })
          }

          // ── Dashboard KPI'ları (mevcut veri korunur, sadece canlı alanlar güncellenir) ─
          qc.setQueryData(['dashboard'], (old: any) => {
            if (!old) return old
            return {
              ...old,
              portfolio_value:      msg.portfolio_value     ?? old.portfolio_value,
              daily_pnl:            msg.daily_pnl           ?? old.daily_pnl,
              daily_trades:         msg.daily_trades        ?? old.daily_trades,
              fear_greed_index:     msg.fear_greed_index    ?? old.fear_greed_index,
              btc_regime:           msg.btc_regime          ?? old.btc_regime,
              open_positions:       msg.positions           ?? old.open_positions,
              open_positions_count: msg.positions?.length   ?? old.open_positions_count,
            }
          })

          // ── Tarayıcı genel bakış (60s'de bir değişir) ───────────────────
          if (msg.overview?.coins?.length) {
            qc.setQueryData(['signals-overview'], msg.overview)
          }
        } catch {}
      }
    }

    connect()
    return () => {
      stopped = true
      ws?.close()
    }
  }, [qc])

  return null
}
