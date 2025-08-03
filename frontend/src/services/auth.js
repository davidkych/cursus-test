// frontend/src/services/auth.js
// ──────────────────────────────────────────────────────────────────────────────
// Lightweight helpers for the /api/auth/* endpoints
//   • register(payload)
//   • login(payload)
//   • getMe(accessToken)         ← NEW
//   • decodeJwt(token)           ← tiny helper (no external dep)
// ──────────────────────────────────────────────────────────────────────────────

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''

/* ─── shared error-handler ──────────────────────────────────────────────── */
async function handleError (res, fallbackMsg) {
  const body = await res.json().catch(() => ({}))
  throw new Error(body.detail || fallbackMsg)
}

/* ─── tiny JWT decoder (no dependency) ─────────────────────────────────── */
export function decodeJwt (token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const json   = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => `%${('00' + c.charCodeAt(0).toString(16)).slice(-2)}`)
        .join(''),
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

/* ─── API calls ─────────────────────────────────────────────────────────── */

/**
 * Register a new user.
 *
 * Expected payload shape (all keys optional except the originals):
 * {
 *   username: string,
 *   email:    string,
 *   password: string,
 *   // NEW optional fields
 *   profile_pic_id:   number,             // numeric ID (1, 2, 3 …)
 *   profile_pic_type: 'default'|'custom'
 * }
 */
export async function register (payload) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Registration failed')
  return res.json()                        // returns created user record
}

/**
 * Login and receive JWT (now contains "username" in the payload).
 *
 * Returns:
 * { access_token: '…', token_type: 'bearer' }
 */
export async function login (payload) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Login failed')
  return res.json()
}

/**
 * Fetch the current user record (username, e-mail, avatar choice, …).
 * The JWT must be supplied by the caller.
 */
export async function getMe (accessToken) {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) await handleError(res, 'Failed to fetch user profile')
  return res.json()
}
