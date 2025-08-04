// frontend/src/services/auth.js
// Lightweight helper for the /api/auth/* endpoints

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Convert non-2xx fetch responses into thrown Error objects,
 * extracting FastAPI-style `detail` messages when present.
 */
function handleError(res, fallbackMsg) {
  return res
    .json()
    .catch(() => ({}))
    .then((body) => {
      throw new Error(body.detail || fallbackMsg)
    })
}

/**
 * Register a new user.
 *
 * Expected payload shape (all keys optional except the originals):
 * {
 *   username:           string,
 *   email:              string,
 *   password:           string,
 *   // ── NEW optional fields ───────────────────────────────
 *   profile_pic_id:     number,          // numeric ID (1, 2, 3…)
 *   profile_pic_type:   'default'|'custom'
 * }
 */
export async function register(payload) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Registration failed')
  return res.json()
}

export async function login(payload) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Login failed')
  return res.json()
}
