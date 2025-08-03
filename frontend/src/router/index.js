// frontend/src/router/index.js
// ──────────────────────────────────────────────────────────────────────────────
// Adds per-route auth protection + dev/staging bypass
// ──────────────────────────────────────────────────────────────────────────────
import { createRouter, createWebHashHistory } from 'vue-router'
import { resolveView } from '@/router/resolveView.js'
import { useAuthStore } from '@/stores/auth.js'          // NEW

// ── Top-level (guest) views – direct imports ──────────────────────────────────
import StyleView from '@/viewsTop/StyleView.vue'

const LoginView         = () => import('@/viewsTop/LoginView.vue')
const RegisterView      = () => import('@/viewsTop/RegisterView.vue')
const ErrorView         = () => import('@/viewsTop/ErrorView.vue')
const PropicGalleryView = () => import('@/viewsTop/PropicGalleryView.vue')

// ──────────────────────────────────────────────────────────────────────────────
// Route groups
// ──────────────────────────────────────────────────────────────────────────────

// 1. Guest / top routes (no auth)
const topRoutes = [
  { path: '/', redirect: '/public/dashboard' },
  { meta: { title: 'Select style' },      path: '/style',           name: 'style',           component: StyleView },
  { meta: { title: 'Login' },             path: '/login',           name: 'login',           component: LoginView },
  { meta: { title: 'Register' },          path: '/register',        name: 'register',        component: RegisterView },
  { meta: { title: 'Error' },             path: '/error',           name: 'error',           component: ErrorView },
  { meta: { title: 'Profile pictures' },  path: '/propic-gallery',  name: 'propic-gallery',  component: PropicGalleryView },
]

// 2. Public UI routes  (/public/*) – AUTH REQUIRED
const publicRoutes = [
  { meta: { title: 'Dashboard',          requiresAuth: true }, path: '/public/dashboard',   name: 'pub-dashboard',   component: resolveView('HomeView.vue',       'public') },
  { meta: { title: 'Tables',             requiresAuth: true }, path: '/public/tables',      name: 'pub-tables',      component: resolveView('TablesView.vue',     'public') },
  { meta: { title: 'Forms',              requiresAuth: true }, path: '/public/forms',       name: 'pub-forms',       component: resolveView('FormsView.vue',      'public') },
  { meta: { title: 'Profile',            requiresAuth: true }, path: '/public/profile',     name: 'pub-profile',     component: resolveView('ProfileView.vue',    'public') },
  { meta: { title: 'Ui',                 requiresAuth: true }, path: '/public/ui',          name: 'pub-ui',          component: resolveView('UiView.vue',         'public') },
  { meta: { title: 'Responsive layout',  requiresAuth: true }, path: '/public/responsive',  name: 'pub-responsive',  component: resolveView('ResponsiveView.vue', 'public') },
]

// 3. Admin UI routes  (/admin/*) – AUTH REQUIRED
const adminRoutes = [
  { meta: { title: 'Dashboard (Admin)',  requiresAuth: true }, path: '/admin/dashboard',   name: 'adm-dashboard',   component: resolveView('HomeView.vue',       'admin') },
  { meta: { title: 'Tables',             requiresAuth: true }, path: '/admin/tables',      name: 'adm-tables',      component: resolveView('TablesView.vue',     'admin') },
  { meta: { title: 'Forms',              requiresAuth: true }, path: '/admin/forms',       name: 'adm-forms',       component: resolveView('FormsView.vue',      'admin') },
  { meta: { title: 'Profile',            requiresAuth: true }, path: '/admin/profile',     name: 'adm-profile',     component: resolveView('ProfileView.vue',    'admin') },
  { meta: { title: 'Ui',                 requiresAuth: true }, path: '/admin/ui',          name: 'adm-ui',          component: resolveView('UiView.vue',         'admin') },
  { meta: { title: 'Responsive layout',  requiresAuth: true }, path: '/admin/responsive',  name: 'adm-responsive',  component: resolveView('ResponsiveView.vue', 'admin') },
]

// ──────────────────────────────────────────────────────────────────────────────
// Router instance
// ──────────────────────────────────────────────────────────────────────────────
const router = createRouter({
  history: createWebHashHistory(),
  routes: [...topRoutes, ...publicRoutes, ...adminRoutes],
  scrollBehavior(_to, _from, saved) {
    return saved || { top: 0 }
  },
})

// ──────────────────────────────────────────────────────────────────────────────
// Global navigation guard – auth + dev/staging bypass
// ──────────────────────────────────────────────────────────────────────────────
router.beforeEach((to, _from, next) => {
  // DEV / STAGING environments should not block navigation
  const isDevOrStaging =
    location.hostname === 'localhost' ||
    (import.meta.env.VITE_API_BASE || '').includes('staging')

  if (isDevOrStaging) return next()

  if (to.meta.requiresAuth) {
    const auth = useAuthStore()
    if (!auth.isAuthenticated) {
      return next({ path: '/login', query: { redirect: to.fullPath } })
    }
  }
  return next()
})

export default router
