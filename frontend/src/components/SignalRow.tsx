interface Signal {
  coin: string
  direction: string
  combined_score: number
  technical_score: number
  sentiment_score?: number
  reasons?: string[]
}

export default function SignalRow({ signal, onClick }: { signal: Signal; onClick?: () => void }) {
  const isLong = signal.direction.toLowerCase().includes('long')

  return (
    <tr
      className="border-b border-border hover:bg-white/[0.03] cursor-pointer transition-colors"
      onClick={onClick}
    >
      <td className="py-2 px-3 font-bold text-text">{signal.coin}</td>
      <td className="py-2 px-3">
        <span className={isLong ? 'badge-long' : 'badge-short'}>
          {isLong ? 'LONG' : 'SHORT'}
        </span>
      </td>
      <td className="py-2 px-3">
        <ScoreBar value={signal.combined_score} />
      </td>
      <td className="py-2 px-3 text-xs text-muted">
        T:{(signal.technical_score * 100).toFixed(0)}%
        {signal.sentiment_score != null && ` D:${(signal.sentiment_score * 100).toFixed(0)}%`}
      </td>
      <td className="py-2 px-3 text-xs text-muted max-w-xs truncate">
        {signal.reasons?.slice(0, 2).join(', ')}
      </td>
    </tr>
  )
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.75 ? '#00ff88' : value >= 0.6 ? '#ffaa00' : '#ff3333'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-border rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  )
}
