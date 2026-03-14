import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts'

interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface Props {
  candles: Candle[]
  height?: number
  showVolume?: boolean
}

export default function CandleChart({ candles, height = 380, showVolume = true }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  // Chart'ı bir kez oluştur
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      width: el.offsetWidth || 600,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#111111' },
        textColor: '#aaaaaa',
        fontFamily: 'monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1e1e1e', style: LineStyle.Solid },
        horzLines: { color: '#1e1e1e', style: LineStyle.Solid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#555', style: LineStyle.Dashed, width: 1, labelBackgroundColor: '#333' },
        horzLine: { color: '#555', style: LineStyle.Dashed, width: 1, labelBackgroundColor: '#333' },
      },
      timeScale: {
        borderColor: '#333',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 6,
      },
      rightPriceScale: {
        borderColor: '#333',
        scaleMargins: showVolume ? { top: 0.08, bottom: 0.28 } : { top: 0.08, bottom: 0.05 },
      },
    })

    chartRef.current = chart

    const cs = chart.addCandlestickSeries({
      upColor: '#00ff88',
      downColor: '#ff3333',
      borderUpColor: '#00ff88',
      borderDownColor: '#ff3333',
      wickUpColor: '#00cc66',
      wickDownColor: '#cc2222',
    })
    candleSeriesRef.current = cs

    if (showVolume) {
      const vs = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'vol',
      })
      vs.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      volumeSeriesRef.current = vs
    }

    const ro = new ResizeObserver(() => {
      if (el && chartRef.current) {
        chartRef.current.applyOptions({ width: el.offsetWidth })
      }
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chartRef.current?.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Veri değiştiğinde sadece data'yı güncelle
  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return

    candleSeriesRef.current.setData(
      candles.map(c => ({
        time: c.time as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    )

    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.setData(
        candles.map(c => ({
          time: c.time as any,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(0,255,136,0.25)' : 'rgba(255,51,51,0.25)',
        }))
      )
    }

    chartRef.current?.timeScale().fitContent()
  }, [candles])

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: `${height}px`,
        overflow: 'hidden',
        position: 'relative',
        background: '#111111',
        borderRadius: 4,
      }}
    />
  )
}
