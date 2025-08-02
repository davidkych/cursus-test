import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  base: '/',
  plugins: [vue(), vueDevTools(), tailwindcss()],
  resolve: {
    alias: {
      '@':            fileURLToPath(new URL('./src',            import.meta.url)),
      '@viewsPublic': fileURLToPath(new URL('./src/viewsPublic', import.meta.url)), // ← NEW
      '@viewsAdmin':  fileURLToPath(new URL('./src/viewsAdmin',  import.meta.url)), // ← NEW
      '@viewsTop':    fileURLToPath(new URL('./src/viewsTop',    import.meta.url)), // ← NEW
    },
  },
})
