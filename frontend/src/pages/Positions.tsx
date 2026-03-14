import { useQuery } from '@tanstack/react-query'
import { fetchPositions } from '../lib/api'
import PositionCard from '../components/PositionCard'
import ErrorBoundary from '../components/ErrorBoundary'

export default function Positions() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 30_000,   // WsSync 3s'de cache'i günceller, bu sadece fallback
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-text font-semibold">Açık Pozisyonlar</h1>
          <p className="text-muted text-xs mt-0.5">Her 5 saniyede otomatik güncellenir</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted text-xs">{data?.count ?? 0} açık</span>
          <button className="btn-muted text-xs" onClick={() => refetch()}>↻ Yenile</button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center h-32 text-muted text-sm animate-pulse">
          Yükleniyor...
        </div>
      )}

      {!isLoading && (data?.count ?? 0) === 0 && (
        <div className="card text-muted text-sm text-center py-12">
          <div className="text-2xl mb-2">—</div>
          Şu anda açık pozisyon yok
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {data?.positions?.map((pos: any) => (
          <ErrorBoundary key={pos.coin}>
            <PositionCard pos={pos} />
          </ErrorBoundary>
        ))}
      </div>
    </div>
  )
}
