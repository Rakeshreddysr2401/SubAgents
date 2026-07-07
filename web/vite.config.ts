import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = 'http://localhost:2024'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat': BACKEND,
      '/auth': BACKEND,
      '/threads': BACKEND,
      '/uploads': BACKEND,
      '/history': BACKEND,
      '/events': BACKEND,
      '/trigger_voice': BACKEND,
      '/health': BACKEND,
      '/ws': { target: BACKEND, ws: true },
    },
  },
})
