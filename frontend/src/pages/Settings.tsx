import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSettings, updateSettings } from '../lib/api'

interface Field {
  key: string
  label: string
  desc?: string
  type: 'number' | 'float' | 'pct'
  min?: number
  max?: number
  step?: number
}

const GROUPS: { group: string; fields: Field[] }[] = [
  {
    group: 'İşlem Ayarları',
    fields: [
      { key: 'leverage', label: 'Kaldıraç', desc: 'Temel kaldıraç oranı', type: 'number', min: 1, max: 20 },
      { key: 'max_leverage', label: 'Maks. Kaldıraç', desc: 'Dinamik üst sınır', type: 'number', min: 1, max: 20 },
      { key: 'max_concurrent_positions', label: 'Maks. Eş Zamanlı Pozisyon', type: 'number', min: 1, max: 20 },
      { key: 'scan_top_n_coins', label: 'Taranan Coin Sayısı', type: 'number', min: 5, max: 100 },
    ],
  },
  {
    group: 'Risk Yönetimi',
    fields: [
      { key: 'daily_loss_limit_pct', label: 'Günlük Kayıp Limiti', desc: 'Bu sınır aşılınca bot durur', type: 'pct', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'stop_loss_pct_from_entry', label: 'Zarar Kes Yüzdesi', desc: 'Giriş fiyatından uzaklık', type: 'pct', min: 0.005, max: 0.2, step: 0.001 },
      { key: 'max_position_size_pct', label: 'Maks. Pozisyon Büyüklüğü', desc: 'Portföyün yüzdesi', type: 'pct', min: 0.01, max: 0.5, step: 0.01 },
    ],
  },
  {
    group: 'Sinyal Eşikleri',
    fields: [
      { key: 'min_technical_score', label: 'Min. Teknik Skor', desc: 'Bu değerin altındaki sinyaller göz ardı edilir', type: 'float', min: 0.3, max: 1.0, step: 0.01 },
      { key: 'min_combined_score', label: 'Min. Birleşik Skor', desc: 'Teknik + duygu skoru birleşimi', type: 'float', min: 0.3, max: 1.0, step: 0.01 },
    ],
  },
]

function fmt(type: string, v: number): string {
  if (type === 'pct') return `${(v * 100).toFixed(1)}%`
  if (type === 'float') return v.toFixed(2)
  return String(v)
}

export default function Settings() {
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const qc = useQueryClient()
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  if (isLoading) return (
    <div className="flex items-center justify-center h-32 text-muted text-sm animate-pulse">
      Yükleniyor...
    </div>
  )

  function handleChange(key: string, val: string) {
    setEdits(prev => ({ ...prev, [key]: val }))
    setMsg(null)
  }

  async function handleSave() {
    const payload: Record<string, number> = {}
    for (const [k, v] of Object.entries(edits)) {
      const n = parseFloat(v)
      if (!isNaN(n)) payload[k] = n
    }
    if (!Object.keys(payload).length) return
    setSaving(true)
    try {
      await updateSettings(payload)
      qc.invalidateQueries({ queryKey: ['settings'] })
      setEdits({})
      setMsg({ text: '✓ Ayarlar kaydedildi.', ok: true })
      setTimeout(() => setMsg(null), 3000)
    } catch (e: any) {
      setMsg({ text: `Hata: ${e.response?.data?.detail ?? e.message}`, ok: false })
    } finally {
      setSaving(false)
    }
  }

  const dirtyCount = Object.keys(edits).length

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-text font-semibold">Ayarlar</h1>
        <div className="flex items-center gap-3">
          {msg && (
            <span className={`text-xs ${msg.ok ? 'text-accent' : 'text-danger'}`}>{msg.text}</span>
          )}
          {dirtyCount > 0 && (
            <span className="text-warn text-xs">{dirtyCount} değişiklik</span>
          )}
          <button
            className="btn-accent"
            onClick={handleSave}
            disabled={saving || dirtyCount === 0}
          >
            {saving ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>
      </div>

      {/* İşlem modu göstergesi */}
      <div className={`card border-l-2 ${data?.paper_trading ? 'border-l-warn' : 'border-l-danger'}`}>
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${data?.paper_trading ? 'bg-warn' : 'bg-danger animate-pulse'}`} />
          <div>
            <div className="text-sm font-semibold">
              {data?.paper_trading ? (
                <span className="text-warn">Simülasyon Modu</span>
              ) : (
                <span className="text-danger">CANLI İŞLEM MODU — Gerçek para kullanılıyor</span>
              )}
            </div>
            <div className="text-xs text-muted mt-0.5">
              İşlem modu yalnızca .env dosyasından değiştirilebilir (PAPER_TRADING)
            </div>
          </div>
        </div>
      </div>

      {GROUPS.map(group => (
        <div key={group.group} className="card space-y-4">
          <div className="text-sm text-text font-semibold border-b border-border pb-2">{group.group}</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {group.fields.map(field => {
              const current = data?.[field.key]
              const editVal = edits[field.key]
              const isDirty = editVal !== undefined

              return (
                <div key={field.key}>
                  <label className="text-muted text-xs block mb-0.5">{field.label}</label>
                  {field.desc && <div className="text-muted text-xs mb-1.5 opacity-70">{field.desc}</div>}
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step={field.step ?? 1}
                      min={field.min}
                      max={field.max}
                      value={editVal ?? (current ?? '')}
                      onChange={e => handleChange(field.key, e.target.value)}
                      className={`bg-bg border rounded px-3 py-1.5 text-sm text-text font-mono w-28 focus:outline-none transition-colors ${
                        isDirty ? 'border-accent/60 shadow-[0_0_0_1px_rgba(0,255,136,0.1)]' : 'border-border'
                      }`}
                    />
                    <span className="text-xs font-mono">
                      {isDirty ? (
                        <span className="text-accent">→ {fmt(field.type, parseFloat(editVal) || 0)}</span>
                      ) : (
                        <span className="text-muted">{fmt(field.type, current ?? 0)}</span>
                      )}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {/* Bilgi kartı */}
      <div className="card space-y-2">
        <div className="text-sm text-text font-semibold border-b border-border pb-2">Sistem Bilgisi (salt okunur)</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div><span className="text-muted">Zaman Dilimi: </span><span className="text-text font-mono">{data?.timeframe}</span></div>
          <div><span className="text-muted">Marjin Modu: </span><span className="text-text font-mono">{data?.margin_mode}</span></div>
          <div className="col-span-2"><span className="text-muted">Veritabanı: </span><span className="text-muted font-mono truncate">{data?.database_url}</span></div>
        </div>
      </div>
    </div>
  )
}
