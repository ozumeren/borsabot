import { useState } from 'react'
import { setApiKey } from '../lib/api'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    setLoading(true)
    setError('')
    try {
      setApiKey(input.trim())
      // Test the key
      const res = await fetch('/api/bot/status', {
        headers: { Authorization: `Bearer ${input.trim()}` },
      })
      if (res.ok) {
        onLogin()
      } else {
        setError('Geçersiz API anahtarı. Lütfen tekrar deneyin.')
        setApiKey('')
      }
    } catch {
      setError('Sunucuya bağlanılamadı.')
      setApiKey('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-5 pointer-events-none"
        style={{ backgroundImage: 'linear-gradient(#00ff88 1px, transparent 1px), linear-gradient(90deg, #00ff88 1px, transparent 1px)', backgroundSize: '40px 40px' }}
      />

      <div className="relative w-full max-w-sm px-4">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-accent text-4xl font-bold tracking-widest mb-1">BORSABOT</div>
          <div className="text-muted text-xs tracking-widest">KRİPTO TRADİNG DASHBOARD</div>
        </div>

        {/* Card */}
        <div className="card border border-border space-y-5">
          <div>
            <div className="text-text font-semibold text-sm mb-1">Giriş Yap</div>
            <div className="text-muted text-xs">Devam etmek için API anahtarınızı girin</div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-muted text-xs block mb-1.5">API Anahtarı</label>
              <input
                type="password"
                value={input}
                onChange={e => { setInput(e.target.value); setError('') }}
                placeholder="••••••••••••••••••••••••"
                autoFocus
                className="w-full bg-bg border border-border rounded px-3 py-2.5 text-text font-mono text-sm focus:outline-none focus:border-accent/60 transition-colors"
              />
            </div>

            {error && (
              <div className="text-danger text-xs bg-danger/5 border border-danger/20 rounded px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="w-full btn-accent py-2.5 text-sm font-semibold tracking-wider"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="inline-block w-3 h-3 border border-accent border-t-transparent rounded-full animate-spin" />
                  Doğrulanıyor...
                </span>
              ) : 'GİRİŞ YAP'}
            </button>
          </form>

          <div className="border-t border-border pt-4">
            <div className="text-xs text-muted space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
                Telegram üzerinden paralel çalışmaya devam eder
              </div>
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
                Tüm işlemler şifreli bağlantı üzerinden yapılır
              </div>
            </div>
          </div>
        </div>

        <div className="text-center mt-6 text-muted text-xs">
          strastix.com © {new Date().getFullYear()}
        </div>
      </div>
    </div>
  )
}
