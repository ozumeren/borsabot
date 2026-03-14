import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchCoinDetail, refreshCoinDetail, fetchPositions } from '../lib/api'
import TradingViewChart from '../components/TradingViewChart'
import PositionChart from '../components/PositionChart'

interface TFData {
  label: string
  error?: string
  rsi?: number
  macd_hist?: number
  macd_bullish?: boolean
  bb_pct?: number
  bb_width_pct?: number
  adx?: number
  atr_pct?: number
  obv_slope?: number
  ema_cross?: string
  above_sma200?: boolean
  trend?: string
  pa_bull_score?: number
  pa_bear_score?: number
  pa_pattern?: string
  score?: number
  direction?: string
  reasons?: string[]
}

interface ScoreBreakdown {
  technical: { label: string; weight: number; value: number; contribution: number }
  sentiment: { label: string; weight: number; value: number; contribution: number }
  market:    { label: string; weight: number; value: number; contribution: number }
  fear_greed_index: number
  funding_rate: number | null
}

interface BotScores {
  long_combined:  number
  short_combined: number
  long_tech:      number
  short_tech:     number
  threshold:      number
  long_eligible:  boolean
  short_eligible: boolean
}

interface CoinData {
  coin: string
  last_price: number
  direction: string
  cached_at: string
  expires_at: string
  combined_score: number
  technical_score: number
  sentiment_score: number
  market_score: number
  score_breakdown: ScoreBreakdown
  bot_scores?: BotScores
  timeframes: Record<string, TFData>
  reasons: string[]
}

const TF_TIMEFRAME: Record<string, string> = {
  '1h': '1h', '1d': '1d', '1w': '1w', '1M': '1M',
}

function scoreColor(v: number) {
  if (v >= 0.62) return '#00ff88'
  if (v >= 0.54) return '#66ffaa'
  if (v >= 0.46) return '#ffaa00'
  if (v >= 0.38) return '#ff8844'
  return '#ff3333'
}

function ScoreBar({ value, max = 1, color }: { value: number; max?: number; color?: string }) {
  const pct = Math.min(100, (value / max) * 100)
  const c = color ?? scoreColor(value)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 5, background: '#1e1e1e', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: c, borderRadius: 3 }} />
      </div>
      <span style={{ fontFamily: 'monospace', fontSize: 12, color: c, minWidth: 36, textAlign: 'right' }}>
        {Math.round(pct)}%
      </span>
    </div>
  )
}

function RsiGauge({ rsi }: { rsi: number }) {
  const pct = rsi
  const color = rsi > 70 ? '#ff3333' : rsi < 30 ? '#00ff88' : '#ffaa00'
  const label = rsi > 70 ? 'Aşırı Alım' : rsi < 30 ? 'Aşırı Satım' : 'Nötr'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted font-mono">
        <span>30</span><span>RSI {rsi.toFixed(1)}</span><span>70</span>
      </div>
      <div style={{ position: 'relative', height: 8, background: '#1e1e1e', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', left: 0, width: '30%', height: '100%',
          background: 'linear-gradient(to right, #00ff8833, #00ff8811)',
        }} />
        <div style={{
          position: 'absolute', right: 0, width: '30%', height: '100%',
          background: 'linear-gradient(to left, #ff333333, #ff333311)',
        }} />
        <div style={{
          position: 'absolute', top: 0, bottom: 0, width: 3, borderRadius: 2,
          background: color, left: `calc(${pct}% - 1.5px)`, transition: 'left 0.5s',
        }} />
      </div>
      <div className="text-center text-xs font-mono" style={{ color }}>{label}</div>
    </div>
  )
}

