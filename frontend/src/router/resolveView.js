/**
 * Runtime resolver that returns the correct component (admin vs public)
 * based on the current user-mode store setting — or an explicit override.
 *
 * Usage in router definitions
 * ---------------------------
 * import { resolveView } from '@/router/resolveView.js'
 *
 * {
 *   path: '/public/dashboard',
 *   name: 'pub-dashboard',
 *   component: resolveView('HomeView.vue', 'public'),   // hard-wired to public
 * }
 *
 * {
 *   path: '/admin/forms',
 *   name: 'adm-forms',
 *   component: resolveView('FormsView.vue', 'admin'),   // hard-wired to admin
 * }
 *
 * If the second argument is omitted the resolver uses the current
 * value of userMode.isAdmin at *navigation time* — handy for dynamic cases.
 */

import { useUserMode } from '@/stores/userMode.js'

// ── Static import maps (evaluated at build-time so Vite can tree-shake) ──
const publicViews = import.meta.glob('../viewsPublic/*View.vue')
const adminViews  = import.meta.glob('../viewsAdmin/*View.vue')

/** Map mode → import.meta.glob dictionary */
const viewMaps = {
  public: publicViews,
  admin:  adminViews,
}

/**
 * @param {string} viewFile   e.g. 'HomeView.vue'  (MUST include extension)
 * @param {'public'|'admin'} [mode]  Explicit override; omit to use store.
 * @returns {() => Promise<any>}     Async component for Vue-router
 */
export function resolveView(viewFile, mode) {
  // Decide which folder to use
  const selectedMode = mode
    ? mode
    : useUserMode().isAdmin
      ? 'admin'
      : 'public'

  const map = viewMaps[selectedMode]
  const key = `../views${selectedMode.charAt(0).toUpperCase() + selectedMode.slice(1)}/${viewFile}`

  if (!map[key]) {
    throw new Error(
      `[resolveView] Component ${viewFile} not found in ${selectedMode} folder`,
    )
  }
  return map[key]          // returns an async component loader
}
