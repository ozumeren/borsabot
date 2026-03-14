import { useEffect, useRef, useState } from 'react'
import { getApiKey } from './api'

type WsEndpoint = 'live' | 'signals'

export function useWebSocket<T = unknown>(endpoint: WsEndpoint) {
  const [data, setData] = useState<T | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const key = getApiKey()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/${endpoint}?token=${key}`

    let stopped = false

    function connect() {
      if (stopped) return
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!stopped) setTimeout(connect, 3000)
      }
      ws.onerror = () => { /* onclose will fire automatically */ }
      ws.onmessage = (e) => {
        try { setData(JSON.parse(e.data)) } catch {}
      }
    }

    connect()
    return () => {
      stopped = true
      wsRef.current?.close()
    }
  }, [endpoint])

  return { data, connected }
}
