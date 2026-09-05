import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
    proxy: {
      '/api/yahoo': {
        target: 'https://query1.finance.yahoo.com',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/yahoo/, '')
      },
      '/api/zerodha': {
        target: 'https://api.kite.trade',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/zerodha/, '')
      }
    }
  }
})

