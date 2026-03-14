import { useEffect, useRef } from 'react'

declare global {
  interface Window { TradingView: any }
}

const TF_MAP: Record<string, string> = {
  '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
  '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720', '1d': 'D',
}

interface Props {
  coin: string
  timeframe?: string
  height?: number
}

let scriptLoaded = false
const callbacks: (() => void)[] = []

function loadTVScript(cb: () => void) {
  if (scriptLoaded) { cb(); return }
  callbacks.push(cb)
  if (document.getElementById('tv-script')) return
  const s = document.createElement('script')
  s.id = 'tv-script'
  s.src = 'https://s3.tradingview.com/tv.js'
  s.async = true
  s.onload = () => {
    scriptLoaded = true
    callbacks.forEach(fn => fn())
    callbacks.length = 0
  }
  document.head.appendChild(s)
}

export default function TradingViewChart({ coin, timeframe = '15m', height = 520 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(`tv_${Math.random().toString(36).slice(2, 9)}`)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    el.innerHTML = `<div id="${idRef.current}" style="height:${height}px"></div>`

    const init = () => {
      if (!window.TradingView) return
      new window.TradingView.widget({
        container_id: idRef.current,
        autosize: true,
        height,
        symbol: `BINANCE:${coin}USDTPERP`,
        interval: TF_MAP[timeframe] ?? '15',
        timezone: 'Europe/Istanbul',
        theme: 'dark',
        style: '1',
        locale: 'tr',
        toolbar_bg: '#111111',
        enable_publishing: false,
        allow_symbol_change: false,
        save_image: true,
        hide_side_toolbar: false,
        withdateranges: true,
        details: false,
        hotlist: false,
        calendar: false,
        studies: [],
        overrides: {
          'paneProperties.background': '#111111',
          'paneProperties.backgroundType': 'solid',
          'paneProperties.vertGridProperties.color': '#1a1a1a',
          'paneProperties.horzGridProperties.color': '#1a1a1a',
          'scalesProperties.textColor': '#888888',
        },
      })
    }

    loadTVScript(init)

    return () => {
      if (el) el.innerHTML = ''
    }
  }, [coin, timeframe, height])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: `${height}px`, overflow: 'hidden', borderRadius: 4, background: '#111111' }}
    />
  )
}
