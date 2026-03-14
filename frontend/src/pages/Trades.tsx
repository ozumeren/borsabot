import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchTrades, fetchTradeStats } from '../lib/api'

const STATUS_OPTIONS = [
  { value: '', label: 'Tüm durumlar' },
  { value: 'OPEN', label: 'Açık' },
  { value: 'CLOSED_TP', label: 'Kâr Al' },
  { value: 'CLOSED_TP1', label: 'Kısmi Kâr Al' },
  { value: 'CLOSED_SL', label: 'Zarar Kes' },
  { value: 'CLOSED_MANUAL', label: 'Manuel Kapatma' },
  { value: 'CLOSED_CIRCUIT', label: 'Devre Kesici' },
]

const statusLabel: Record<string, string> = {
  OPEN: 'Açık',
  CLOSED_TP: 'Kâr Al',
  CLOSED_TP1: 'Kısmi KA',
  CLOSED_SL: 'Zarar Kes',
  CLOSED_MANUAL: 'Manuel',
  CLOSED_CIRCUIT: 'Devre Kesici',
}

export default function Trades() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [coin, setCoin] = useState('')
  const [direction, setDirection] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['trades', page, status, coin, direction],
    queryFn: () => fetchTrades({
      page,
      per_page: 20,
      status: status || undefined,
      coin: coin || undefined,
      direction: direction || undefined,
    }),
  })
  const { data: stats } = useQuery({ queryKey: ['trade-stats'], queryFn: fetchTradeStats })

  return (
    <div className="space-y-4">
      <h1 className="text-text font-semibold">İşlem Geçmişi</h1>

      {/* İstatistikler */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {[
            { label: 'Toplam', value: stats.lifetime.total_trades },
            { label: 'Kazanan', value: stats.lifetime.winning_trades },
            { label: 'Kaybeden', value: stats.lifetime.losing_trades },
            { label: 'Kazanma Oranı', value: `${(stats.lifetime.win_rate * 100).toFixed(1)}%` },
            {
              label: 'Toplam K/Z',
              value: `${stats.lifetime.total_pnl_usdt >= 0 ? '+' : ''}${stats.lifetime.total_pnl_usdt.toFixed(2)}$`,
              signed: true,
              val: stats.lifetime.total_pnl_usdt,
            },
            { label: 'Sharpe', value: stats.lifetime.sharpe_ratio?.toFixed(2) ?? '—' },
          ].map(s => (
            <div key={s.label} className="card">
              <div className="text-muted text-xs">{s.label}</div>
              <div className={`text-sm font-bold font-mono mt-0.5 ${
                'signed' in s && s.signed ? (s.val! >= 0 ? 'pnl-positive' : 'pnl-negative') : 'text-text'
              }`}>{String(s.value)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filtreler */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          placeholder="Coin (örn: BTC)"
          value={coin}
          onChange={e => { setCoin(e.target.value.toUpperCase()); setPage(1) }}
          className="bg-card border border-border rounded px-3 py-1.5 text-sm text-text font-mono w-32 focus:outline-none focus:border-accent/50"
        />
        <select
          value={direction}
          onChange={e => { setDirection(e.target.value); setPage(1) }}
          className="bg-card border border-border rounded px-3 py-1.5 text-sm text-text font-mono focus:outline-none focus:border-accent/50"
        >
          <option value="">Tüm yönler</option>
          <option value="long">Long</option>
          <option value="short">Short</option>
        </select>
        <select
          value={status}
          onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="bg-card border border-border rounded px-3 py-1.5 text-sm text-text font-mono focus:outline-none focus:border-accent/50"
        >
          {STATUS_OPTIONS.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        {(coin || direction || status) && (
          <button
            className="btn-muted text-xs"
            onClick={() => { setCoin(''); setDirection(''); setStatus(''); setPage(1) }}
          >
            ✕ Temizle
          </button>
        )}
      </div>

      {/* Tablo */}
      <div className="card overflow-x-auto">
        {isLoading ? (
          <div className="text-muted text-sm py-8 text-center animate-pulse">Yükleniyor...</div>
        ) : (data?.trades?.length ?? 0) === 0 ? (
          <div className="text-muted text-sm py-8 text-center">İşlem bulunamadı</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2 px-2">Coin</th>
                <th className="text-left py-2 px-2">Yön</th>
                <th className="text-left py-2 px-2">Durum</th>
                <th className="text-right py-2 px-2">Giriş</th>
                <th className="text-right py-2 px-2">Çıkış</th>
                <th className="text-right py-2 px-2">K/Z $</th>
                <th className="text-right py-2 px-2">K/Z %</th>
                <th className="text-right py-2 px-2">Skor</th>
                <th className="text-right py-2 px-2">Tarih</th>
              </tr>
            </thead>
            <tbody>
              {data?.trades?.map((t: any) => (
                <tr key={t.id} className="border-b border-border/40 hover:bg-white/[0.02] transition-colors">
                  <td className="py-1.5 px-2 text-muted">{t.id}</td>
                  <td className="py-1.5 px-2 text-text font-bold">{t.coin}</td>
                  <td className="py-1.5 px-2">
                    <span className={t.direction === 'long' ? 'badge-long' : 'badge-short'}>
                      {t.direction === 'long' ? 'LONG' : 'SHORT'}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-muted">{statusLabel[t.status] ?? t.status}</td>
                  <td className="py-1.5 px-2 text-right font-mono text-text">{t.entry_price?.toFixed(4)}</td>
                  <td className="py-1.5 px-2 text-right font-mono text-text">{t.exit_price?.toFixed(4) ?? '—'}</td>
                  <td className={`py-1.5 px-2 text-right font-mono ${(t.pnl_usdt ?? 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                    {t.pnl_usdt != null ? `${t.pnl_usdt >= 0 ? '+' : ''}${t.pnl_usdt.toFixed(2)}$` : '—'}
                  </td>
                  <td className={`py-1.5 px-2 text-right font-mono ${(t.pnl_pct ?? 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                    {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? '+' : ''}${(t.pnl_pct * 100).toFixed(2)}%` : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-right text-muted">
                    {t.combined_score != null ? `${(t.combined_score * 100).toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-1.5 px-2 text-right text-muted">
                    {t.opened_at ? new Date(t.opened_at).toLocaleDateString('tr-TR') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Sayfalama */}
      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 justify-center">
          <button className="btn-muted" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹ Önceki</button>
          <span className="text-muted text-sm font-mono">{page} / {data.pages}</span>
          <button className="btn-muted" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>Sonraki ›</button>
        </div>
      )}
    </div>
  )
}