function TrendBadge({ trend }: { trend?: string }) {
  if (!trend || trend === 'UNKNOWN') return <span className="text-muted text-xs">—</span>
  const map: Record<string, { label: string; cls: string }> = {
    UPTREND:   { label: '↑ YUKARI', cls: 'text-accent border-accent/30 bg-accent/5' },
    DOWNTREND: { label: '↓ AŞAĞI',  cls: 'text-danger border-danger/30 bg-danger/5' },
    RANGING:   { label: '↔ YATAY',  cls: 'text-warn border-warn/30 bg-warn/5' },
  }
  const s = map[trend] ?? { label: trend, cls: 'text-muted border-border' }
  return <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${s.cls}`}>{s.label}</span>
}

function TimeframeCard({ tfKey, tf }: { tfKey: string; tf: TFData }) {
  if (tf.error) return (
    <div className="card flex items-center justify-center text-muted text-xs py-6">{tf.error}</div>
  )
  const isLong  = tf.direction?.includes('LONG')
  const isShort = tf.direction?.includes('SHORT')
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-text font-bold font-mono">{tf.label}</span>
        <div className="flex items-center gap-2">
          {isLong  && <span className="badge-long text-xs">LONG ▲</span>}
          {isShort && <span className="badge-short text-xs">SHORT ▼</span>}
          {!isLong && !isShort && <span className="text-muted text-xs font-mono">NÖTR</span>}
        </div>
      </div>

      {tf.rsi != null && <RsiGauge rsi={tf.rsi} />}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <div className="text-muted mb-1">Teknik Skor</div>
          <ScoreBar value={tf.score ?? 0} />
        </div>
        <div>
          <div className="text-muted mb-1">Trend</div>
          <TrendBadge trend={tf.trend} />
        </div>
        <div>
          <div className="text-muted mb-0.5">MACD</div>
          <span className={`font-mono ${tf.macd_bullish ? 'text-accent' : 'text-danger'}`}>
            {tf.macd_bullish ? '▲ Pozitif' : '▼ Negatif'}
          </span>
        </div>
        <div>
          <div className="text-muted mb-0.5">EMA Çapraz</div>
          <span className={`font-mono ${tf.ema_cross === 'bullish' ? 'text-accent' : 'text-danger'}`}>
            {tf.ema_cross === 'bullish' ? '▲ Yükseliş' : '▼ Düşüş'}
          </span>
        </div>
        <div>
          <div className="text-muted mb-0.5">ADX</div>
          <span className={`font-mono ${(tf.adx ?? 0) >= 40 ? 'text-accent' : (tf.adx ?? 0) >= 20 ? 'text-warn' : 'text-muted'}`}>
            {tf.adx?.toFixed(1) ?? '—'} {(tf.adx ?? 0) >= 40 ? '(Güçlü)' : (tf.adx ?? 0) >= 20 ? '(Trend)' : '(Zayıf)'}
          </span>
        </div>
        <div>
          <div className="text-muted mb-0.5">SMA200 Üzeri</div>
          <span className={`font-mono ${tf.above_sma200 ? 'text-accent' : 'text-danger'}`}>
            {tf.above_sma200 ? '✓ Evet' : '✗ Hayır'}
          </span>
        </div>
        {tf.pa_pattern && (
          <div className="col-span-2">
            <div className="text-muted mb-0.5">PA Formasyonu</div>
            <span className="font-mono text-warn">{tf.pa_pattern}</span>
            <span className="text-muted ml-2">
              ▲{Math.round((tf.pa_bull_score ?? 0) * 100)}% ▼{Math.round((tf.pa_bear_score ?? 0) * 100)}%
            </span>
          </div>
        )}
        <div>
          <div className="text-muted mb-0.5">BB Genişliği</div>
          <span className="font-mono text-text">{tf.bb_width_pct?.toFixed(1) ?? '—'}%</span>
        </div>
        <div>
          <div className="text-muted mb-0.5">ATR</div>
          <span className="font-mono text-text">{tf.atr_pct?.toFixed(2) ?? '—'}%</span>
        </div>
      </div>

      {tf.reasons && tf.reasons.length > 0 && (
        <div>
          <div className="text-muted text-xs mb-1">Nedenler</div>
          <ul className="space-y-0.5">
            {tf.reasons.map((r, i) => (
              <li key={i} className="text-xs text-text font-mono flex gap-1.5">
                <span className="text-muted shrink-0">›</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

const TF_ORDER = ['1h', '1d', '1w', '1M']

export default function CoinDetail() {
  const { symbol } = useParams<{ symbol: string }>()
  const coin = (symbol ?? '').toUpperCase()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const [activeTf, setActiveTf] = useState('1h')

  const { data, isLoading, error } = useQuery<CoinData>({
    queryKey: ['coin-detail', coin],
    queryFn: () => fetchCoinDetail(coin),
    staleTime: 60 * 60 * 1000,
    gcTime:    60 * 60 * 1000,
    retry: 1,
  })

  const { data: positionsData } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 5_000,
  })

  const openPos = positionsData?.positions?.find(
    (p: any) => (p.coin ?? '').toUpperCase() === coin
  )

  async function handleRefresh() {
    setRefreshing(true)
    try {
      const fresh = await refreshCoinDetail(coin)
      qc.setQueryData(['coin-detail', coin], fresh)
    } finally {
      setRefreshing(false)
    }
  }

  const now = new Date()
  const expiresAt = data ? new Date(data.expires_at) : null
  const cachedAt  = data ? new Date(data.cached_at)  : null
  const msLeft    = expiresAt ? expiresAt.getTime() - now.getTime() : 0
  const minLeft   = Math.max(0, Math.floor(msLeft / 60000))
  const expired   = msLeft <= 0

  const isLong  = data?.direction?.includes('LONG')
  const isShort = data?.direction?.includes('SHORT')
  const bd      = data?.score_breakdown

  if (isLoading) return (
    <div className="flex items-center justify-center h-64 text-muted text-sm font-mono">
      <span className="animate-pulse">{coin} analiz ediliyor...</span>
    </div>
  )

  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="text-danger text-sm">Veri alınamadı.</div>
      <button className="btn-muted text-xs" onClick={() => navigate(-1)}>← Geri</button>
    </div>
  )

  return (
    <div className="space-y-4 max-w-6xl mx-auto">

      {/* Başlık */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button className="text-muted hover:text-text text-xs transition-colors" onClick={() => navigate(-1)}>
            ← Geri
          </button>
          <h1 className="text-text font-bold text-lg font-mono">{coin}</h1>
          {isLong  && <span className="badge-long">LONG ▲</span>}
          {isShort && <span className="badge-short">SHORT ▼</span>}
          {!isLong && !isShort && <span className="text-muted text-xs font-mono">NÖTR</span>}
          {data.last_price > 0 && (
            <span className="text-text font-mono text-sm">
              ${data.last_price < 1
                ? data.last_price.toFixed(6)
                : data.last_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted font-mono">
          {cachedAt && <span>Son: {cachedAt.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</span>}
          {!expired && <span className="text-warn">· {minLeft}dk kaldı</span>}
          {expired  && <span className="text-danger">· Süresi doldu</span>}
          <button
            className="btn-accent text-xs ml-1"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? (
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
                Yenileniyor
              </span>
            ) : '⟳ Yenile'}
          </button>
        </div>
      </div>

      {/* Grafik */}
      <div className="card p-0 overflow-hidden">
        {openPos ? (
          <>
            <div className="flex items-center justify-between px-3 pt-2 pb-1.5 border-b border-border">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-mono font-bold ${openPos.direction === 'long' ? 'text-accent' : 'text-danger'}`}>
                  {openPos.direction === 'long' ? 'LONG ▲' : 'SHORT ▼'}
                </span>
                <span className="text-muted text-xs">· Giriş: <span className="text-text font-mono">${Number(openPos.entry_price).toFixed(4)}</span></span>
                <span className="text-muted text-xs">· SL: <span className="text-danger font-mono">${Number(openPos.stop_loss_price).toFixed(4)}</span></span>
                {openPos.take_profit_price > 0 && (
                  <span className="text-muted text-xs">· TP1: <span className="text-accent font-mono">${Number(openPos.take_profit_price).toFixed(4)}</span></span>
                )}
              </div>
              <span className="text-muted text-xs font-mono">Açık Pozisyon</span>
            </div>
            <PositionChart
              coin={coin}
              direction={openPos.direction}
              entryPrice={Number(openPos.entry_price)}
              slPrice={Number(openPos.stop_loss_price)}
              tpPrice={Number(openPos.take_profit_price)}
              tp2Price={openPos.take_profit2_price ? Number(openPos.take_profit2_price) : undefined}
              height={480}
            />
          </>
        ) : (
          <>
            <div className="flex items-center gap-1 px-3 pt-2 pb-1 border-b border-border">
              {TF_ORDER.map(tf => (
                <button
                  key={tf}
                  onClick={() => setActiveTf(tf)}
                  className={`px-2 py-0.5 rounded text-xs font-mono transition-colors ${
                    activeTf === tf
                      ? 'text-accent bg-accent/10 border border-accent/20'
                      : 'text-muted hover:text-text'
                  }`}
                >
                  {data.timeframes[tf]?.label ?? tf}
                </button>
              ))}
            </div>
            <TradingViewChart coin={coin} timeframe={TF_TIMEFRAME[activeTf] ?? '1h'} height={480} />
          </>
        )}
      </div>

      {/* Skor özeti + detaylı dağılım */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Kombine skor özeti */}
        <div className="card space-y-3">
          <div className="text-text font-semibold text-sm">Skor Özeti</div>
          <div className="space-y-1.5">
            <div>
              <div className="flex justify-between text-xs text-muted mb-1">
                <span>Kombine Skor</span>
                <span className="font-mono" style={{ color: scoreColor(data.combined_score) }}>
                  {Math.round(data.combined_score * 100)}%
                </span>
              </div>
              <div style={{ height: 8, background: '#1e1e1e', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.round(data.combined_score * 100)}%`,
                  height: '100%',
                  background: scoreColor(data.combined_score),
                  borderRadius: 4,
                  transition: 'width 0.5s',
                }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs text-muted mb-1">
                <span>Teknik Skor</span>
                <span className="font-mono">{Math.round(data.technical_score * 100)}%</span>
              </div>
              <ScoreBar value={data.technical_score} />
            </div>
          </div>

          {/* Fear & Greed + Funding */}
          <div className="grid grid-cols-2 gap-2 pt-1 border-t border-border text-xs">
            <div>
              <div className="text-muted">Fear & Greed</div>
              <div className={`font-mono font-bold ${
                (bd?.fear_greed_index ?? 50) < 30 ? 'text-danger' :
                (bd?.fear_greed_index ?? 50) > 70 ? 'text-accent' : 'text-warn'
              }`}>
                {bd?.fear_greed_index ?? '—'}
                <span className="text-muted font-normal ml-1">
                  {(bd?.fear_greed_index ?? 50) < 25 ? '(Aşırı Korku)'
                    : (bd?.fear_greed_index ?? 50) < 45 ? '(Korku)'
                    : (bd?.fear_greed_index ?? 50) > 75 ? '(Aşırı Açgözlülük)'
                    : (bd?.fear_greed_index ?? 50) > 55 ? '(Açgözlülük)'
                    : '(Nötr)'}
                </span>
              </div>
            </div>
            <div>
              <div className="text-muted">Funding Rate</div>
              <div className={`font-mono font-bold ${
                bd?.funding_rate == null ? 'text-muted' :
                bd.funding_rate > 0 ? 'text-danger' : 'text-accent'
              }`}>
                {bd?.funding_rate != null
                  ? `${(bd.funding_rate * 100).toFixed(4)}%`
                  : '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Katkı dağılımı */}
        <div className="card space-y-3">
          <div className="text-text font-semibold text-sm">Skor Katkı Dağılımı</div>
          {bd && ['technical', 'sentiment', 'market'].map(key => {
            const item = bd[key as keyof ScoreBreakdown] as { label: string; weight: number; value: number; contribution: number }
            if (!item || typeof item !== 'object' || !('weight' in item)) return null
            return (
              <div key={key} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-muted">{item.label}</span>
                  <span className="font-mono text-text">
                    {Math.round(item.value * 100)}% × {Math.round(item.weight * 100)}%
                    <span className="text-muted ml-1">= {Math.round(item.contribution * 100)}%</span>
                  </span>
                </div>
                <ScoreBar value={item.contribution} max={item.weight} />
              </div>
            )
          })}
          <div className="pt-2 border-t border-border flex justify-between text-xs">
            <span className="text-muted">Toplam</span>
            <span className="font-mono font-bold" style={{ color: scoreColor(data.combined_score) }}>
              {Math.round(data.combined_score * 100)}%
            </span>
          </div>
        </div>
      </div>

      {/* Bot Karar Skoru */}
      {data.bot_scores && (() => {
        const bs = data.bot_scores!
        const threshold = bs.threshold
        const thresholdPct = Math.round(threshold * 100)
        return (
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-text font-semibold text-sm">Bot Karar Skoru</div>
              <span className="text-xs text-muted font-mono">Eşik: {thresholdPct}%</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* LONG */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-accent font-mono font-bold">LONG ▲</span>
                  <span className={`font-mono font-bold ${bs.long_eligible ? 'text-accent' : 'text-muted'}`}>
                    {Math.round(bs.long_combined * 100)}%
                    {bs.long_eligible
                      ? <span className="ml-1.5 text-xs text-accent">✓ GİRİŞ</span>
                      : <span className="ml-1.5 text-xs text-muted">✗ Yetersiz</span>}
                  </span>
                </div>
                <div style={{ position: 'relative', height: 8, background: '#1e1e1e', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(100, Math.round(bs.long_combined * 100))}%`,
                    height: '100%',
                    background: bs.long_eligible ? '#00ff88' : '#555555',
                    borderRadius: 4,
                    transition: 'width 0.5s',
                  }} />
                  {/* threshold line */}
                  <div style={{
                    position: 'absolute', top: 0, bottom: 0, width: 2,
                    background: '#ffaa00', left: `${thresholdPct}%`,
                    opacity: 0.8,
                  }} />
                </div>
                <div className="text-xs text-muted font-mono">Teknik: {Math.round(bs.long_tech * 100)}%</div>
              </div>
              {/* SHORT */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-danger font-mono font-bold">SHORT ▼</span>
                  <span className={`font-mono font-bold ${bs.short_eligible ? 'text-danger' : 'text-muted'}`}>
                    {Math.round(bs.short_combined * 100)}%
                    {bs.short_eligible
                      ? <span className="ml-1.5 text-xs text-danger">✓ GİRİŞ</span>
                      : <span className="ml-1.5 text-xs text-muted">✗ Yetersiz</span>}
                  </span>
                </div>
                <div style={{ position: 'relative', height: 8, background: '#1e1e1e', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(100, Math.round(bs.short_combined * 100))}%`,
                    height: '100%',
                    background: bs.short_eligible ? '#ff3333' : '#555555',
                    borderRadius: 4,
                    transition: 'width 0.5s',
                  }} />
                  <div style={{
                    position: 'absolute', top: 0, bottom: 0, width: 2,
                    background: '#ffaa00', left: `${thresholdPct}%`,
                    opacity: 0.8,
                  }} />
                </div>
                <div className="text-xs text-muted font-mono">Teknik: {Math.round(bs.short_tech * 100)}%</div>
              </div>
            </div>
            <div className="text-xs text-muted pt-1 border-t border-border">
              Sarı çizgi = bot eşiği ({thresholdPct}%). Bu skora ulaşan yön pozisyon açabilir.
              Ekranda görünen "Kombine Skor" yön bağımsız gösterim skorudur — bot skoru farklı olabilir.
            </div>
          </div>
        )
      })()}

      {/* Zaman dilimi analizleri */}
      <div>
        <div className="text-text font-semibold text-sm mb-3">Zaman Dilimi Analizleri</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {TF_ORDER.map(tf => (
            <TimeframeCard key={tf} tfKey={tf} tf={data.timeframes[tf] ?? { label: tf, error: 'Veri yok' }} />
          ))}
        </div>
      </div>

    </div>
  )
}
