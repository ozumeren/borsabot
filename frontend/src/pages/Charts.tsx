import { useState } from 'react'
import TradingViewChart from '../components/TradingViewChart'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
const QUICK_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX', 'LINK', 'DOT']

export default function Charts() {
  const [coin, setCoin] = useState('BTC')
  const [inputVal, setInputVal] = useState('BTC')
  const [timeframe, setTimeframe] = useState('15m')

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const c = inputVal.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (c) setCoin(c)
  }

  return (
    <div className="space-y-4">
      {/* Kontroller */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-text font-semibold">Fiyat Grafikleri</h1>

        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <input
            value={inputVal}
            onChange={e => setInputVal(e.target.value.toUpperCase())}
            placeholder="BTC, ETH..."
            className="bg-card border border-border rounded px-3 py-1 text-sm text-text font-mono w-24 focus:outline-none focus:border-accent/60"
          />
          <button type="submit" className="btn-accent text-xs px-3 py-1">Ara</button>
        </form>

        {/* Timeframe */}
        <div className="flex gap-1">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2 py-1 rounded text-xs font-mono transition-colors ${
                tf === timeframe
                  ? 'bg-accent/15 text-accent border border-accent/30'
                  : 'text-muted hover:text-text hover:bg-white/5'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Hızlı coin seçimi */}
      <div className="flex flex-wrap gap-1.5">
        {QUICK_COINS.map(c => (
          <button
            key={c}
            onClick={() => { setCoin(c); setInputVal(c) }}
            className={`px-2.5 py-1 rounded text-xs font-mono border transition-colors ${
              c === coin
                ? 'bg-accent/10 text-accent border-accent/30'
                : 'bg-card text-muted border-border hover:text-text'
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {/* TradingView Chart */}
      <div className="card p-0 overflow-hidden">
        <TradingViewChart key={`${coin}-${timeframe}`} coin={coin} timeframe={timeframe} height={560} />
      </div>

      <p className="text-muted text-xs">
        Kaynak: TradingView — Binance Perpetuals · Çizim araçları aktif
      </p>
    </div>
  )
}
