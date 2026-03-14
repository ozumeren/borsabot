import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useState } from 'react'
import { getApiKey } from './lib/api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Positions from './pages/Positions'
import Scanner from './pages/Scanner'
import Trades from './pages/Trades'
import Sentiment from './pages/Sentiment'
import Settings from './pages/Settings'
import Charts from './pages/Charts'
import CoinDetail from './pages/CoinDetail'
import StatusBar from './components/StatusBar'

const NAV = [
  { to: '/', label: 'Panel', exact: true },
  { to: '/charts', label: 'Grafikler' },
  { to: '/positions', label: 'Pozisyonlar' },
  { to: '/scanner', label: 'Tarayıcı' },
  { to: '/trades', label: 'İşlemler' },
  { to: '/sentiment', label: 'Duygu' },
  { to: '/settings', label: 'Ayarlar' },
]

export default function App() {
  const [authed, setAuthed] = useState(() => !!getApiKey())

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />
  }

  return (
    <BrowserRouter>
      <div className="flex flex-col min-h-screen">
        {/* Top nav */}
        <nav className="border-b border-border bg-card px-4 flex items-center gap-1 h-12 shrink-0">
          <span className="text-accent font-mono font-bold mr-6 text-sm tracking-widest">
            ◈ BORSABOT
          </span>
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.exact}
              className={({ isActive }) =>
                `px-3 py-1 rounded text-xs font-mono transition-colors ${
                  isActive
                    ? 'text-accent bg-accent/10 border border-accent/20'
                    : 'text-muted hover:text-text hover:bg-white/5'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
          <div className="ml-auto flex items-center gap-3">
            <StatusBar />
            <button
              className="text-muted text-xs hover:text-danger transition-colors"
              onClick={() => { localStorage.removeItem('borsabot_api_key'); setAuthed(false) }}
              title="Çıkış yap"
            >
              ⏻
            </button>
          </div>
        </nav>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/charts" element={<Charts />} />
            <Route path="/charts/:coinParam" element={<Charts />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/scanner" element={<Scanner />} />
            <Route path="/coin/:symbol" element={<CoinDetail />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/sentiment" element={<Sentiment />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
