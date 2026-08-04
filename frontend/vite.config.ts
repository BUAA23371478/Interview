import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// MAOO 平台：base 必须是 /app/{slug}/，路由 basename 需一致
const SLUG = 'interview-agent'

export default defineConfig({
  base: `/app/${SLUG}/`,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 本地开发把 /app/{slug}/api 代理到后端
      [`/app/${SLUG}/api`]: {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) => path.replace(new RegExp(`^/app/${SLUG}/api`), ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
