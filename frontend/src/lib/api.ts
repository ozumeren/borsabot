import axios from 'axios'

const API_KEY = localStorage.getItem('borsabot_api_key') ?? ''

export const api = axios.create({
  baseURL: '/api',
  headers: {
    Authorization: `Bearer ${API_KEY}`,
  },
})

export function setApiKey(key: string) {
  localStorage.setItem('borsabot_api_key', key)
  api.defaults.headers['Authorization'] = `Bearer ${key}`
}

export function getApiKey(): string {
  return localStorage.getItem('borsabot_api_key') ?? ''
}

// ── Typed fetchers ──────────────────────────────────────────────────────────

export const fetchDashboard = () => api.get('/dashboard').then(r => r.data)
export const fetchPositions = () => api.get('/positions').then(r => r.data)
export const closePosition = (symbol: string) => api.post(`/positions/close/${symbol}`).then(r => r.data)
export const fetchTrades = (params?: Record<string, unknown>) => api.get('/trades', { params }).then(r => r.data)
export const fetchTradeStats = () => api.get('/trades/stats').then(r => r.data)
export const fetchSignalScan = () => api.get('/signals/scan').then(r => r.data)
export const fetchSignalOverview = () => api.get('/signals/overview').then(r => r.data)
export const fetchFullScan = () => api.get('/signals/full-scan').then(r => r.data)
export const fetchSignal = (symbol: string) => api.get(`/signals/${symbol}`).then(r => r.data)
export const fetchSentimentOverview = () => api.get('/sentiment/overview').then(r => r.data)
export const fetchCoinSentiment = (coin: string) => api.get(`/sentiment/${coin}`).then(r => r.data)
export const fetchBotStatus = () => api.get('/bot/status').then(r => r.data)
export const triggerScan = () => api.post('/bot/scan').then(r => r.data)
export const fetchSettings = () => api.get('/settings').then(r => r.data)
export const updateSettings = (data: Record<string, unknown>) => api.put('/settings', data).then(r => r.data)
export const fetchChart = (symbol: string, timeframe = '15m', limit = 200) =>
  api.get(`/chart/${symbol}`, { params: { timeframe, limit } }).then(r => r.data)
export const fetchCoinDetail = (symbol: string) => api.get(`/coin/${symbol}`).then(r => r.data)
export const refreshCoinDetail = (symbol: string) => api.post(`/coin/${symbol}/refresh`).then(r => r.data)
