import { useEffect, useRef } from 'react'
import { createChart, ColorType, LineStyle } from 'lightweight-charts'

interface EquityPoint {
  date: string
  value: number
}

export default function PnLChart({ data }: { data: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111111' },
        textColor: '#555555',
      },
      grid: {
        vertLines: { color: '#1f1f1f' },
        horzLines: { color: '#1f1f1f' },
      },
      crosshair: {
        vertLine: { color: '#333', style: LineStyle.Dashed },
        horzLine: { color: '#333', style: LineStyle.Dashed },
      },
      timeScale: {
        borderColor: '#1f1f1f',
        timeVisible: true,
      },
      rightPriceScale: { borderColor: '#1f1f1f' },
      width: containerRef.current.clientWidth,
      height: 200,
    })

    const series = chart.addAreaSeries({
      lineColor: '#00ff88',
      topColor: 'rgba(0,255,136,0.15)',
      bottomColor: 'rgba(0,255,136,0)',
      lineWidth: 2,
    })

    const chartData = data
      .filter(d => d.value > 0)
      .map(d => ({ time: d.date as `${number}-${number}-${number}`, value: d.value }))

    if (chartData.length) series.setData(chartData)

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current!.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="w-full" />
}
