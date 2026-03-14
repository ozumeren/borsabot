interface Props {
  value: number
}

function getLabel(v: number): string {
  if (v <= 20) return 'Aşırı Korku'
  if (v <= 40) return 'Korku'
  if (v <= 60) return 'Nötr'
  if (v <= 80) return 'Açgözlülük'
  return 'Aşırı Açgözlülük'
}

function getColor(v: number): string {
  if (v <= 25) return '#ff3333'
  if (v <= 45) return '#ff8800'
  if (v <= 55) return '#ffaa00'
  if (v <= 75) return '#88ff44'
  return '#00ff88'
}

export default function FearGreedGauge({ value }: Props) {
  const color = getColor(value)
  const label = getLabel(value)
  const angle = -90 + (value / 100) * 180

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="text-xs text-muted tracking-wider">KORKU & AÇGÖZLÜLÜK</div>
      <svg width="160" height="90" viewBox="0 0 160 90">
        <path d="M 10 80 A 70 70 0 0 1 150 80" fill="none" stroke="#1f1f1f" strokeWidth="12" strokeLinecap="round" />
        <path
          d="M 10 80 A 70 70 0 0 1 150 80"
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${value * 2.2} 220`}
          opacity="0.8"
        />
        <g transform={`rotate(${angle}, 80, 80)`}>
          <line x1="80" y1="80" x2="80" y2="18" stroke={color} strokeWidth="2" strokeLinecap="round" />
          <circle cx="80" cy="80" r="4" fill={color} />
        </g>
        <text x="80" y="70" textAnchor="middle" fill={color} fontSize="20" fontFamily="monospace" fontWeight="600">
          {value}
        </text>
      </svg>
      <div className="text-sm font-mono font-semibold" style={{ color }}>{label}</div>
    </div>
  )
}
