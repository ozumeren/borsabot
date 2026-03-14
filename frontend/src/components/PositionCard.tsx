import { closePosition } from '../lib/api'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import PositionChart from './PositionChart'

interface Position {
  coin: string
  direction: string
  entry_price: number
  current_price?: number
  stop_loss_price: number
  take_profit_price?: number
  take_profit2_price?: number
  quantity: number
  margin_used: number
  leverage: number
  pnl_usdt?: number
  pnl_pct?: number
}

export default function PositionCard({ pos }: { pos: Position }) {
  const qc = useQueryClient()
  const [closing, setClosing] = useState(false)
  const [chartOpen, setChartOpen] = useState(false)

  const isLong = pos.direction === 'long'
  const marginUsed: number = (pos as any).margin_used ?? (pos as any).margin ?? 0
  const currentPrice = pos.current_price ?? pos.entry_price
  const notional = marginUsed * pos.leverage
  const pricePct = isLong
    ? (currentPrice - pos.entry_price) / pos.entry_price
    : (pos.entry_price - currentPrice) / pos.entry_price
  const pnlLive = pricePct * notional - notional * 0.002   // %0.2 giriş+çıkış ücreti

  const range = pos.take_profit_price && pos.stop_loss_price
    ? Math.abs(pos.take_profit_price - pos.stop_loss_price)
    : null
  const progress = range && pos.take_profit_price
    ? Math.max(0, Math.min(100, isLong
        ? ((currentPrice - pos.stop_loss_price) / range) * 100
        : ((pos.stop_loss_price - currentPrice) / range) * 100
      ))
    : null

  async function handleClose() {
    if (!confirm(`${pos.coin} pozisyonunu kapatmak istediğinize emin misiniz?`)) return
    setClosing(true)
    try {
      await closePosition(pos.coin)
      qc.invalidateQueries({ queryKey: ['positions'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    } finally {
      setClosing(false)
    }
  }

  return (
    <div className="card space-y-3 hover:border-accent/20 transition-colors">
      {/* Başlık */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-text font-bold">{pos.coin}</span>
          <span className={isLong ? 'badge-long' : 'badge-short'}>
            {isLong ? 'LONG' : 'SHORT'}
          </span>
          <span className="text-muted text-xs">{pos.leverage}x</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="text-muted hover:text-text text-xs transition-colors"
            onClick={() => setChartOpen(o => !o)}
            title="Grafik göster"
          >
            {chartOpen ? '▲ Grafik' : '▼ Grafik'}
          </button>
          <button className="btn-danger text-xs" onClick={handleClose} disabled={closing}>
            {closing ? '...' : 'KAPAT'}
          </button>
        </div>
      </div>

      {/* Fiyatlar */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-muted">Giriş</div>
          <div className="text-text font-mono">${pos.entry_price.toFixed(4)}</div>
        </div>
        <div>
          <div className="text-muted">Güncel</div>
          <div className={`font-mono ${isLong ? (currentPrice >= pos.entry_price ? 'text-accent' : 'text-danger') : (currentPrice <= pos.entry_price ? 'text-accent' : 'text-danger')}`}>
            ${currentPrice.toFixed(4)}
          </div>
        </div>
        <div>
          <div className="text-muted">K/Z</div>
          <div className={`font-mono ${pnlLive >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
            {pnlLive >= 0 ? '+' : ''}{pnlLive.toFixed(2)}$
          </div>
        </div>
      </div>

      {/* SL / TP seviyeleri */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-muted text-xs">Zarar Kes</div>
          <div className="text-danger font-mono">${pos.stop_loss_price.toFixed(4)}</div>
        </div>
        {pos.take_profit_price && pos.take_profit_price > 0 && (
          <div>
            <div className="text-muted text-xs">Kâr Al 1</div>
            <div className="text-accent font-mono">${pos.take_profit_price.toFixed(4)}</div>
          </div>
        )}
        {pos.take_profit2_price && pos.take_profit2_price > 0 && (
          <div>
            <div className="text-muted text-xs">Kâr Al 2</div>
            <div className="text-accent/70 font-mono">${pos.take_profit2_price.toFixed(4)}</div>
          </div>
        )}
      </div>

      {/* İlerleme çubuğu ZK → KA */}
      {progress !== null && (
        <div>
          <div className="h-1.5 bg-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${progress}%`,
                background: progress > 70 ? '#00ff88' : progress > 40 ? '#ffaa00' : '#ff3333',
              }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted mt-0.5">
            <span>ZK</span>
            <span>{progress.toFixed(0)}%</span>
            <span>KA</span>
          </div>
        </div>
      )}

      {/* Grafik (tıklanınca açılır) */}
      {chartOpen && pos.take_profit_price && pos.take_profit_price > 0 && (
        <PositionChart
          coin={pos.coin}
          direction={pos.direction}
          entryPrice={pos.entry_price}
          slPrice={pos.stop_loss_price}
          tpPrice={pos.take_profit_price}
          tp2Price={pos.take_profit2_price}
          height={260}
        />
      )}

      {/* Marjin */}
      <div className="text-xs text-muted">
        Marjin: <span className="text-text">{marginUsed.toFixed(2)}$</span>
        <span className="mx-2">·</span>
        Miktar: <span className="text-text">{pos.quantity.toFixed(4)}</span>
      </div>
    </div>
  )
}
