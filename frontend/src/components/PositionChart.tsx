import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts'
import { fetchChart } from '../lib/api'

interface Props {
  coin: string
  direction: string   // 'long' | 'short'
  entryPrice: number
  slPrice: number
  tpPrice: number
  tp2Price?: number
  height?: number
}

export default function PositionChart({
  coin,
  direction,
  entryPrice,
  slPrice,
  tpPrice,
  tp2Price,
  height = 280,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const { data } = useQuery({
    queryKey: ['chart', coin, '15m', 100],
    queryFn: () => fetchChart(coin, '15m', 100),
    refetchInterval: 30_000,
  })

  // Chart'ı bir kez oluştur
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      width: el.offsetWidth || 500,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#0d0d0d' },
        textColor: '#888',
        fontFamily: 'monospace',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#161616' },
        horzLines: { color: '#161616' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: '#222', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#222' },
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
    seriesRef.current = cs

    // Price lines
    cs.createPriceLine({
      price: entryPrice,
      color: '#ffaa00',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: 'Giriş',
    })
    cs.createPriceLine({
      price: tpPrice,
      color: '#00ff88',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: 'TP1',
    })
    if (tp2Price && tp2Price > 0) {
      cs.createPriceLine({
        price: tp2Price,
        color: '#00cc66',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: 'TP2',
      })
    }
    cs.createPriceLine({
      price: slPrice,
      color: '#ff3333',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: 'SL',
    })

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
      seriesRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Veri güncellenince
  useEffect(() => {
    if (!seriesRef.current || !data?.candles?.length) return
    seriesRef.current.setData(
      data.candles.map((c: any) => ({
        time: c.time as any,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
    )
    chartRef.current?.timeScale().fitContent()
  }, [data])

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: `${height}px`,
        overflow: 'hidden',
        position: 'relative',
        background: '#0d0d0d',
        borderRadius: 4,
      }}
    />
  )
}
