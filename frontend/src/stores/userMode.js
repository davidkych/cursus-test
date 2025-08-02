// Pinia store that tracks whether the UI is in public (default) or admin mode
// ── usage ──────────────────────────────────────────────────────────────
// import { useUserMode } from '@/stores/userMode.js'
// const userMode = useUserMode()
// if (userMode.isAdmin) { ... }          // read
// userMode.toggle()                      // toggle
// userMode.setAdmin() / userMode.setPublic()  // explicit set
// ────────────────────────────────────────────────────────────────────────

import { defineStore } from 'pinia'

export const useUserMode = defineStore('userMode', {
  state: () => ({
    /** `true` → admin UI, `false` → public UI */
    isAdmin: false,
  }),

  actions: {
    /** Switch to admin mode */
    setAdmin() {
      this.isAdmin = true
    },

    /** Switch to public (user) mode */
    setPublic() {
      this.isAdmin = false
    },

    /** Flip between admin ↔︎ public */
    toggle() {
      this.isAdmin = !this.isAdmin
    },
  },
})
