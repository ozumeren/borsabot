import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSignalOverview, fetchFullScan } from '../lib/api'

interface CoinRow {
  coin: string
  price: number
  change_pct: number
  rsi: number
  score: number
  combined_score?: number
  direction: string
  macd_bullish: boolean
  status: 'entry' | 'watch' | 'neutral' | 'avoid'
  reasons: string[]
}

interface OverviewData {
  coins: CoinRow[]
  btc_regime: string
  updated_at: string | null
}

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  entry:   { label: 'GİRİŞ',    cls: 'text-accent border-accent/40 bg-accent/10' },
  watch:   { label: 'İZLE',     cls: 'text-warn border-warn/40 bg-warn/10' },
  neutral: { label: '—',        cls: 'text-muted border-border' },
  avoid:   { label: 'UZAK DUR', cls: 'text-danger border-danger/40 bg-danger/10' },
}

function scoreColor(score: number): string {
  if (score >= 0.62) return '#00ff88'
  if (score >= 0.54) return '#66ffaa'
  if (score >= 0.46) return '#ffaa00'
  if (score >= 0.38) return '#ff8844'
  return '#ff3333'
}

function scoreBar(score: number) {
  const pct = Math.round(score * 100)
  const color = scoreColor(score)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 56,
        height: 4,
        background: '#1e1e1e',
        borderRadius: 2,
        overflow: 'hidden',
      }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: 'monospace', fontSize: 11, color }}>{pct}%</span>
    </div>
  )
}

export default function Scanner() {
  const [fullScanData, setFullScanData] = useState<CoinRow[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [showFull, setShowFull] = useState(false)

  const { data, dataUpdatedAt } = useQuery<OverviewData>({
    queryKey: ['signals-overview'],
    queryFn: fetchSignalOverview,
    refetchInterval: 30_000,
    staleTime: 25_000,
  })

  const regime = data?.btc_regime ?? 'neutral'
  const regimeLabel = regime === 'bull' ? 'BOĞA' : regime === 'bear' ? 'AYI' : 'NÖTR'
  const regimeClass = regime === 'bull' ? 'text-accent border-accent/30' : regime === 'bear' ? 'text-danger border-danger/30' : 'text-warn border-warn/30'

  const lastUpdate = data?.updated_at
    ? new Date(data.updated_at).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  async function handleFullScan() {
    setScanning(true)
    setShowFull(true)
    try {
      const res = await fetchFullScan()
      setFullScanData(res.coins ?? [])
    } finally {
      setScanning(false)
    }
  }

  const displayCoins: CoinRow[] = showFull ? (fullScanData ?? []) : (data?.coins ?? [])

  return (
    <div className="space-y-4">
      {/* Başlık */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-text font-semibold">Piyasa Tarayıcı</h1>
          <span className={`text-xs font-mono px-2 py-0.5 rounded border ${regimeClass}`}>
            BTC {regimeLabel}
          </span>
          {lastUpdate && (
            <span className="text-muted text-xs font-mono">Son: {lastUpdate}</span>
          )}
          {!showFull && (
            <span className="text-muted text-xs">Otomatik güncelleme — 30s</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {showFull && (
            <button className="btn-muted text-xs" onClick={() => { setShowFull(false); setFullScanData(null) }}>
              ← İlk 20
            </button>
          )}
          <button
            className="btn-accent text-xs"
            onClick={handleFullScan}
            disabled={scanning}
          >
            {scanning ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
                Taranıyor...
              </span>
            ) : '⟳ Tüm Piyasayı Tara'}
          </button>
        </div>
      </div>

      {/* Renk skalası */}
      <div className="flex items-center gap-2 text-xs text-muted font-mono">
        <span>Zayıf</span>
        <div style={{
          width: 120,
          height: 6,
          borderRadius: 3,
          background: 'linear-gradient(to right, #ff3333, #ff8844, #ffaa00, #66ffaa, #00ff88)',
        }} />
        <span>Güçlü</span>
        <div className="ml-4 flex items-center gap-3">
          {Object.entries(STATUS_STYLE).map(([k, v]) => (
            <span key={k} className={`px-1.5 py-0.5 rounded border text-xs ${v.cls}`}>{v.label}</span>
          ))}
        </div>
      </div>

      {/* Tablo */}
      <div className="card overflow-x-auto p-0">
        {displayCoins.length === 0 ? (
          <div className="text-muted text-sm py-16 text-center">
            {scanning ? 'Taranıyor...' : showFull ? 'Sonuç bulunamadı' : 'Yükleniyor...'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border bg-card">
                <th className="text-left py-2.5 px-4">#</th>
                <th className="text-left py-2.5 px-4">Coin</th>
                <th className="text-right py-2.5 px-4">Fiyat</th>
                <th className="text-right py-2.5 px-4">24s %</th>
                <th className="text-right py-2.5 px-4">RSI</th>
                <th className="text-left py-2.5 px-4">Skor</th>
                <th className="text-left py-2.5 px-4">Yön</th>
                <th className="text-left py-2.5 px-4">Kombine</th>
                <th className="text-left py-2.5 px-4">Durum</th>
                <th className="text-left py-2.5 px-4">Nedenler</th>
              </tr>
            </thead>
            <tbody>
              {displayCoins.map((coin, i) => {
                const st = STATUS_STYLE[coin.status] ?? STATUS_STYLE.neutral
                const isLong = coin.direction.includes('LONG')
                const isShort = coin.direction.includes('SHORT')
                const rowBg = coin.status === 'entry'
                  ? 'bg-accent/3'
                  : coin.status === 'avoid'
                  ? 'bg-danger/3'
                  : ''

                return (
                  <tr key={coin.coin} className={`border-b border-border/50 hover:bg-white/3 transition-colors ${rowBg}`}>
                    <td className="py-2.5 px-4 text-muted text-xs font-mono">{i + 1}</td>
                    <td className="py-2.5 px-4">
                      <span className="text-text font-bold font-mono">{coin.coin}</span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-xs text-text">
                      ${coin.price < 1
                        ? coin.price.toFixed(4)
                        : coin.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className={`py-2.5 px-4 text-right font-mono text-xs ${(coin.change_pct ?? 0) >= 0 ? 'text-accent' : 'text-danger'}`}>
                      {(coin.change_pct ?? 0) >= 0 ? '+' : ''}{(coin.change_pct ?? 0).toFixed(2)}%
                    </td>
                    <td className={`py-2.5 px-4 text-right font-mono text-xs ${
                      coin.rsi > 70 ? 'text-danger' : coin.rsi < 30 ? 'text-accent' : 'text-text'
                    }`}>
                      {coin.rsi.toFixed(1)}
                      {coin.rsi > 70 && <span className="ml-1 text-danger text-xs">↑</span>}
                      {coin.rsi < 30 && <span className="ml-1 text-accent text-xs">↓</span>}
                    </td>
                    <td className="py-2.5 px-4">{scoreBar(coin.score)}</td>
                    <td className="py-2.5 px-4">
                      {isLong && <span className="text-accent text-xs font-mono font-bold">LONG ▲</span>}
                      {isShort && <span className="text-danger text-xs font-mono font-bold">SHORT ▼</span>}
                      {!isLong && !isShort && <span className="text-muted text-xs">—</span>}
                    </td>
                    <td className="py-2.5 px-4">
                      {scoreBar(coin.combined_score ?? coin.score)}
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={`text-xs font-mono px-2 py-0.5 rounded border ${st.cls}`}>
                        {st.label}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-xs text-muted max-w-48 truncate">
                      {coin.reasons.join(', ') || '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
