// frontend/src/stores/auth.js
// Centralized auth store: token, current user, avatar URL, init/login/logout/fetchMe.
// - No hardcoding of API base (service layer already handles VITE_API_BASE).
// - Uses only built-in /assets/propics/*.png for avatars unless backend provides a short-lived SAS.
// - Supports optional dev mock via VITE_AUTH_MOCK=1.
// - Leaves routing decisions to callers (e.g., router guards / NavBar).

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { login as apiLogin, me as apiMe } from '@/services/auth.js' // ← direct import; no top-level await
import { useMainStore } from '@/stores/main.js' // ← keep top-bar name in sync

/* ─────────────────────────── constants ─────────────────────────── */
const TOKEN_KEY = 'auth.token'
const MOCK = import.meta.env?.VITE_AUTH_MOCK === '1'

/* ───────────────────────── avatar catalog ─────────────────────────
Build a { [id:number]: url } map from /assets/propics/*.png at build time
(eager + treeshakeable with Vite).
*/
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

/**
 * Resolve avatar URL for display.
 * - If the user's profile is marked as "custom" and backend provided a short-lived SAS
 *   (`avatar_url` from /me), prefer that URL.
 * - Otherwise fall back to the bundled sprite by numeric `profile_pic_id`.
 */
function resolveAvatarUrl(profile_pic_id, profile_pic_type, avatar_url) {
  if (profile_pic_type === 'custom' && typeof avatar_url === 'string' && avatar_url) {
    return avatar_url
  }
  // Only 'default' supported for bundled sprites
  const id = Number(profile_pic_id) || avatarIds[0] || 1
  return avatarMap[id] || avatarMap[avatarIds[0]] || ''
}

/** Keep main store's display name & e-mail in sync with the auth user. */
function syncMainStoreUser(u) {
  const name = u?.username || ''
  const email = u?.email || ''
  try {
    const main = useMainStore()
    main.setUser({ name, email })
  } catch {
    // Pinia may not be mounted yet during early init; safe to ignore
  }
}

/* ─────────────────────────── store ─────────────────────────────── */
export const useAuth = defineStore('auth', () => {
  // state
  const token = ref(/** @type {string|null} */ (null))
  const user = ref(
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
      avatar_url?: string               // ⟨NEW⟩ short-lived SAS from /me (optional)
      // ⟨NEW⟩ account flags
      is_admin?: boolean
      is_premium_member?: boolean
      // ⟨NEW⟩ Latest login telemetry snapshot (optional; shape mirrors backend)
      login_context?: {
        last_login_utc?: string
        ip?: string
        ua?: {
          raw?: string
          browser?: { name?: string, version?: string }
          os?: { name?: string, version?: string }
          is_mobile?: boolean
          is_tablet?: boolean
          is_pc?: boolean
          is_bot?: boolean
        }
        locale?: { client?: string|null, accept_language?: string|null }
        timezone?: string
        geo?: { country_iso2?: string, source?: string }
      }
    }} */ (null),
  )
  const inited = ref(false)

  // getters
  const isAuthenticated = computed(() => !!token.value)
  const displayName = computed(() => user.value?.username || '')
  const avatarUrl = computed(() =>
    resolveAvatarUrl(
      user.value?.profile_pic_id,
      user.value?.profile_pic_type,
      user.value?.avatar_url, // ⟨NEW⟩ prefer SAS if custom
    ),
  )

  // ⟨NEW⟩ convenience getters for telemetry (safe, read-only)
  const lastLoginAt = computed(() => {
    const iso = user.value?.login_context?.last_login_utc
    return iso ? new Date(iso).toISOString() : null
  })
  const lastLoginSummary = computed(() => {
    const lc = user.value?.login_context
    if (!lc) return ''
    const parts = []
    const browserName = lc.ua?.browser?.name || ''
    const browserVer = lc.ua?.browser?.version || ''
    const osName = lc.ua?.os?.name || ''
    const osVer = lc.ua?.os?.version || ''
    const country = lc.geo?.country_iso2 || ''
    const tz = lc.timezone || ''
    if (browserName) parts.push(browserVer ? ${browserName} ${browserVer} : browserName)
    if (osName) parts.push(osVer ? ${osName} ${osVer} : osName)
    if (country) parts.push(country)
    if (tz) parts.push(tz)
    return parts.join(' • ')
  })

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
        // NEW flags (defaults)
        is_admin: false,
        is_premium_member: false,
        // Demo telemetry (optional)
        login_context: {
          last_login_utc: new Date().toISOString(),
          ip: '203.0.113.42',
          ua: { browser: { name: 'Mock', version: '0' }, os: { name: 'MockOS', version: '0' }, is_pc: true },
          locale: { client: 'en-GB', accept_language: 'en-GB' },
          timezone: 'Europe/London',
          geo: { country_iso2: 'GB', source: 'mock' },
        },
      }
      // ensure top-bar picks up the username
      syncMainStoreUser(user.value)
      inited.value = true
      return
    }

    if (token.value) {
      try {
        user.value = await apiMe()
        // ensure top-bar picks up the username after refresh
        syncMainStoreUser(user.value)
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
        email: ${creds.username}@example.com,
        created: new Date().toISOString(),
        profile_pic_id: 1,
        profile_pic_type: 'default',
        // NEW flags (defaults)
        is_admin: false,
        is_premium_member: false,
        login_context: {
          last_login_utc: new Date().toISOString(),
          ip: '203.0.113.42',
          ua: { browser: { name: 'Mock', version: '0' }, os: { name: 'MockOS', version: '0' }, is_pc: true },
          locale: { client: 'en-GB', accept_language: 'en-GB' },
          timezone: 'Europe/London',
          geo: { country_iso2: 'GB', source: 'mock' },
        },
      }
      // sync for top-bar
      syncMainStoreUser(user.value)
      return
    }

    const res = await apiLogin({ username: creds.username, password: creds.password })
    // apiLogin returns { access_token, token_type }
    token.value = res?.access_token || null
    writeToken(token.value)

    // Fetch current profile
    try {
      user.value = await apiMe()
      // sync for top-bar
      syncMainStoreUser(user.value)
    } catch {
      token.value = null
      writeToken(null)
      user.value = null
      throw new Error('Failed to fetch user profile')
    }
  }

  function setUser(u) {
    user.value = u
    // keep main store in sync when caller updates the user programmatically
    syncMainStoreUser(user.value)
  }

  /** ⟨NEW⟩ Convenience: refresh current user from /me and update store. */
  async function refresh() {
    try {
      const u = await apiMe()
      user.value = u
      syncMainStoreUser(user.value)
    } catch {
      // If session expired, clear local auth state and bubble up
      token.value = null
      writeToken(null)
      user.value = null
      throw new Error('Session expired')
    }
  }

  function logout() {
    token.value = null
    user.value = null
    writeToken(null)
    // Not resetting main store name here; authenticated layouts usually disappear after logout.
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
    lastLoginAt,
    lastLoginSummary,
    // actions
    init,
    login,
    logout,
    setUser,
    refresh,
    // ⟨NEW⟩
  }
})
