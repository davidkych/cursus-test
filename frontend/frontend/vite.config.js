import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // Serve and build the app at the root URL –
  // no /admin-one-vue-tailwind/ prefix in production
  base: '/',
  plugins: [vue()],
  server: { port: 5173 },
  build:  { outDir: 'dist' }
})
