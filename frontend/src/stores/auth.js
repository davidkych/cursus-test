// frontend/src/stores/auth.js
// Auth/session store (Pinia).
// ▸ Keeps the JWT in localStorage
// ▸ Exposes isAuthenticated, username, avatarUrl, etc.
// ▸ Auto-hydrates profile data via GET /api/auth/me

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe as apiGetMe } from '@/services/auth.js'

const STORAGE_KEY = 'access_token'

export const useAuthStore = defineStore('auth', () => {
  /* ─── state ───────────────────────────────────────────── */
  const accessToken     = ref('')               // raw JWT
  const username        = ref('')
  const profilePicId    = ref(null)
  const profilePicType  = ref('default')        // 'default' | 'custom' (future)

  /* ─── getters ─────────────────────────────────────────── */
  const isAuthenticated = computed(() => !!accessToken.value)

  const avatarUrl = computed(() => {
    if (!profilePicId.value) return ''
    // built-in avatars only (1.png … 23.png)
    return new URL(
      `../assets/propics/${profilePicId.value}.png`,
      import.meta.url,
    ).href
  })

  /* ─── helpers ─────────────────────────────────────────── */
  function _persistToken () {
    if (typeof window !== 'undefined') {
      if (accessToken.value) localStorage.setItem(STORAGE_KEY, accessToken.value)
      else localStorage.removeItem(STORAGE_KEY)
    }
  }

  /* ─── actions ─────────────────────────────────────────── */
  async function setToken (token) {
    accessToken.value = token
    _persistToken()
    await refreshProfile()              // hydrate user fields
  }

  async function refreshProfile () {
    if (!accessToken.value) return
    try {
      const data = await apiGetMe(accessToken.value)   // Authorization handled inside service
      username.value        = data.username
      profilePicId.value    = data.profile_pic_id  ?? null
      profilePicType.value  = data.profile_pic_type ?? 'default'
    } catch (err) {
      // Invalid/expired token ⇒ force logout
      console.error('[auth] refreshProfile failed:', err)
      logout()
    }
  }

  function logout () {
    accessToken.value   = ''
    username.value      = ''
    profilePicId.value  = null
    profilePicType.value = 'default'
    _persistToken()
  }

  /* ─── bootstrap from localStorage ─────────────────────── */
  ;(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        accessToken.value = saved
        // Fire-and-forget; errors handled inside
        refreshProfile()
      }
    }
  })()

  /* expose */
  return {
    // state
    accessToken,
    username,
    profilePicId,
    profilePicType,
    // getters
    isAuthenticated,
    avatarUrl,
    // actions
    setToken,
    refreshProfile,
    logout,
  }
})
