// frontend/src/services/auth.js
// Lightweight helper for the /api/auth/* endpoints

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''
const TOKEN_KEY = 'auth.token'
const MOCK = import.meta.env?.VITE_AUTH_MOCK === '1'

/**
 * Convert non-2xx fetch responses into thrown Error objects,
 * extracting FastAPI-style detail messages when present.
 */
function handleError(res, fallbackMsg) {
  return res
    .json()
    .catch(() => ({}))
    .then((body) => {
      const d = body?.detail
      let msg = fallbackMsg

      if (typeof d === 'string') {
        msg = d
      } else if (Array.isArray(d)) {
        // FastAPI validation errors
        msg = d
          .map((e) => e?.msg || (typeof e === 'string' ? e : JSON.stringify(e)))
          .join(' • ')
      } else if (d && typeof d === 'object') {
        msg = d.msg || d.error || JSON.stringify(d)
      } else if (body?.message && typeof body.message === 'string') {
        msg = body.message
      }

      throw new Error(msg)
    })
}

/* ─────────────────────────── token helpers ─────────────────────────── */
function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}
function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch { /* ignore */ }
}

/* ─────────────────────────── authFetch ───────────────────────────────
   Wrapper around fetch that injects Authorization header (if token present)
   and silently clears token on 401 (expiry) per requirement #5. */
export async function authFetch(url, init = {}) {
  const headers = new Headers(init.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // Do not force Content-Type; callers set it when needed.
  headers.set('Accept', 'application/json')

  const res = await fetch(url, { ...init, headers })

  if (res.status === 401) {
    // Silent logout: clear token; let caller route to /login on next nav.
    clearToken()
    // Try to parse error for consistency
    try {
      await handleError(res, 'Unauthorized')
    } catch (err) {
      throw err
    }
  }

  return res
}

/* ─────────────────────────── API calls ─────────────────────────────── */

/**
 * Register a new user.
 *
 * Expected payload shape (all keys optional except the originals):
 * {
 *   username:           string,
 *   email:              string,
 *   password:           string,
 *   // optional fields we now pass through from the Register form:
 *   gender:             'male'|'female',
 *   dob:                'YYYY-MM-DD',
 *   country:            string,
 *   profile_pic_id:     number,
 *   profile_pic_type:   'default'|'custom',
 *   accepted_terms:     boolean
 * }
 * Note: server sets `is_admin` and `is_premium_member` to false by default
 * and does not accept them from the client.
 */
export async function register(payload) {
  if (MOCK) {
    // Minimal happy-path mock for dev convenience
    return Promise.resolve({
      id: payload.username,
      username: payload.username,
      email: payload.email,
      created: new Date().toISOString(),
    })
  }

  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Registration failed')
  return res.json()
}

export async function login(payload) {
  if (MOCK) {
    // Issue a fake token; store reads it, not this layer.
    return Promise.resolve({ access_token: 'mock.jwt.token', token_type: 'bearer' })
  }

  // Attach client-only context via headers (server can’t derive reliably)
  const tz =
    (typeof Intl !== 'undefined' &&
      Intl.DateTimeFormat &&
      Intl.DateTimeFormat().resolvedOptions &&
      Intl.DateTimeFormat().resolvedOptions().timeZone) ||
    ''
  const locale = (typeof navigator !== 'undefined' && navigator.language) || ''

  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // New headers for telemetry
      'X-Client-Timezone': tz,
      'X-Client-Locale': locale,
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Login failed')
  return res.json()
}

/**
 * Get current user profile (requires Authorization bearer token).
 * Returns a profile like:
 * {
 *   id, username, email, created, gender, dob, country,
 *   profile_pic_id, profile_pic_type,
 *   // NEW flags:
 *   is_admin: boolean,
 *   is_premium_member: boolean,
 *   // NEW (optional):
 *   login_context: { last_login_utc, ip, ua, locale, timezone, geo },
 *   // NEW (optional):
 *   profile_pic_url: string | null
 * }
 */
export async function me() {
  if (MOCK) {
    return Promise.resolve({
      id: 'mock-user',
      username: 'mockuser',
      email: 'mock@example.com',
      created: new Date().toISOString(),
      gender: 'male',
      dob: '1990-01-01',
      country: 'HKG',
      profile_pic_id: 1,
      profile_pic_type: 'default',
      // NEW flags with defaults
      is_admin: false,
      is_premium_member: false,
      // Example shape; real backend may omit or differ in mock
      login_context: {
        last_login_utc: new Date().toISOString(),
        ip: '203.0.113.42',
        ua: { browser: { name: 'Mock', version: '0' }, os: { name: 'MockOS', version: '0' } },
        locale: { client: 'en-GB', accept_language: 'en-GB' },
        timezone: 'Europe/London',
        geo: { country_iso2: 'GB', source: 'mock' },
      },
      profile_pic_url: null,
    })
  }

  const res = await authFetch(`${API_BASE}/api/auth/me`, { method: 'GET' })
  if (!res.ok) await handleError(res, 'Failed to fetch profile')
  return res.json()
}

/**
 * Redeem a case-sensitive code and return the updated /me payload.
 * - Requires Authorization bearer token (handled by authFetch).
 */
export async function redeemCode(code) {
  if (MOCK) {
    // In mock mode we can't actually mutate flags; return current profile.
    return me()
  }

  const res = await authFetch(`${API_BASE}/api/auth/codes/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) await handleError(res, 'Redeem failed')
  return res.json()
}

/**
 * ⟨NEW⟩ Upload a custom avatar for the current user.
 * - Sends multipart/form-data to /api/auth/avatar
 * - Returns the updated /me payload (including profile_pic_url and profile_pic_type="custom")
 */
export async function uploadAvatar(file) {
  if (!file) throw new Error('No file provided')

  if (MOCK) {
    // Dev-only: emulate server response by augmenting current /me with a blob URL
    const base = await me()
    try {
      const objectUrl = URL.createObjectURL(file)
      return {
        ...base,
        profile_pic_type: 'custom',
        profile_pic_url: objectUrl,
      }
    } catch {
      return base
    }
  }

  const form = new FormData()
  form.append('file', file, file.name)

  const res = await authFetch(`${API_BASE}/api/auth/avatar`, {
    method: 'POST',
    body: form, // do NOT set Content-Type; browser sets multipart boundary
  })
  if (!res.ok) await handleError(res, 'Avatar upload failed')
  return res.json()
}
