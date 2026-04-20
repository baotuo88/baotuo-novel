// AIMETA P=Vite配置_构建和开发服务器配置|R=构建配置_代理配置|NR=不含业务逻辑|E=-|X=internal|A=Vite配置|D=vite|S=fs|RD=./README.ai
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [
    vue(),
    vueJsx(),
    command === 'serve' ? vueDevTools() : null,
  ].filter(Boolean),
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          const normalizedId = id.replace(/\\/g, '/')
          if (
            normalizedId.includes('/node_modules/naive-ui/') ||
            normalizedId.includes('/node_modules/vueuc/') ||
            normalizedId.includes('/node_modules/vooks/') ||
            normalizedId.includes('/node_modules/@css-render/')
          ) {
            return 'naive-ui'
          }
          if (
            normalizedId.includes('/node_modules/vue/') ||
            normalizedId.includes('/node_modules/@vue/') ||
            normalizedId.includes('/node_modules/pinia/') ||
            normalizedId.includes('/node_modules/vue-router/')
          ) {
            return 'framework'
          }
          if (normalizedId.includes('/node_modules/chart.js/')) {
            return 'charts'
          }
          if (normalizedId.includes('/node_modules/@headlessui/')) {
            return 'headlessui'
          }
          if (normalizedId.includes('/node_modules/marked/')) {
            return 'markdown'
          }
          return 'vendor'
        }
      }
    }
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
}))
