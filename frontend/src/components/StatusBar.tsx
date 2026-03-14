import { useWebSocket } from '../lib/websocket'

interface LiveData {
  btc_regime: string
  fear_greed_index: number
  portfolio_value: number
  daily_pnl: number
  circuit_breaker_active: boolean
  positions: unknown[]
}

export default function StatusBar() {
  const { data, connected } = useWebSocket<LiveData>('live')

  return (
    <div className="flex items-center gap-3 text-xs font-mono">
      <span
        className={`w-2 h-2 rounded-full transition-colors ${connected ? 'bg-accent shadow-[0_0_6px_#00ff88]' : 'bg-muted'}`}
        title={connected ? 'Bağlı' : 'Bağlantı kesik'}
      />
      {data ? (
        <>
          <span className="text-muted hidden sm:inline">
            BTC:{' '}
            <span className={
              data.btc_regime === 'bull' ? 'text-accent' :
              data.btc_regime === 'bear' ? 'text-danger' : 'text-warn'
            }>
              {data.btc_regime === 'bull' ? 'BOĞA' : data.btc_regime === 'bear' ? 'AYI' : 'NÖTR'}
            </span>
          </span>
          <span className="text-muted hidden sm:inline">
            K&K: <span className="text-text">{data.fear_greed_index}</span>
          </span>
          <span className="text-muted">
            Günlük:{' '}
            <span className={data.daily_pnl >= 0 ? 'text-accent' : 'text-danger'}>
              {data.daily_pnl >= 0 ? '+' : ''}{data.daily_pnl.toFixed(2)}$
            </span>
          </span>
          <span className="text-muted hidden md:inline">
            Pos: <span className="text-text">{data.positions?.length ?? 0}</span>
          </span>
          {data.circuit_breaker_active && (
            <span className="text-danger border border-danger/30 px-2 py-0.5 rounded animate-pulse text-xs">
              DEVRE KESİCİ
            </span>
          )}
        </>
      ) : (
        <span className="text-muted">bağlanıyor...</span>
      )}
    </div>
  )
}
