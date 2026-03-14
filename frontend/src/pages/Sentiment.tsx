import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSentimentOverview, fetchCoinSentiment } from '../lib/api'
import FearGreedGauge from '../components/FearGreedGauge'

export default function Sentiment() {
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null)

  const { data } = useQuery({ queryKey: ['sentiment-overview'], queryFn: fetchSentimentOverview })
  const { data: coinData } = useQuery({
    queryKey: ['sentiment-coin', selectedCoin],
    queryFn: () => fetchCoinSentiment(selectedCoin!),
    enabled: !!selectedCoin,
  })

  const coins = Object.keys(data?.news_by_coin ?? {})

  const regimeLabel = data?.btc_regime === 'bull' ? 'BOĞA' : data?.btc_regime === 'bear' ? 'AYI' : 'NÖTR'
  const regimeClass = data?.btc_regime === 'bull' ? 'text-accent' : data?.btc_regime === 'bear' ? 'text-danger' : 'text-warn'

  return (
    <div className="space-y-4">
      <h1 className="text-text font-semibold">Piyasa Duygusu</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Gösterge + Rejim */}
        <div className="card flex flex-col items-center justify-center gap-4 py-6">
          <FearGreedGauge value={data?.fear_greed_index ?? 50} />
          <div className="text-center">
            <div className="text-xs text-muted mb-1">BTC Piyasa Rejimi</div>
            <div className={`text-xl font-bold ${regimeClass}`}>{regimeLabel}</div>
          </div>
        </div>

        {/* Gemini AI skorları */}
        <div className="card space-y-2">
          <div className="text-sm text-text font-semibold">AI Duygu Skorları (Gemini)</div>
          <div className="space-y-1 max-h-72 overflow-y-auto pr-1">
            {Object.entries(data?.gemini_scores ?? {})
              .sort(([, a]: any, [, b]: any) => Math.abs(b.score) - Math.abs(a.score))
              .map(([coin, g]: any) => (
                <div
                  key={coin}
                  className="flex items-center justify-between text-xs cursor-pointer hover:bg-white/[0.03] px-2 py-1 rounded transition-colors"
                  onClick={() => setSelectedCoin(coin === selectedCoin ? null : coin)}
                >
                  <span className={`text-text font-mono ${coin === selectedCoin ? 'text-accent' : ''}`}>{coin}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1 bg-border rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.abs(g.score) * 100}%`,
                          background: g.score >= 0 ? '#00ff88' : '#ff3333',
                        }}
                      />
                    </div>
                    <span className={`font-mono w-10 text-right ${g.score >= 0 ? 'text-accent' : 'text-danger'}`}>
                      {g.score >= 0 ? '+' : ''}{(g.score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            {Object.keys(data?.gemini_scores ?? {}).length === 0 && (
              <div className="text-muted text-xs py-4 text-center">Henüz skor yok</div>
            )}
          </div>
        </div>

        {/* Haber akışı */}
        <div className="card space-y-2">
          <div className="text-sm text-text font-semibold">Son Haberler</div>
          <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
            {coins.length === 0 && (
              <div className="text-muted text-xs py-4 text-center">Haber önbelleği boş</div>
            )}
            {coins.map(coin => (
              <div key={coin}>
                <div
                  className="text-xs text-muted cursor-pointer hover:text-text transition-colors"
                  onClick={() => setSelectedCoin(coin === selectedCoin ? null : coin)}
                >
                  {coin}
                </div>
                {(data.news_by_coin[coin] ?? []).map((h: string, i: number) => (
                  <div key={i} className="text-xs text-text pl-2 border-l border-border py-0.5 truncate" title={h}>
                    {h}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Coin detay */}
      {selectedCoin && coinData && (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-text font-bold">{selectedCoin} — Detay</div>
            <button className="text-muted hover:text-text transition-colors" onClick={() => setSelectedCoin(null)}>✕</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <div className="text-muted mb-2">Haber Başlıkları</div>
              {(coinData.headlines?.length ?? 0) === 0 ? (
                <div className="text-muted">Haber bulunamadı</div>
              ) : coinData.headlines?.map((h: string, i: number) => (
                <div key={i} className="text-text py-1 border-b border-border/40 truncate" title={h}>{h}</div>
              ))}
            </div>
            <div className="space-y-3">
              {coinData.gemini_score != null && (
                <div>
                  <div className="text-muted mb-1">AI Skoru</div>
                  <div className={`text-lg font-bold font-mono ${coinData.gemini_score >= 0 ? 'text-accent' : 'text-danger'}`}>
                    {coinData.gemini_score >= 0 ? '+' : ''}{(coinData.gemini_score * 100).toFixed(0)}%
                  </div>
                  {coinData.gemini_reason && (
                    <div className="text-muted text-xs mt-1">{coinData.gemini_reason}</div>
                  )}
                </div>
              )}
              {coinData.funding_rate != null && (
                <div>
                  <div className="text-muted mb-1">Fonlama Oranı</div>
                  <div className={`font-mono ${coinData.funding_rate >= 0 ? 'text-accent' : 'text-danger'}`}>
                    {(coinData.funding_rate * 100).toFixed(4)}%
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
