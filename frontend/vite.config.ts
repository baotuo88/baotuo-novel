// AIMETA P=Vite配置_构建和开发服务器配置|R=构建配置_代理配置|NR=不含业务逻辑|E=-|X=internal|A=Vite配置|D=vite|S=fs|RD=./README.ai
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (
            id.includes('/vue/') ||
            id.includes('/pinia/') ||
            id.includes('/vue-router/')
          ) {
            return 'framework'
          }
          if (id.includes('/naive-ui/es/data-table/')) {
            return 'naive-data-table'
          }
          if (
            id.includes('/naive-ui/es/form/') ||
            id.includes('/naive-ui/es/input/') ||
            id.includes('/naive-ui/es/input-number/') ||
            id.includes('/naive-ui/es/select/') ||
            id.includes('/naive-ui/es/date-picker/') ||
            id.includes('/naive-ui/es/switch/') ||
            id.includes('/naive-ui/es/tabs/')
          ) {
            return 'naive-form'
          }
          if (
            id.includes('/naive-ui/es/modal/') ||
            id.includes('/naive-ui/es/popconfirm/') ||
            id.includes('/naive-ui/es/alert/') ||
            id.includes('/naive-ui/es/spin/') ||
            id.includes('/naive-ui/es/tag/')
          ) {
            return 'naive-feedback'
          }
          if (
            id.includes('/naive-ui/es/button/') ||
            id.includes('/naive-ui/es/layout/') ||
            id.includes('/naive-ui/es/menu/') ||
            id.includes('/naive-ui/es/scrollbar/') ||
            id.includes('/naive-ui/es/space/') ||
            id.includes('/naive-ui/es/card/') ||
            id.includes('/naive-ui/es/pagination/')
          ) {
            return 'naive-core'
          }
          if (
            id.includes('/naive-ui/') ||
            id.includes('/vueuc/') ||
            id.includes('/vooks/') ||
            id.includes('/@css-render/')
          ) {
            return 'naive-shared'
          }
          if (id.includes('/chart.js/')) {
            return 'charts'
          }
          if (id.includes('/@headlessui/')) {
            return 'headlessui'
          }
          if (id.includes('/marked/')) {
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
})
