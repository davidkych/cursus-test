import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useMainStore } from '@/stores/main.js'
import { useAuth } from '@/stores/auth.js'

import './css/main.css'

// Init Pinia
const pinia = createPinia()

// Create Vue app
const app = createApp(App)
app.use(router).use(pinia)

// Bootstrap: ensure auth state is loaded before first render
;(async () => {
  try {
    const auth = useAuth(pinia)
    await auth.init() // reads token, fetches /api/auth/me (or mock)
  } catch {
    // ignore init errors; guards will handle redirects
  }

  // Mount the app after auth is ready so avatar/name render correctly
  app.mount('#app')

  // Init main store (sample data; unchanged behavior)
  const mainStore = useMainStore(pinia)
  mainStore.fetchSampleClients()
  mainStore.fetchSampleHistory()
})()

// Dark mode
// Uncomment, if you'd like to restore persisted darkMode setting, or use `prefers-color-scheme: dark`. Make sure to uncomment localStorage block in src/stores/darkMode.js
// import { useDarkModeStore } from './stores/darkMode'

// const darkModeStore = useDarkModeStore(pinia)

// if (
//   (!localStorage['darkMode'] && window.matchMedia('(prefers-color-scheme: dark)').matches) ||
//   localStorage['darkMode'] === '1'
// ) {
//   darkModeStore.set(true)
// }

// Default title tag
const defaultDocumentTitle = 'Admin One Vue 3 Tailwind'

// Set document title from route meta
router.afterEach((to) => {
  document.title = to.meta?.title
    ? `${to.meta.title} — ${defaultDocumentTitle}`
    : defaultDocumentTitle
})
