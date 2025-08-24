import { createRouter, createWebHashHistory } from 'vue-router'
import { resolveView } from '@/router/resolveView.js'

// ── Top-level (guest) views — imported directly --------------------------------
import StyleView from '@/viewsTop/StyleView.vue'

const LoginView         = () => import('@/viewsTop/LoginView.vue')
const RegisterView      = () => import('@/viewsTop/RegisterView.vue')
const ErrorView         = () => import('@/viewsTop/ErrorView.vue')
const PropicGalleryView = () => import('@/viewsTop/PropicGalleryView.vue')

// ────────────────────────────────────────────────────────────────────────────────
// Route groups
// ────────────────────────────────────────────────────────────────────────────────

// 1. Guest / top routes (no prefix)
const topRoutes = [
  // Landing: always redirect to the public dashboard (guard may refine)
  {
    path: '/',
    redirect: '/public/dashboard',
  },
  {
    meta: { title: 'Select style' },
    path: '/style',
    name: 'style',
    component: StyleView,
  },
  {
    meta: { title: 'Login' },
    path: '/login',
    name: 'login',
    component: LoginView,
  },
  {
    meta: { title: 'Register' },
    path: '/register',
    name: 'register',
    component: RegisterView,
  },
  {
    meta: { title: 'Error' },
    path: '/error',
    name: 'error',
    component: ErrorView,
  },
  {
    meta: { title: 'Profile pictures' },
    path: '/propic-gallery',
    name: 'propic-gallery',
    component: PropicGalleryView,
  },
]

// 2. Public UI routes  (/public/*)
const publicRoutes = [
  {
    meta: { title: 'Dashboard' },
    path: '/public/dashboard',
    name: 'pub-dashboard',
    component: resolveView('HomeView.vue', 'public'),
  },
  {
    meta: { title: 'Tables' },
    path: '/public/tables',
    name: 'pub-tables',
    component: resolveView('TablesView.vue', 'public'),
  },
  {
    meta: { title: 'Forms' },
    path: '/public/forms',
    name: 'pub-forms',
    component: resolveView('FormsView.vue', 'public'),
  },
  {
    meta: { title: 'Profile' },
    path: '/public/profile',
    name: 'pub-profile',
    component: resolveView('ProfileView.vue', 'public'),
  },
  {
    meta: { title: 'Ui' },
    path: '/public/ui',
    name: 'pub-ui',
    component: resolveView('UiView.vue', 'public'),
  },
  {
    meta: { title: 'Responsive layout' },
    path: '/public/responsive',
    name: 'pub-responsive',
    component: resolveView('ResponsiveView.vue', 'public'),
  },
]

// 3. Admin UI routes  (/admin/*)
const adminRoutes = [
  {
    meta: { title: 'Dashboard (Admin)' },
    path: '/admin/dashboard',
    name: 'adm-dashboard',
    component: resolveView('HomeView.vue', 'admin'),
  },
  {
    meta: { title: 'Tables' },
    path: '/admin/tables',
    name: 'adm-tables',
    component: resolveView('TablesView.vue', 'admin'),
  },
  {
    meta: { title: 'Forms' },
    path: '/admin/forms',
    name: 'adm-forms',
    component: resolveView('FormsView.vue', 'admin'),
  },
  {
    meta: { title: 'Profile' },
    path: '/admin/profile',
    name: 'adm-profile',
    component: resolveView('ProfileView.vue', 'admin'),
  },
  {
    meta: { title: 'Ui' },
    path: '/admin/ui',
    name: 'adm-ui',
    component: resolveView('UiView.vue', 'admin'),
  },
  {
    meta: { title: 'Responsive layout' },
    path: '/admin/responsive',
    name: 'adm-responsive',
    component: resolveView('ResponsiveView.vue', 'admin'),
  },
  // ⟨NEW⟩ Codes generator view (admin)
  {
    meta: { title: 'Codes' },
    path: '/admin/codes',
    name: 'adm-codes',
    component: resolveView('CodesView.vue', 'admin'),
  },
  // ⟨NEW⟩ Users management view (admin)
  {
    meta: { title: 'Users' },
    path: '/admin/users',
    name: 'adm-users',
    component: resolveView('UsersView.vue', 'admin'),
  },
]

// ────────────────────────────────────────────────────────────────────────────────
// Router instance
// ────────────────────────────────────────────────────────────────────────────────

const router = createRouter({
  history: createWebHashHistory(),
  routes: [...topRoutes, ...publicRoutes, ...adminRoutes],
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

/* ─────────────────────────── Global auth guard ────────────────────────────── */
const TOKEN_KEY = 'auth.token'
const MOCK = import.meta.env?.VITE_AUTH_MOCK === '1'

function hasToken() {
  try {
    return !!localStorage.getItem(TOKEN_KEY)
  } catch {
    return false
  }
}
function requiresAuth(path) {
  return path.startsWith('/public/') || path.startsWith('/admin/')
}

router.beforeEach((to, from, next) => {
  // ⟨DEV behavior⟩ When mock mode is ON, bypass all auth redirects.
  if (MOCK) {
    if (to.path === '/') return next('/public/dashboard')
    return next()
  }

  const authed = hasToken()

  if (to.path === '/') {
    next(authed ? '/public/dashboard' : '/login')
    return
  }

  if (requiresAuth(to.path) && !authed) {
    next({ name: 'login' })
    return
  }

  if (to.name === 'login' && authed) {
    next('/public/dashboard')
    return
  }

  next()
})

export default router
