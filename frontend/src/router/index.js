import { createRouter, createWebHashHistory } from 'vue-router'
import { resolveView } from '@/router/resolveView.js'

// ── Top‑level (guest) views — imported directly --------------------------------
import StyleView     from '@/viewsTop/StyleView.vue'

const LoginView     = () => import('@/viewsTop/LoginView.vue')
const RegisterView  = () => import('@/viewsTop/RegisterView.vue')
const ErrorView     = () => import('@/viewsTop/ErrorView.vue')

// ────────────────────────────────────────────────────────────────────────────────
// Route groups
// ────────────────────────────────────────────────────────────────────────────────

// 1. Guest / top routes (no prefix)
const topRoutes = [
  // Landing: always redirect to the public dashboard
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

export default router
