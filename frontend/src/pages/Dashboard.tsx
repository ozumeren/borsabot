import { useQuery } from '@tanstack/react-query'
import { fetchDashboard } from '../lib/api'
import { useWebSocket } from '../lib/websocket'
import PnLChart from '../components/PnLChart'
import PositionCard from '../components/PositionCard'
import FearGreedGauge from '../components/FearGreedGauge'

interface LiveData {
  portfolio_value: number
  daily_pnl: number
  fear_greed_index: number
  btc_regime: string
  positions: unknown[]
}

export default function Dashboard() {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: fetchDashboard })
  const { data: live } = useWebSocket<LiveData>('live')

  const portfolio = live?.portfolio_value ?? data?.portfolio_value ?? 0
  const dailyPnl = live?.daily_pnl ?? data?.daily_pnl ?? 0
  const fearGreed = live?.fear_greed_index ?? data?.fear_greed_index ?? 50
  const regime = live?.btc_regime ?? data?.btc_regime ?? 'neutral'

  if (isLoading) return (
    <div className="flex items-center justify-center h-48 text-muted text-sm">
      <span className="animate-pulse">Yükleniyor...</span>
    </div>
  )

  const kpis = [
    { label: 'Portföy', value: `$${portfolio.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}` },
    { label: 'Günlük K/Z', value: `${dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}$`, signed: true, val: dailyPnl },
    { label: 'Bugünkü İşlem', value: data?.daily_trades ?? 0 },
    { label: 'Kazanan/Kaybeden', value: `${data?.daily_winning ?? 0}/${data?.daily_losing ?? 0}` },
    { label: 'Toplam K/Z', value: `${(data?.lifetime_pnl ?? 0) >= 0 ? '+' : ''}${(data?.lifetime_pnl ?? 0).toFixed(2)}$`, signed: true, val: data?.lifetime_pnl ?? 0 },
    { label: 'Kazanma Oranı', value: `${((data?.lifetime_win_rate ?? 0) * 100).toFixed(1)}%` },
    { label: 'Toplam İşlem', value: data?.lifetime_trades ?? 0 },
    { label: 'Açık Pozisyon', value: data?.open_positions_count ?? 0 },
  ]

  const regimeLabel = regime === 'bull' ? 'BOĞA' : regime === 'bear' ? 'AYI' : 'NÖTR'
  const regimeClass = regime === 'bull' ? 'text-accent' : regime === 'bear' ? 'text-danger' : 'text-warn'

  return (
    <div className="space-y-4">
      {/* Paper trading uyarısı */}
      {data?.paper_trading && (
        <div className="flex items-center gap-2 text-xs text-warn border border-warn/20 bg-warn/5 rounded px-3 py-2">
          <span>⚠</span>
          <span>Simülasyon modu aktif — gerçek para kullanılmıyor</span>
        </div>
      )}

      {/* KPI kartları */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {kpis.map(k => (
          <div key={k.label} className="card">
            <div className="text-muted text-xs leading-tight">{k.label}</div>
            <div className={`text-base font-bold mt-1 font-mono ${
              'signed' in k ? (k.val! >= 0 ? 'pnl-positive' : 'pnl-negative') : 'text-text'
            }`}>
              {String(k.value)}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Özsermaye eğrisi */}
        <div className="card lg:col-span-2 space-y-2">
          <div className="text-sm text-text font-semibold">Özsermaye Eğrisi (30 gün)</div>
          <PnLChart data={data?.equity_curve ?? []} />
        </div>

        {/* Korku & Açgözlülük + BTC Rejimi */}
        <div className="card flex flex-col items-center justify-center gap-4 py-6">
          <FearGreedGauge value={fearGreed} />
          <div className="text-center">
            <div className="text-xs text-muted mb-1">BTC Piyasa Rejimi</div>
            <div className={`text-2xl font-bold ${regimeClass}`}>{regimeLabel}</div>
          </div>
        </div>
      </div>

      {/* Açık pozisyonlar */}
      {(data?.open_positions?.length ?? 0) > 0 && (
        <div className="space-y-2">
          <div className="text-sm text-text font-semibold">
            Açık Pozisyonlar
            <span className="text-muted font-normal ml-2">({data.open_positions.length})</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {data.open_positions.map((pos: any) => (
              <PositionCard key={pos.coin} pos={pos} />
            ))}
          </div>
        </div>
      )}

      {/* En iyi fırsat */}
      {data?.best_opportunity && (
        <div className="card border-accent/20 bg-accent/[0.03]">
          <div className="text-xs text-muted mb-2">En İyi Fırsat</div>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-text font-bold">{data.best_opportunity.coin}</span>
            <span className={data.best_opportunity.direction.includes('long') ? 'badge-long' : 'badge-short'}>
              {data.best_opportunity.direction.includes('long') ? 'LONG' : 'SHORT'}
            </span>
            <span className="text-accent font-mono text-sm font-bold">
              {(data.best_opportunity.combined_score * 100).toFixed(0)}%
            </span>
            <span className="text-muted text-xs truncate">
              {data.best_opportunity.reasons?.slice(0, 3).join(' · ')}
            </span>
          </div>
        </div>
      )}

      {/* Son işlemler */}
      {(data?.recent_trades?.length ?? 0) > 0 && (
        <div className="space-y-2">
          <div className="text-sm text-text font-semibold">Son İşlemler</div>
          <div className="card overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted border-b border-border">
                  <th className="text-left py-2 px-2">Coin</th>
                  <th className="text-left py-2 px-2">Yön</th>
                  <th className="text-left py-2 px-2">Durum</th>
                  <th className="text-right py-2 px-2">K/Z</th>
                  <th className="text-right py-2 px-2">Kapanış</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_trades.map((t: any) => (
                  <tr key={t.id} className="border-b border-border/40 hover:bg-white/[0.02]">
                    <td className="py-1.5 px-2 text-text font-bold">{t.coin}</td>
                    <td className="py-1.5 px-2">
                      <span className={t.direction === 'long' ? 'badge-long' : 'badge-short'}>
                        {t.direction === 'long' ? 'LONG' : 'SHORT'}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 text-muted">{t.status}</td>
                    <td className={`py-1.5 px-2 text-right font-mono ${(t.pnl_usdt ?? 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                      {(t.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(t.pnl_usdt ?? 0).toFixed(2)}$
                    </td>
                    <td className="py-1.5 px-2 text-right text-muted">
                      {t.closed_at ? new Date(t.closed_at).toLocaleDateString('tr-TR') : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
