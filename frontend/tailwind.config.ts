import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#0a0a0a',
        card:    '#111111',
        border:  '#1f1f1f',
        accent:  '#00ff88',
        danger:  '#ff3333',
        warn:    '#ffaa00',
        muted:   '#555555',
        text:    '#e0e0e0',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
