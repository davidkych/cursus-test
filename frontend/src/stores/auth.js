// frontend/src/stores/auth.js
// Centralized auth store: token, current user, avatar URL, init/login/logout/fetchMe.
// - No hardcoding of API base (service layer already handles VITE_API_BASE).
// - Uses only built-in /assets/propics/*.png for avatars (per your decision).
// - Supports optional dev mock via VITE_AUTH_MOCK=1.
// - Leaves routing decisions to callers (e.g., router guards / NavBar).

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { login as apiLogin } from '@/services/auth.js'

// NOTE: we'll call api.me() once you add it next step.
let apiMe = null
try {
  // Soft import to avoid breaking dev until services/auth.js is updated.
  // eslint-disable-next-line import/no-unresolved
  const mod = await import('@/services/auth.js')
  apiMe = mod.me
} catch (_) {
  /* services/auth.js will add me() in a later step */
}

/* ─────────────────────────── constants ─────────────────────────── */
const TOKEN_KEY = 'auth.token'
const MOCK      = import.meta.env?.VITE_AUTH_MOCK === '1'

/* ───────────────────────── avatar catalog ─────────────────────────
   Build a { [id:number]: url } map from /assets/propics/*.png
   at build time (eager + treeshakeable with Vite). */
const avatarFiles = import.meta.glob('@/assets/propics/*.png', {
  eager: true,
  import: 'default',
})
const avatarMap = Object.entries(avatarFiles).reduce((acc, [path, url]) => {
  const m = path.match(/\/(\d+)\.png$/)
  if (m) acc[Number(m[1])] = url
  return acc
}, /** @type {Record<number, string>} */ ({}))

const avatarIds = Object.keys(avatarMap)
  .map((n) => Number(n))
  .sort((a, b) => a - b)

/* ─────────────────────────── helpers ───────────────────────────── */
function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore storage errors (private mode, etc.) */
  }
}

function resolveAvatarUrl(profile_pic_id, profile_pic_type) {
  // Only 'default' supported for now
  const id = Number(profile_pic_id) || avatarIds[0] || 1
  return avatarMap[id] || avatarMap[avatarIds[0]] || ''
}

/* ─────────────────────────── store ─────────────────────────────── */
export const useAuth = defineStore('auth', () => {
  // state
  const token = ref(/** @type {string|null} */ (null))
  const user  = ref(
    /** @type {null | {
      id?: string
      username?: string
      email?: string
      created?: string
      gender?: 'male'|'female'
      dob?: string
      country?: string
      profile_pic_id?: number
      profile_pic_type?: 'default'|'custom'
    }} */ (null),
  )
  const inited = ref(false)

  // getters
  const isAuthenticated = computed(() => !!token.value)
  const displayName     = computed(() => user.value?.username || '')
  const avatarUrl       = computed(() =>
    resolveAvatarUrl(user.value?.profile_pic_id, user.value?.profile_pic_type),
  )

  // actions
  async function init() {
    if (inited.value) return
    token.value = readToken()
    if (MOCK) {
      // In mock mode, synthesize a user quickly so UI works without backend.
      if (!token.value) {
        token.value = 'mock.jwt.token'
        writeToken(token.value)
      }
      user.value = {
        id: 'mock-user',
        username: 'mockuser',
        email: 'mock@example.com',
        created: new Date().toISOString(),
        gender: 'male',
        dob: '1990-01-01',
        country: 'HKG',
        profile_pic_id: 1,
        profile_pic_type: 'default',
      }
      inited.value = true
      return
    }

    if (token.value && apiMe) {
      try {
        user.value = await apiMe()
      } catch {
        // Token invalid/expired → clear
        token.value = null
        writeToken(null)
        user.value = null
      }
    }
    inited.value = true
  }

  /**
   * Perform login, store token, fetch profile.
   * @param {{username: string, password: string}} creds
   */
  async function login(creds) {
    if (MOCK) {
      token.value = 'mock.jwt.token'
      writeToken(token.value)
      // emulate "me"
      user.value = {
        id: creds.username,
        username: creds.username,
        email: `${creds.username}@example.com`,
        created: new Date().toISOString(),
        profile_pic_id: 1,
        profile_pic_type: 'default',
      }
      return
    }

    const res = await apiLogin({ username: creds.username, password: creds.password })
    // apiLogin returns { access_token, token_type }
    token.value = res?.access_token || null
    writeToken(token.value)

    // Fetch current profile (requires /api/auth/me)
    if (apiMe) {
      try {
        user.value = await apiMe()
      } catch {
        // If we fail to fetch profile, treat as unauthenticated
        token.value = null
        writeToken(null)
        user.value = null
        throw new Error('Failed to fetch user profile')
      }
    }
  }

  function setUser(u) {
    user.value = u
  }

  function logout() {
    token.value = null
    user.value  = null
    writeToken(null)
    // Redirection is handled by caller (NavBar or route guard)
  }

  return {
    // state
    token,
    user,
    inited,
    // getters
    isAuthenticated,
    displayName,
    avatarUrl,
    // actions
    init,
    login,
    logout,
    setUser,
  }
})
